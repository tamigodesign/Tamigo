from __future__ import annotations

import json
import logging
import os
import ssl
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tamigo_intel.config import (
    DEFAULT_RECENCY_DAYS,
    RECENCY_MAX,
    RECENCY_MIN,
    ConfigError,
    SearchConfig,
    load_config,
    save_config,
    validate_limits,
)
from tamigo_intel.db import Database
from tamigo_intel.exporting import export_csv, export_json
from tamigo_intel.http_client import HttpClient, HttpError
from tamigo_intel.maintenance import DeletionRefused, delete_all_if_confirmed, delete_selected_if_confirmed
from tamigo_intel.pipeline import _store, run_search
from tamigo_intel.sources.base import Discovered
from tamigo_intel.sources.sam_gov import SourceUnavailable
from tamigo_intel.status_text import overall_status
from tamigo_intel.tls import install_ca_bundle, verified_context
from tamigo_intel.vault import KeychainVault, MemoryVault
from tests.test_core import discovery

SECRET = "tamigo-test-secret-9f3a"


def _config(**kwargs) -> SearchConfig:
    base = dict(keywords=["WCAG", "PDF accessibility"], request_interval_seconds=0, max_per_source=10, max_organizations=10)
    base.update(kwargs)
    return SearchConfig(**base)


def _absent(directory: Path, secret: str) -> None:
    raw = secret.encode()
    for path in directory.rglob("*"):
        if path.is_file():
            assert raw not in path.read_bytes(), path


def test_default_lookback_is_90_days():
    config = SearchConfig()
    assert config.recency_days == 90
    assert DEFAULT_RECENCY_DAYS == 90
    assert RECENCY_MIN == 1
    assert RECENCY_MAX == 7300
    validate_limits(config)


def test_lookback_rejects_invalid_numbers_and_keeps_a_chosen_long_window(tmp_path: Path):
    for bad in (-1, 0, 7301, True, False, "90", 90.5, None):
        config = SearchConfig()
        config.recency_days = bad  # type: ignore[assignment]
        with pytest.raises(ConfigError):
            validate_limits(config)
    chosen = SearchConfig(recency_days=1845)
    validate_limits(chosen)
    vault = MemoryVault()
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"recency_days": 1825, "sam_api_key": SECRET}), encoding="utf-8")
    migrated = load_config(path, vault)
    assert migrated.recency_days == 90
    assert migrated.sam_api_key == SECRET
    assert SECRET not in path.read_text(encoding="utf-8")
    assert vault.get("sam_api_key") == SECRET
    migrated.recency_days = 1825
    save_config(migrated, path, vault)
    assert load_config(path, vault).recency_days == 1825
    assert SECRET not in path.read_text(encoding="utf-8")
    legacy = tmp_path / "custom.json"
    legacy.write_text(json.dumps({"recency_days": 1845}), encoding="utf-8")
    assert load_config(legacy, MemoryVault()).recency_days == 1845


def test_refresh_preserves_records_and_adds_findings(tmp_path: Path):
    db = Database(tmp_path / "t.sqlite")
    original = discovery(
        source_record_id="same",
        organization_name="Kept Agency",
        excerpt="WCAG remediation original text",
    )
    updated = discovery(
        source_record_id="same",
        organization_name="Kept Agency",
        excerpt="WCAG remediation updated text",
    )
    added = discovery(
        source_record_id="new",
        organization_name="Added Agency",
        excerpt="PDF accessibility remediation for the library",
    )

    class Batch:
        name = "batch"

        def __init__(self, items):
            self.items = items

        def search(self, config, client):
            return list(self.items)

    first = run_search(db, _config(), sources=[Batch([original])], client=HttpClient(min_interval=0))
    assert first["status"] == "completed_with_results"
    lead_id = db.query_leads()[0]["id"]
    db.update_lead_operator(lead_id, "reviewing", "ostaje posle osvežavanja", "2026-12-01", "manually_verified")
    second = run_search(db, _config(), sources=[Batch([updated, added])], client=HttpClient(min_interval=0))
    assert second["status"] == "completed_with_results"
    names = {row["organization"] for row in db.query_leads()}
    assert names == {"Kept Agency", "Added Agency"}
    bundle = db.lead_bundle(lead_id)
    assert bundle["lead"]["user_notes"] == "ostaje posle osvežavanja"
    assert bundle["lead"]["verification_status"] == "manually_verified"
    with db.connect() as conn:
        history = [row["excerpt"] for row in conn.execute("SELECT excerpt FROM evidence_history")]
        runs = conn.execute("SELECT COUNT(*) FROM search_runs").fetchone()[0]
    assert any("original text" in excerpt for excerpt in history)
    assert runs == 2


