from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tamigo_intel.classification import evidence_class, opportunity_status
from tamigo_intel.config import SearchConfig, load_config
from tamigo_intel.countries import country_allowed, preset_codes
from tamigo_intel.failures import failure_kind
from tamigo_intel.http_client import HttpClient, HttpError
from tamigo_intel.languages import query_keywords
from tamigo_intel.pipeline import run_search
from tamigo_intel.sources.find_tender import release_to_item
from tamigo_intel.sources.sam_gov import SourceUnavailable
from tamigo_intel.status_text import overall_status
from tamigo_intel.terms import country_code
from tamigo_intel.vault import MemoryVault
from tests.test_core import discovery


def _config(**kwargs) -> SearchConfig:
    base = dict(keywords=["WCAG"], request_interval_seconds=0, max_per_source=10, max_organizations=10)
    base.update(kwargs)
    return SearchConfig(**base)


def test_http_403_is_not_a_certificate_failure():
    assert failure_kind(HttpError("HTTP 403 za https://canadabuys.canada.ca/opendata", status=403)) == "forbidden"
    assert failure_kind(OSError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")) == "tls"
    assert failure_kind(HttpError("HTTP 401", status=401)) == "auth"
    assert failure_kind(HttpError("HTTP 404", status=404)) == "not_found"
    assert failure_kind(HttpError("HTTP 429", status=429)) == "rate_limit"
    assert failure_kind(HttpError("HTTP 503", status=503)) == "server"
    assert failure_kind(TimeoutError("timed out")) == "timeout"


def test_country_filter_is_off_by_default_and_can_exclude(tmp_path: Path):
    assert country_allowed("DE", ["US"], False) is True
    assert country_allowed("DE", ["US"], True) is False
    assert country_allowed("US", ["US", "CA"], True) is True
    assert country_allowed("", ["US"], True) is False
    assert "DE" in preset_codes("eu")
    assert "GB" not in preset_codes("eu")
    assert "GB" in preset_codes("europe")
    assert country_code("GBR") == "GB"
    assert country_code("DEU") == "DE"

    db_path = tmp_path / "t.sqlite"
    from tamigo_intel.db import Database

    db = Database(db_path)

    class Mixed:
        name = "mixed"

        def search(self, config, client):
            return [
                discovery(source_record_id="us", organization_name="US Agency", country="US"),
                discovery(source_record_id="de", organization_name="DE Behörde", country="DE"),
            ]

    open_filter = run_search(db, _config(restrict_countries=False), sources=[Mixed()], client=HttpClient(min_interval=0))
    assert open_filter["status"] == "completed_with_results"
    assert {row["country"] for row in db.query_leads()} == {"US", "DE"}
    db.update_lead_operator(db.query_leads()[0]["id"], "reviewing", "beleška ostaje", "", "unverified_prospect")
    restricted = Database(db_path)
    again = run_search(
        restricted,
        _config(restrict_countries=True, selected_countries=["US"]),
        sources=[Mixed()],
        client=HttpClient(min_interval=0),
    )
    assert again["status"] == "completed_with_results"
    assert {row["country"] for row in restricted.query_leads()} == {"US", "DE"}
    notes = [row["user_notes"] for row in restricted.query_leads() if row["user_notes"]]
    assert notes == ["beleška ostaje"]
    assert restricted.dashboard()["organizations"] == 2


def test_repeat_search_does_not_duplicate_the_organization(tmp_path: Path):
    from tamigo_intel.db import Database

    db = Database(tmp_path / "t.sqlite")

    class One:
        name = "one"

        def search(self, config, client):
            return [discovery()]

    run_search(db, _config(), sources=[One()], client=HttpClient(min_interval=0))
    run_search(db, _config(), sources=[One()], client=HttpClient(min_interval=0))
    assert db.dashboard()["organizations"] == 1
    assert db.dashboard()["leads"] == 1


def test_missing_key_is_configuration_not_a_transport_failure():
    assert overall_status([{"status": "unavailable"}], 0) == "needs_configuration"
    assert overall_status([{"status": "failed"}, {"status": "unavailable"}], 0) == "failed"


def test_unavailable_source_run_is_needs_configuration(tmp_path: Path):
    from tamigo_intel.db import Database

    db = Database(tmp_path / "t.sqlite")

    class Missing:
        name = "sam_gov"

        def search(self, config, client):
            raise SourceUnavailable("nema ključa")

    result = run_search(db, _config(), sources=[Missing()], client=HttpClient(min_interval=0))
    assert result["status"] == "needs_configuration"
    assert result["sources"][0]["error_kind"] == "configuration"


def test_forbidden_source_is_labeled_separately(tmp_path: Path):
    from tamigo_intel.db import Database

    db = Database(tmp_path / "t.sqlite")

    class Blocked:
        name = "blocked"

        def search(self, config, client):
            raise HttpError("HTTP 403 za https://example.test/csv", status=403)

    result = run_search(db, _config(), sources=[Blocked()], client=HttpClient(min_interval=0))
    assert result["status"] == "failed"
    assert result["sources"][0]["error_kind"] == "forbidden"
    assert "TLS provera" not in result["sources"][0]["error"]


def test_multilingual_terms_stay_off_until_requested():
    plain = _config(keywords=["WCAG"])
    assert query_keywords(plain) == ["WCAG"]
    expanded = query_keywords(_config(keywords=["WCAG"], multilingual=True, search_languages=["de"]))
    assert expanded[0] == "WCAG"
    assert "barrierefreie PDF" in expanded


def test_find_tender_parser_keeps_awards_historical():
    release = {
        "ocid": "ocds-test-1",
        "id": "1-2026",
        "tag": ["tender"],
        "date": "2026-10-01T00:00:00Z",
        "buyer": {"name": "Example Council"},
        "tender": {
            "title": "WCAG 2.2 remediation of public PDFs",
            "description": "PDF accessibility remediation",
            "tenderPeriod": {"endDate": "2099-12-01T00:00:00Z"},
            "value": {"amount": 1000, "currency": "GBP"},
        },
    }
    item = release_to_item(release, ["WCAG"])
    assert item is not None
    assert item.country == "GB"
    assert item.procurement_signal == "open_procurement"
    assert item.source_url.endswith("/Notice/1-2026")
    assert item.amount == 1000
    awarded = dict(release, tag=["award"], ocid="ocds-test-2")
    award = release_to_item(awarded, ["WCAG"])
    assert award is not None
    assert award.procurement_signal == "past_award"
    noise = dict(release, tender={"title": "Snow removal", "description": "Plow the parking lot"})
    assert release_to_item(noise, ["WCAG"]) is None


def test_old_config_keeps_new_fields_at_safe_defaults(tmp_path: Path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"defaults_revision": 2, "recency_days": 120}), encoding="utf-8")
    loaded = load_config(path, MemoryVault())
    assert loaded.recency_days == 120
    assert loaded.restrict_countries is False
    assert loaded.multilingual is False
    assert loaded.selected_countries == ["US", "CA", "GB", "AU"]


