from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from tamigo_intel.config import SearchConfig
from tamigo_intel.db import Database
from tamigo_intel.pipeline import _store
from tamigo_intel.sources.base import Discovered
from tamigo_intel.ui.main_window import MainWindow


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    return app


def test_window_lists_real_lead(qapp, tmp_path: Path):
    db = Database(tmp_path / "ui.sqlite")
    config = SearchConfig(keywords=["WCAG"], request_interval_seconds=0)
    item = Discovered(
        source_name="fixture",
        source_record_id="ui-1",
        source_url="https://example.test/ui",
        organization_name="Public Library Board",
        country="CA",
        title="EPUB accessibility remediation",
        excerpt="Request for EPUB accessibility and WCAG support.",
        explanation="Test.",
        limitations="Nije nalaz o kvaru.",
        level="A",
        kind="procurement_notice",
        procurement_signal="open_procurement",
        published_at="2026-04-01",
    )
    with db.connect() as conn:
        _store(db, conn, item, config)
        conn.commit()
    window = MainWindow(database=db, config=config)
    window.refresh_dashboard()
    window.reload_leads()
    assert window.dashboard_labels["leads"].text() == "1"
    assert window.table.rowCount() == 1
    assert window.table.item(0, 0).text() == "Public Library Board"
    window.table.selectRow(0)
    window.show_selected_lead()
    assert "Ovo nije ocena neusklađenosti" in window.detail.toHtml()
    assert "https://example.test/ui" in window.detail.toHtml()
    window.close()