def test_clearing_the_view_does_not_delete_rows(tmp_path: Path):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from tamigo_intel.ui.main_window import MainWindow

    QApplication.instance() or QApplication([])
    db = Database(tmp_path / "t.sqlite")
    with db.connect() as conn:
        _store(db, conn, discovery(), _config())
        conn.commit()
    window = MainWindow(database=db, config=_config(), backup_directory=tmp_path / "backups")
    assert window.table.rowCount() == 1
    assert window.dashboard_labels["leads"].text() == "1"
    window.clear_current_view()
    assert window.table.rowCount() == 0
    assert window.view_suppressed is True
    assert db.dashboard()["leads"] == 1
    assert window.dashboard_labels["leads"].text() == "1"
    window.apply_filters()
    assert window.table.rowCount() == 1
    window.close()


def test_explicit_deletion_requires_confirmation(tmp_path: Path):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QMessageBox

    from tamigo_intel.ui.main_window import MainWindow

    QApplication.instance() or QApplication([])
    db = Database(tmp_path / "t.sqlite")
    with db.connect() as conn:
        _store(db, conn, discovery(source_record_id="one", organization_name="First Agency"), _config())
        _store(db, conn, discovery(source_record_id="two", organization_name="Second Agency"), _config())
        conn.commit()
    db.save_search("ostaje", '{"keywords": ["WCAG"]}')
    with pytest.raises(DeletionRefused):
        delete_selected_if_confirmed(db, [1], False, tmp_path / "backups")
    with pytest.raises(DeletionRefused):
        delete_all_if_confirmed(db, False, tmp_path / "backups")
    assert db.dashboard()["leads"] == 2

    window = MainWindow(database=db, config=_config(), backup_directory=tmp_path / "backups")
    window.table.selectRow(0)
    answers = iter(
        [
            QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        ]
    )
    prompts: list[tuple] = []

    def question(*args, **_kwargs):
        prompts.append(args)
        return next(answers)

    monkey = pytest.MonkeyPatch()
    monkey.setattr(QMessageBox, "question", question)
    try:
        window.delete_selected()
        assert db.dashboard()["leads"] == 2
        assert not list((tmp_path / "backups").glob("pre-brisanja-*.sqlite"))
        window.table.selectRow(0)
        window.delete_selected()
        assert db.dashboard()["leads"] == 1
        assert list((tmp_path / "backups").glob("pre-brisanja-*.sqlite"))
        window.delete_all_research()
        assert db.dashboard()["leads"] == 1
        window.delete_all_research()
    finally:
        monkey.undo()
    assert prompts[0][-1] == QMessageBox.StandardButton.No
    assert "nije čišćenje prikaza" in prompts[0][2]
    assert "rezervna kopija" in prompts[2][2].lower()
    assert db.dashboard()["organizations"] == 0
    assert db.list_saved_searches()[0]["name"] == "ostaje"
    assert list((tmp_path / "backups").glob("pre-brisanja-*.sqlite"))
    window.close()


