from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tamigo_intel.http_client import HttpClient
from tamigo_intel.pipeline import run_search
from tamigo_intel.sources.boamp import query_terms, record_to_item
from tamigo_intel.status_text import overall_status
from tamigo_intel.terms import procurement_level
from tests.test_expansion import _config


NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)


def _row(**kwargs):
    base = {
        "idweb": "26-100789",
        "objet": "Schémas directeurs d'accessibilité numérique et audits de sites",
        "nomacheteur": "Groupement Versailles",
        "titulaire": "Agence exemple",
        "dateparution": "2026-10-16",
        "nature": "APPEL_OFFRE",
        "etat": "INITIAL",
        "url_avis": "https://www.boamp.fr/pages/avis/?q=idweb:26-100789",
        "datelimitereponse": "2026-11-12T12:00:00+00:00",
        "descripteur_libelle": ["Informatique (prestations de services)"],
    }
    base.update(kwargs)
    return base


def test_boamp_open_notice_stays_open_and_award_stays_historical():
    item = record_to_item(_row(), ["accessibilité numérique"], NOW)
    assert item is not None
    assert item.country == "FR"
    assert item.organization_name == "Groupement Versailles"
    assert item.supplier_name == "Agence exemple"
    assert item.procurement_signal == "open_procurement"
    assert item.level == "A"
    assert item.source_url.startswith("https://www.boamp.fr/")
    assert item.amount is None
    award = record_to_item(_row(idweb="26-2", nature="ATTRIBUTION", datelimitereponse=None), ["RGAA"], NOW)
    assert award is not None
    assert award.procurement_signal == "past_award"
    assert award.organization_name == "Groupement Versailles"


def test_boamp_past_deadline_is_closed_and_building_access_is_dropped():
    closed = record_to_item(_row(datelimitereponse="2020-01-01T00:00:00+00:00"), ["accessibilité numérique"], NOW)
    assert closed is not None
    assert closed.procurement_signal == "closed"
    building = record_to_item(
        _row(objet="Mise en accessibilité des escaliers du musée", descripteur_libelle=[]),
        ["accessibilité numérique"],
        NOW,
    )
    assert building is None
    assert procurement_level("Mise en accessibilité des escaliers", "") == "D"


def test_boamp_query_uses_at_most_four_terms():
    terms = query_terms(["WCAG", "RGAA", "a", "accessibilité numérique", "documents accessibles", "audit d'accessibilité"])
    assert terms[0] == "WCAG"
    assert len(terms) == 4
    assert "a" not in terms


def test_country_bound_source_is_not_called_outside_the_filter(tmp_path: Path):
    from tamigo_intel.db import Database

    db = Database(tmp_path / "t.sqlite")

    class FranceOnly:
        name = "boamp"
        countries = ("FR",)
        called = False

        def search(self, config, client):
            self.called = True
            return []

    source = FranceOnly()
    result = run_search(
        db,
        _config(restrict_countries=True, selected_countries=["US"], enabled_sources=["boamp"]),
        sources=[source],
        client=HttpClient(min_interval=0),
    )
    assert source.called is False
    assert result["sources"][0]["status"] == "skipped"
    assert result["status"] == "completed_empty"
    assert overall_status([{"status": "ok"}, {"status": "skipped"}], 1) == "completed_with_results"
    assert overall_status([{"status": "failed"}, {"status": "skipped"}], 0) == "failed"


def test_search_tab_shows_countries_before_sources(tmp_path: Path):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from tamigo_intel.countries import COUNTRIES
    from tamigo_intel.db import Database
    from tamigo_intel.ui.main_window import MainWindow
    from tamigo_intel.vault import MemoryVault

    app = QApplication.instance() or QApplication([])
    window = MainWindow(
        database=Database(tmp_path / "t.sqlite"),
        config=_config(),
        config_file=tmp_path / "config.json",
        backup_directory=tmp_path / "backups",
        vault=MemoryVault(),
    )
    window.resize(1280, 800)
    window.show()
    app.processEvents()
    assert window.search_page.isAncestorOf(window.country_box)
    assert window.search_controls.layout().itemAt(0).widget() is window.country_box
    assert window.country_summary.text().startswith("Filter zemlje je ISKLJUČEN")
    assert window.source_boxes["boamp"].isChecked() is False
    assert window.source_boxes["contracts_finder"].isChecked() is True
    assert window.planned_boxes["tenderned"].isEnabled() is False
    assert "nije još ugrađeno" in window.planned_boxes["tenderned"].text()
    window.select_all_countries()
    assert len(window._selected_country_codes()) == len(COUNTRIES)
    window.clear_country_selection()
    assert window._selected_country_codes() == []
    window._set_source_group(["contracts_finder", "tenderned", "boamp"], True)
    assert window.source_boxes["boamp"].isChecked() is True
    assert window.planned_boxes["tenderned"].isChecked() is False
    top = window.country_box.mapTo(window.search_scroll.viewport(), window.country_box.rect().topLeft())
    assert top.y() < window.search_scroll.viewport().height()
    window.close()