def test_classifications_do_not_turn_a_historical_award_into_an_active_opportunity():
    assert evidence_class("A", "past_award") == "historical"
    assert opportunity_status("past_award") == "historical_award"
    assert opportunity_status("open_procurement") == "active"
    assert evidence_class("A", "open_procurement") == "explicit_procurement"


def test_country_controls_are_separate_from_sources(tmp_path: Path):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from tamigo_intel.db import Database
    from tamigo_intel.ui.main_window import MainWindow

    QApplication.instance() or QApplication([])
    window = MainWindow(
        database=Database(tmp_path / "t.sqlite"),
        config=_config(),
        config_file=tmp_path / "config.json",
        backup_directory=tmp_path / "backups",
        vault=MemoryVault(),
    )
    assert window.restrict_countries.isChecked() is False
    assert "US" in window._selected_country_codes()
    assert window.source_boxes["find_tender"].isChecked() is False
    assert window.source_boxes["contracts_finder"].isChecked() is True
    assert window.multilingual.isChecked() is False
    window.apply_country_preset("eu")
    assert "DE" in window._selected_country_codes()
    assert "US" not in window._selected_country_codes()
    window.restrict_countries.setChecked(True)
    window.persist_search_preferences()
    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert saved["restrict_countries"] is True
    assert "DE" in saved["selected_countries"]
    assert saved["sam_api_key"] == ""
    window.close()