def test_credentials_stay_out_of_files_logs_and_exports(tmp_path: Path, caplog):
    caplog.set_level(logging.INFO, logger="tamigo_intel")
    vault = MemoryVault()
    config = _config(sam_api_key=SECRET)
    path = tmp_path / "config.json"
    save_config(config, path, vault)
    assert vault.get("sam_api_key") == SECRET
    assert SECRET not in path.read_text(encoding="utf-8")
    assert SECRET not in json.dumps(config.to_public_dict())
    db = Database(tmp_path / "t.sqlite")

    class Leaky:
        name = "leaky"

        def search(self, config, client):
            raise OSError(f"api_key={config.sam_api_key} rejected")

    result = run_search(db, config, sources=[Leaky()], client=HttpClient(min_interval=0, secrets=[SECRET]))
    assert result["status"] == "failed"
    assert SECRET not in "\n".join(result["log"])
    assert SECRET not in caplog.text
    with db.connect() as conn:
        _store(db, conn, discovery(), config)
        conn.commit()
    export_json(db, tmp_path / "out.json")
    export_csv(db, tmp_path / "out.csv")
    _absent(tmp_path, SECRET)

    stored: dict[tuple[str, str], str] = {}

    class FakeKeyring:
        class errors:
            class PasswordDeleteError(Exception):
                pass

        @staticmethod
        def set_password(service, name, value):
            stored[(service, name)] = value

        @staticmethod
        def get_password(service, name):
            return stored.get((service, name))

        @staticmethod
        def delete_password(service, name):
            stored.pop((service, name), None)

    monkey = pytest.MonkeyPatch()
    monkey.setitem(sys.modules, "keyring", FakeKeyring)
    try:
        chain = KeychainVault()
        chain.set("sam_api_key", SECRET)
        assert chain.get("sam_api_key") == SECRET
        assert chain.configured("sam_api_key") is True
        chain.set("sam_api_key", "")
        assert chain.get("sam_api_key") == ""
    finally:
        monkey.undo()
    assert SECRET not in json.dumps(stored)


def test_failed_source_is_not_a_successful_search(tmp_path: Path):
    db = Database(tmp_path / "t.sqlite")
    with db.connect() as conn:
        _store(db, conn, discovery(), _config())
        conn.commit()
    db.update_lead_operator(1, "reviewing", "beleška ostaje", "2026-12-01", "unverified_prospect")

    class Bad:
        name = "bad"

        def search(self, config, client):
            raise OSError("CERTIFICATE_VERIFY_FAILED")

    result = run_search(db, _config(), sources=[Bad()], client=HttpClient(min_interval=0))
    assert result["status"] == "failed"
    assert result["sources"][0]["status"] == "failed"
    assert result["sources"][0]["count"] == 0
    assert result["status"] not in {"completed", "completed_with_results", "completed_empty", "partial"}
    assert db.dashboard()["leads"] == 1
    assert db.lead_bundle(1)["lead"]["user_notes"] == "beleška ostaje"


def test_all_sources_failing_is_failed(tmp_path: Path):
    db = Database(tmp_path / "t.sqlite")

    class Bad:
        def __init__(self, name):
            self.name = name

        def search(self, config, client):
            raise HttpError("TLS", status=None)

    class Missing:
        name = "sam_gov"

        def search(self, config, client):
            raise SourceUnavailable("nema ključa")

    result = run_search(
        db,
        _config(),
        sources=[Bad("one"), Missing(), Bad("two")],
        client=HttpClient(min_interval=0),
    )
    assert result["status"] == "failed"
    assert [item["status"] for item in result["sources"]] == ["failed", "unavailable", "failed"]
    assert all(item["status"] != "ok" for item in result["sources"])
    assert db.dashboard()["organizations"] == 0
    assert overall_status(result["sources"], 0) == "failed"


def test_partial_success_names_the_failed_source(tmp_path: Path):
    db = Database(tmp_path / "t.sqlite")

    class Good:
        name = "good"

        def search(self, config, client):
            return [discovery(organization_name="Good Agency", source_record_id="good-1")]

    class Bad:
        name = "bad"

        def search(self, config, client):
            raise HttpError("mreža", status=503)

    class Empty:
        name = "empty"

        def search(self, config, client):
            return []

    mixed = run_search(db, _config(), sources=[Good(), Bad()], client=HttpClient(min_interval=0))
    assert mixed["status"] == "partial"
    by_name = {item["name"]: item for item in mixed["sources"]}
    assert by_name["good"]["status"] == "ok"
    assert by_name["good"]["count"] == 1
    assert by_name["bad"]["status"] == "failed"
    assert by_name["bad"]["count"] == 0
    assert db.dashboard()["leads"] == 1

    empty = run_search(db, _config(), sources=[Empty()], client=HttpClient(min_interval=0))
    assert empty["status"] == "completed_empty"
    assert empty["sources"][0]["status"] == "ok"
    assert empty["sources"][0]["count"] == 0
    assert db.dashboard()["leads"] == 1


