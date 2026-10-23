from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from tamigo_intel.config import SearchConfig, load_config, save_config
from tamigo_intel.db import Database
from tamigo_intel.exporting import export_csv, export_json
from tamigo_intel.legal import hints_for
from tamigo_intel.paths import backup_dir, db_path
from tamigo_intel.pipeline import analyze_path
from tamigo_intel.ui.worker import SearchThread

LEAD_COLUMNS = [
    ("organization", "Ustanova"),
    ("country", "Zemlja"),
    ("website", "Sajt"),
    ("category", "Kategorija"),
    ("formats", "Format"),
    ("evidence_level", "Nivo traga"),
    ("procurement_signal", "Nabavka"),
    ("total_score", "Bodovi"),
    ("verification_status", "Provera"),
    ("status", "Status"),
    ("next_action", "Sledeći korak"),
]


class MainWindow(QMainWindow):
    def __init__(self, database: Database | None = None, config: SearchConfig | None = None) -> None:
        super().__init__()
        self.db = database or Database(db_path())
        self.config = config or load_config()
        self.thread: SearchThread | None = None
        self.current_lead_id: int | None = None
        self.setWindowTitle("Tamigo — obaveštaj o pristupačnosti")
        self.resize(1280, 800)
        tabs = QTabWidget()
        tabs.addTab(self._build_dashboard(), "Pregled")
        tabs.addTab(self._build_search(), "Pretraga")
        tabs.addTab(self._build_leads(), "Lidovi")
        tabs.addTab(self._build_settings(), "Podešavanja")
        self.tabs = tabs
        self.setCentralWidget(tabs)
        self.statusBar().showMessage("Javni tragovi. Nije pravna ocena usklađenosti.")
        self.refresh_dashboard()
        self.reload_leads()

    def _build_dashboard(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.dashboard_labels: dict[str, QLabel] = {}
        grid = QGridLayout()
        names = [
            ("organizations", "Ustanove"),
            ("leads", "Lidovi"),
            ("strong", "Nivo A ili B"),
            ("procurement", "Otvorena nabavka"),
            ("awaiting", "Čeka proveru"),
        ]
        for index, (key, title) in enumerate(names):
            box = QGroupBox(title)
            inner = QVBoxLayout(box)
            label = QLabel("0")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            inner.addWidget(label)
            self.dashboard_labels[key] = label
            grid.addWidget(box, 0, index)
        layout.addLayout(grid)
        self.dashboard_detail = QTextBrowser()
        layout.addWidget(self.dashboard_detail)
        button = QPushButton("Osveži")
        button.clicked.connect(self.refresh_dashboard)
        layout.addWidget(button)
        return page

    def _build_search(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        self.keywords = QPlainTextEdit("\n".join(self.config.keywords))
        self.keywords.setFixedHeight(110)
        self.max_orgs = QSpinBox()
        self.max_orgs.setRange(1, 500)
        self.max_orgs.setValue(self.config.max_organizations)
        self.recency = QSpinBox()
        self.recency.setRange(1, 8000)
        self.recency.setValue(self.config.recency_days)
        self.interval = QSpinBox()
        self.interval.setRange(0, 30)
        self.interval.setValue(int(self.config.request_interval_seconds))
        form.addRow("Ključne reči", self.keywords)
        form.addRow("Najviše ustanova", self.max_orgs)
        form.addRow("Svežina u danima", self.recency)
        form.addRow("Pauza između zahteva (s)", self.interval)
        layout.addLayout(form)
        self.source_boxes: dict[str, QCheckBox] = {}
        row = QHBoxLayout()
        for name, title in (
            ("contracts_finder", "Contracts Finder (UK)"),
            ("usaspending", "USAspending (SAD)"),
            ("ted", "TED (EU)"),
            ("github_issues", "GitHub issues"),
            ("sam_gov", "SAM.gov (traži ključ)"),
        ):
            box = QCheckBox(title)
            box.setChecked(name in self.config.enabled_sources)
            self.source_boxes[name] = box
            row.addWidget(box)
        layout.addLayout(row)
        buttons = QHBoxLayout()
        self.start_button = QPushButton("Pokreni pretragu")
        self.stop_button = QPushButton("Zaustavi")
        self.stop_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_search)
        self.stop_button.clicked.connect(self.stop_search)
        self.saved_name = QLineEdit()
        self.saved_name.setPlaceholderText("Ime sačuvane pretrage")
        save_search = QPushButton("Sačuvaj pretragu")
        save_search.clicked.connect(self.save_current_search)
        self.saved_searches = QComboBox()
        self.reload_saved_searches()
        load_search = QPushButton("Učitaj")
        load_search.clicked.connect(self.load_saved_search)
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.stop_button)
        buttons.addWidget(self.saved_name)
        buttons.addWidget(save_search)
        buttons.addWidget(self.saved_searches)
        buttons.addWidget(load_search)
        layout.addLayout(buttons)
        self.search_log = QPlainTextEdit()
        self.search_log.setReadOnly(True)
        layout.addWidget(self.search_log)
        return page

    def _build_leads(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        filters = QHBoxLayout()
        self.filter_level = QComboBox()
        self.filter_level.addItems(["", "A", "B", "C", "D"])
        self.filter_country = QLineEdit()
        self.filter_country.setPlaceholderText("Zemlja, npr. US")
        self.filter_format = QComboBox()
        self.filter_format.addItems(["", "pdf", "epub", "web"])
        self.filter_procurement = QComboBox()
        self.filter_procurement.addItems(["", "open_procurement", "past_award", "closed", "none"])
        apply_filters = QPushButton("Filtriraj")
        apply_filters.clicked.connect(self.reload_leads)
        filters.addWidget(QLabel("Nivo"))
        filters.addWidget(self.filter_level)
        filters.addWidget(self.filter_country)
        filters.addWidget(self.filter_format)
        filters.addWidget(self.filter_procurement)
        filters.addWidget(apply_filters)
        layout.addLayout(filters)
        splitter = QSplitter(Qt.Orientation.Vertical)
        self.table = QTableWidget(0, len(LEAD_COLUMNS))
        self.table.setHorizontalHeaderLabels([title for _key, title in LEAD_COLUMNS])
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.itemSelectionChanged.connect(self.show_selected_lead)
        splitter.addWidget(self.table)
        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(True)
        detail_layout.addWidget(self.detail)
        operator = QHBoxLayout()
        self.status_box = QComboBox()
        self.status_box.addItems(["new", "reviewing", "qualified", "contacted", "rejected", "archived"])
        self.verification_box = QComboBox()
        self.verification_box.addItems(["unverified_prospect", "manually_verified", "rejected"])
        self.follow_up = QLineEdit()
        self.follow_up.setPlaceholderText("Datum praćenja YYYY-MM-DD")
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText("Beleška")
        self.notes.setFixedHeight(70)
        save = QPushButton("Sačuvaj belešku")
        save.clicked.connect(self.save_operator)
        analyze = QPushButton("Analiziraj fajl")
        analyze.clicked.connect(self.analyze_file)
        export_all = QPushButton("Izvezi CSV")
        export_qualified = QPushButton("Izvezi kvalifikovane JSON")
        export_all.clicked.connect(lambda: self.export("csv", False))
        export_qualified.clicked.connect(lambda: self.export("json", True))
        operator.addWidget(self.status_box)
        operator.addWidget(self.verification_box)
        operator.addWidget(self.follow_up)
        operator.addWidget(save)
        operator.addWidget(analyze)
        operator.addWidget(export_all)
        operator.addWidget(export_qualified)
        detail_layout.addLayout(operator)
        detail_layout.addWidget(self.notes)
        splitter.addWidget(detail)
        layout.addWidget(splitter)
        return page

    def _build_settings(self) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)
        self.priority = QLineEdit(", ".join(self.config.priority_countries))
        self.deprioritized = QLineEdit(", ".join(self.config.deprioritized_countries))
        self.sam_key = QLineEdit(self.config.sam_api_key)
        self.sam_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.github_token = QLineEdit(self.config.github_token)
        self.github_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.excluded = QLineEdit(", ".join(self.config.excluded_names))
        layout.addRow("Prioritetne zemlje", self.priority)
        layout.addRow("Niži prioritet", self.deprioritized)
        layout.addRow("Isključene ustanove", self.excluded)
        layout.addRow("SAM.gov API ključ", self.sam_key)
        layout.addRow("GitHub token", self.github_token)
        save = QPushButton("Sačuvaj podešavanja")
        save.clicked.connect(self.save_settings)
        backup = QPushButton("Napravi rezervnu kopiju baze")
        backup.clicked.connect(self.make_backup)
        layout.addRow(save)
        layout.addRow(backup)
        note = QLabel(
            "Ključevi ostaju u lokalnom config.json i ne ulaze u izvoz lidova. "
            "Zakazana pretraga ne radi kad je program zatvoren."
        )
        note.setWordWrap(True)
        layout.addRow(note)
        return page

    def refresh_dashboard(self) -> None:
        data = self.db.dashboard()
        for key, label in self.dashboard_labels.items():
            label.setText(str(data.get(key, 0)))
        lines = ["Po zemljama:"]
        for row in data["by_country"]:
            lines.append(f"- {row['country'] or 'nije utvrđeno'}: {row['count']}")
        lines.append("Po kategoriji:")
        for row in data["by_category"]:
            lines.append(f"- {row['category']}: {row['count']}")
        lines.append("Izvori:")
        for row in data["sources"]:
            lines.append(f"- {row['source_name']}: {row['last_status']} {row['last_error']}")
        lines.append("Poslednja pokretanja:")
        for row in data["recent_runs"]:
            lines.append(f"- {row['started_at']} {row['status']} {row['error']}")
        self.dashboard_detail.setPlainText("\n".join(lines))

    def current_config_from_form(self) -> SearchConfig:
        config = self.config
        config.keywords = [line.strip() for line in self.keywords.toPlainText().splitlines() if line.strip()]
        config.max_organizations = self.max_orgs.value()
        config.recency_days = self.recency.value()
        config.request_interval_seconds = float(self.interval.value())
        config.enabled_sources = [name for name, box in self.source_boxes.items() if box.isChecked()]
        return config

    def save_current_search(self) -> None:
        name = self.saved_name.text().strip()
        if not name:
            return
        config = self.current_config_from_form()
        self.db.save_search(name, json.dumps(config.to_public_dict(), ensure_ascii=False))
        self.reload_saved_searches()
        self.statusBar().showMessage(f"Pretraga je sačuvana: {name}")

    def reload_saved_searches(self) -> None:
        self.saved_searches.clear()
        for row in self.db.list_saved_searches():
            self.saved_searches.addItem(row["name"], row["id"])

    def load_saved_search(self) -> None:
        search_id = self.saved_searches.currentData()
        if not search_id:
            return
        with self.db.connect() as conn:
            row = conn.execute("SELECT config_json FROM saved_searches WHERE id = ?", (search_id,)).fetchone()
        if row is None:
            return
        data = json.loads(row["config_json"])
        if data.get("keywords"):
            self.keywords.setPlainText("\n".join(data["keywords"]))
        if data.get("max_organizations"):
            self.max_orgs.setValue(int(data["max_organizations"]))
        if data.get("recency_days"):
            self.recency.setValue(int(data["recency_days"]))
        enabled = set(data.get("enabled_sources") or [])
        for name, box in self.source_boxes.items():
            box.setChecked(name in enabled)
        self.statusBar().showMessage("Sačuvana pretraga je učitana. Ključevi nisu u tom zapisu.")

    def start_search(self) -> None:
        if self.thread and self.thread.isRunning():
            return
        config = self.current_config_from_form()
        self.thread = SearchThread(str(self.db.path), config)
        self.thread.progress.connect(self.append_log)
        self.thread.finished_ok.connect(self.search_finished)
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.append_log("Pretraga je pokrenuta.")
        self.thread.start()

    def stop_search(self) -> None:
        if self.thread:
            self.thread.cancel()
            self.append_log("Zaustavljanje je zatraženo.")

    def append_log(self, message: str) -> None:
        self.search_log.appendPlainText(message)

    def search_finished(self, result: dict) -> None:
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.append_log(f"Kraj: {result.get('status')} , ustanove: {result.get('stored')}")
        self.refresh_dashboard()
        self.reload_leads()

    def reload_leads(self) -> None:
        filters = {
            "min_level": self.filter_level.currentText(),
            "country": self.filter_country.text().strip(),
            "format": self.filter_format.currentText(),
            "procurement": self.filter_procurement.currentText(),
        }
        rows = self.db.query_leads(filters)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for row_index, lead in enumerate(rows):
            for column, (key, _title) in enumerate(LEAD_COLUMNS):
                item = QTableWidgetItem(str(lead.get(key) or ""))
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, lead["id"])
                self.table.setItem(row_index, column, item)
        self.table.setSortingEnabled(True)

    def show_selected_lead(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        item = self.table.item(row, 0)
        if item is None:
            return
        lead_id = item.data(Qt.ItemDataRole.UserRole)
        if not lead_id:
            return
        self.current_lead_id = int(lead_id)
        bundle = self.db.lead_bundle(self.current_lead_id)
        if not bundle:
            return
        lead = bundle["lead"]
        parts = [
            f"<h2>{lead['organization']}</h2>",
            f"<p>{lead['country']} · {lead['category'] or 'kategorija nije utvrđena'} "
            f"({lead['category_verification']}) · nivo {lead['evidence_level']} · bodovi {lead['total_score']}</p>",
            "<p><b>Ovo nije ocena neusklađenosti.</b></p>",
            f"<p>{lead['summary'].replace(chr(10), '<br>')}</p>",
            "<h3>Zašto ovi bodovi</h3>",
            f"<pre>{lead['score_explanation']}</pre>",
            "<h3>Dokazi</h3><ul>",
        ]
        for evidence in bundle["evidence"]:
            parts.append(
                f"<li><a href=\"{evidence['source_url']}\">{evidence['title']}</a><br>"
                f"{evidence['excerpt']}<br><i>{evidence['limitations']}</i></li>"
            )
        parts.append("</ul><h3>Kontakti</h3><ul>")
        if not bundle["contacts"]:
            parts.append("<li>Nema javno prepisane adrese.</li>")
        for contact in bundle["contacts"]:
            parts.append(
                f"<li>{contact['email']} — provera: {contact['email_verification']} — "
                f"<a href=\"{contact['source_url']}\">izvor</a></li>"
            )
        parts.append("</ul><h3>Pravni kontekst za ručnu proveru</h3><ul>")
        for hint in hints_for(lead["country"]):
            parts.append(f"<li><a href=\"{hint.source_url}\">{hint.title}</a> — {hint.note} ({hint.applicability})</li>")
        parts.append("</ul><h3>Istorija</h3><ul>")
        for event in bundle["events"]:
            parts.append(f"<li>{event['at']} {event['kind']}: {event['detail']}</li>")
        parts.append("</ul>")
        self.detail.setHtml("".join(parts))
        self.notes.setPlainText(lead.get("user_notes") or "")
        self.follow_up.setText(lead.get("follow_up_on") or "")
        self.status_box.setCurrentText(lead["status"])
        self.verification_box.setCurrentText(lead["verification_status"])

    def save_operator(self) -> None:
        if not self.current_lead_id:
            return
        self.db.update_lead_operator(
            self.current_lead_id,
            self.status_box.currentText(),
            self.notes.toPlainText(),
            self.follow_up.text().strip(),
            self.verification_box.currentText(),
        )
        self.reload_leads()

    def analyze_file(self) -> None:
        if not self.current_lead_id:
            QMessageBox.information(self, "Tamigo", "Prvo izaberite lid.")
            return
        path, _selected = QFileDialog.getOpenFileName(self, "Fajl", "", "Dokumenti (*.pdf *.epub *.html *.htm)")
        if not path:
            return
        bundle = self.db.lead_bundle(self.current_lead_id)
        assert bundle is not None
        result = analyze_path(self.db, bundle["lead"]["organization_id"], Path(path), self.config)
        QMessageBox.information(
            self,
            "Provera",
            f"Indikatora: {len(result.indicators)}. {result.limitations}",
        )
        self.show_selected_lead()

    def export(self, kind: str, qualified_only: bool) -> None:
        suffix = "csv" if kind == "csv" else "json"
        path, _selected = QFileDialog.getSaveFileName(self, "Izvoz", f"lidovi.{suffix}", f"*.{suffix}")
        if not path:
            return
        if kind == "csv":
            count = export_csv(self.db, Path(path), qualified_only=qualified_only)
        else:
            count = export_json(self.db, Path(path), qualified_only=qualified_only)
        self.statusBar().showMessage(f"Izvezeno zapisa: {count}")

    def save_settings(self) -> None:
        self.config.priority_countries = _split(self.priority.text())
        self.config.deprioritized_countries = _split(self.deprioritized.text())
        self.config.excluded_names = _split(self.excluded.text())
        self.config.sam_api_key = self.sam_key.text().strip()
        self.config.github_token = self.github_token.text().strip()
        save_config(self.config)
        self.statusBar().showMessage("Podešavanja su sačuvana lokalno.")

    def make_backup(self) -> None:
        destination = backup_dir() / "tamigo-backup.sqlite"
        self.db.backup_to(destination)
        self.statusBar().showMessage(f"Kopija: {destination}")


def _split(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def dumps_config(config: SearchConfig) -> str:
    return json.dumps(config.to_public_dict(), ensure_ascii=False)