def test_notes_and_evidence_history_survive_restart(tmp_path: Path):
    path = tmp_path / "t.sqlite"
    first = Database(path)
    with first.connect() as conn:
        _store(
            first,
            conn,
            discovery(source_record_id="hist", excerpt="WCAG remediation original text"),
            _config(),
        )
        conn.commit()
    first.update_lead_operator(1, "reviewing", "beleška preživljava", "2026-12-01", "unverified_prospect")
    with first.connect() as conn:
        _store(
            first,
            conn,
            discovery(source_record_id="hist", excerpt="WCAG remediation updated text"),
            _config(),
        )
        conn.commit()
    del first
    second = Database(path)
    bundle = second.lead_bundle(1)
    assert bundle["lead"]["user_notes"] == "beleška preživljava"
    assert bundle["lead"]["status"] == "reviewing"
    with second.connect() as conn:
        history = [row["excerpt"] for row in conn.execute("SELECT excerpt FROM evidence_history")]
    assert any("original text" in excerpt for excerpt in history)
    assert bundle["evidence"][0]["excerpt"] == "WCAG remediation updated text"


def test_tls_verification_stays_enabled():
    install_ca_bundle()
    context = verified_context()
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    root = Path(__file__).resolve().parents[1] / "tamigo_intel"
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "CERT_NONE" not in text
        assert "check_hostname = False" not in text


def test_window_documents_lookback_and_keeps_secrets_out_of_fields(tmp_path: Path):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QMessageBox

    from tamigo_intel.ui.main_window import MainWindow

    QApplication.instance() or QApplication([])
    vault = MemoryVault()
    vault.set("sam_api_key", SECRET)
    config = _config(sam_api_key=SECRET)
    db = Database(tmp_path / "t.sqlite")
    window = MainWindow(
        database=db,
        config=config,
        config_file=tmp_path / "config.json",
        backup_directory=tmp_path / "backups",
        vault=vault,
    )
    assert window.recency.value() == 90
    assert window.recency.minimum() == RECENCY_MIN
    assert window.recency.maximum() == RECENCY_MAX
    assert "90" in window.recency_hint.text()
    assert str(RECENCY_MAX) in window.recency_hint.text()
    assert window.refresh_button.text() == "Osveži / ponovi pretragu"
    assert window.clear_button.text() == "Očisti trenutni prikaz"
    assert window.dashboard_refresh_button.text() == "Ažuriraj brojače"
    assert window.settings_button.text() == "Podešavanja i API ključevi"
    editor = window.credential_editors["sam_api_key"]
    assert editor.text() == ""
    assert editor.echoMode() == editor.EchoMode.Password
    assert SECRET not in window.credential_state["sam_gov"].text()
    assert "Ključ je sačuvan." in window.credential_state["sam_gov"].text()
    window.save_settings()
    assert vault.get("sam_api_key") == SECRET
    assert SECRET not in (tmp_path / "config.json").read_text(encoding="utf-8")
    warnings: list = []

    def warning(*args):
        warnings.append(args)
        return QMessageBox.StandardButton.Ok

    monkey = pytest.MonkeyPatch()
    monkey.setattr(QMessageBox, "warning", warning)
    try:
        assert window._assign_int_spin(window.recency, -5, "Period unazad") is False
        assert window.recency.value() == 90
        assert window._assign_int_spin(window.recency, 1845, "Period unazad") is True
        assert window.recency.value() == 1845
        assert window._assign_int_spin(window.recency, True, "Period unazad") is False
        assert window.recency.value() == 1845
    finally:
        monkey.undo()
    assert warnings
    window.recency.setValue(90)
    window.close()
