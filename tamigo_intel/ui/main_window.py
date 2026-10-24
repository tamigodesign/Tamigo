from __future__ import annotations

import json
import sys
from dataclasses import replace
from datetime import datetime, timezone
from functools import partial
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
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
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from tamigo_intel.config import (
    DEFAULT_RECENCY_DAYS,
    INTERVAL_MAX,
    INTERVAL_MIN,
    MAX_ORGS_MAX,
    MAX_ORGS_MIN,
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
from tamigo_intel.legal import hints_for
from tamigo_intel.maintenance import DELETE_ALL_TEXT, DELETE_SELECTED_TEXT, DeletionRefused, delete_all_if_confirmed, delete_selected_if_confirmed
from tamigo_intel.paths import backup_dir, db_path
from tamigo_intel.pipeline import analyze_path
from tamigo_intel.redact import redact
from tamigo_intel.sources.catalog import SOURCE_CATALOG, auth_label, catalog_by_name, test_connection
from tamigo_intel.status_text import outcome_label
from tamigo_intel.terms import PROCUREMENT_LABELS, procurement_label
from tamigo_intel.ui.worker import SearchThread
from tamigo_intel.vault import SECRET_FIELDS

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


class ConnectionProbe(QThread):
    finished_probe = Signal(str, str, str)

    def __init__(self, name: str, config: SearchConfig) -> None:
        super().__init__()
        self.name = name
        self.config = config

    def run(self) -> None:
        from tamigo_intel.http_client import HttpClient

        secrets = [value for value in (self.config.sam_api_key, self.config.github_token, self.config.openai_api_key) if value]
        client = HttpClient(min_interval=0, timeout=20, secrets=secrets)
        try:
            status, message = test_connection(self.name, self.config, client)
        except Exception as exc:
            status, message = "failed", redact(str(exc), secrets)
        self.finished_probe.emit(self.name, status, message)


class MainWindow(QMainWindow):
    def __init__(
        self,
        database: Database | None = None,
        config: SearchConfig | None = None,
        config_file: Path | None = None,
        backup_directory: Path | None = None,
        vault=None,
    ) -> None:
        super().__init__()
        self.db = database or Database(db_path())
        self.config = config or load_config()
        self.config_file = config_file
        self.backup_directory = backup_directory
        self.vault = vault
        self.thread: SearchThread | None = None
        self._probes: dict[str, ConnectionProbe] = {}
        self.current_lead_id: int | None = None
        self.view_suppressed = False
        self.credential_editors: dict[str, QLineEdit] = {}
        self.credential_state: dict[str, QLabel] = {}
        self.probe_state: dict[str, QLabel] = {}
        self.credential_clears: set[str] = set()
        self.setWindowTitle("Tamigo — obaveštaj o pristupačnosti")
        self.resize(1280, 800)
        tabs = QTabWidget()
        self.dashboard_page = self._build_dashboard()
        self.search_page = self._build_search()
        self.leads_page = self._build_leads()
        self.settings_page = self._build_settings()
        tabs.addTab(self.dashboard_page, "Pregled")
        tabs.addTab(self.search_page, "Pretraga")
        tabs.addTab(self.leads_page, "Lidovi")
        tabs.addTab(self.settings_page, "Podešavanja")
        self.tabs = tabs
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.addLayout(self._build_actions())
        outer.addWidget(tabs)
        self.setCentralWidget(root)
        self.statusBar().showMessage("Javni tragovi. Nije pravna ocena usklađenosti.")
        self.refresh_dashboard()
        self.refresh_run_status()
        self.reload_leads()
        self.refresh_source_table_from_db()

    def _build_actions(self) -> QVBoxLayout:
        layout = QVBoxLayout()
        row = QHBoxLayout()
        self.start_button = QPushButton("Pokreni pretragu")
        self.start_button.setToolTip("Pokreće pretragu na uključenim izvorima i dopunjuje postojeće zapise.")
        self.refresh_button = QPushButton("Osveži / ponovi pretragu")
        self.refresh_button.setToolTip(
            "Ponovo pita uključene izvore i dopunjuje postojeće zapise. "
            "Ne briše ustanove, lidove, dokaze, beleške ni istoriju pretrage."
        )
        self.stop_button = QPushButton("Zaustavi pretragu")
        self.stop_button.setToolTip("Prekida tekuću pretragu. Već sačuvani zapisi ostaju.")
        self.stop_button.setEnabled(False)
        self.clear_button = QPushButton("Očisti trenutni prikaz")
        self.clear_button.setToolTip("Skida redove sa ekrana. Baza se ne dira.")
        self.saved_button = QPushButton("Sačuvane pretrage")
        self.saved_button.setToolTip("Otvara sačuvane pretrage. U njima nema API ključeva.")
        self.settings_button = QPushButton("Podešavanja i API ključevi")
        self.settings_button.setToolTip("Izvori, ključevi i proba veze. Lozinka naloga se ne traži.")
        self.export_button = QPushButton("Izvezi rezultate")
        self.export_button.setToolTip("Izvoz CSV. Ključevi se ne upisuju u fajl.")
        self.start_button.clicked.connect(self.start_search)
        self.refresh_button.clicked.connect(self.refresh_search)
        self.stop_button.clicked.connect(self.stop_search)
        self.clear_button.clicked.connect(self.clear_current_view)
        self.saved_button.clicked.connect(self.show_saved_searches)
        self.settings_button.clicked.connect(self.show_settings)
        self.export_button.clicked.connect(lambda: self.export("csv", False))
        for button in (
            self.start_button,
            self.refresh_button,
            self.stop_button,
            self.clear_button,
            self.saved_button,
            self.settings_button,
            self.export_button,
        ):
            row.addWidget(button)
        layout.addLayout(row)
        self.last_success = QLabel("Poslednji put kad je bar jedan izvor odgovorio: nema.")
        self.latest_outcome = QLabel("Poslednji ishod: pretraga još nije pokretana.")
        self.last_success.setWordWrap(True)
        self.latest_outcome.setWordWrap(True)
        layout.addWidget(self.last_success)
        layout.addWidget(self.latest_outcome)
        return layout

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
        self.dashboard_refresh_button = QPushButton("Ažuriraj brojače")
        self.dashboard_refresh_button.setToolTip("Ponovo čita brojeve iz baze. Ne pokreće pretragu i ne briše zapise.")
        self.dashboard_refresh_button.clicked.connect(self.refresh_dashboard)
        layout.addWidget(self.dashboard_refresh_button)
        return page

    def _build_search(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        self.keywords = QPlainTextEdit("\n".join(self.config.keywords))
        self.keywords.setFixedHeight(110)
        self.keywords.setToolTip("Jedna ključna reč po redu. Generička reč accessibility sama ne pravi lid.")
        self.max_orgs = QSpinBox()
        self.max_orgs.setRange(MAX_ORGS_MIN, MAX_ORGS_MAX)
        self.max_orgs.setToolTip(f"Ceo broj od {MAX_ORGS_MIN} do {MAX_ORGS_MAX}.")
        self._assign_int_spin(self.max_orgs, self.config.max_organizations, "Najviše ustanova", notify=False)
        self.recency = QSpinBox()
        self.recency.setRange(RECENCY_MIN, RECENCY_MAX)
        self.recency.setToolTip(
            f"Podrazumevano {DEFAULT_RECENCY_DAYS} dana. Dozvoljeno je od {RECENCY_MIN} do {RECENCY_MAX}. "
            "Veći broj uključuje starije oglase. Sačuvani zapisi se ne brišu kad se broj smanji."
        )
        self._assign_int_spin(self.recency, self.config.recency_days, "Period unazad", notify=False)
        self.interval = QSpinBox()
        self.interval.setRange(INTERVAL_MIN, INTERVAL_MAX)
        self.interval.setToolTip(f"Pauza u sekundama, od {INTERVAL_MIN} do {INTERVAL_MAX}.")
        interval_raw = self.config.request_interval_seconds
        if isinstance(interval_raw, bool) or not isinstance(interval_raw, (int, float)):
            interval_value = INTERVAL_MIN
        else:
            interval_value = int(interval_raw)
        self._assign_int_spin(self.interval, interval_value, "Pauza između zahteva", notify=False)
        self.recency_hint = QLabel(
            f"Podrazumevano {DEFAULT_RECENCY_DAYS} dana. Najmanje {RECENCY_MIN}, najviše {RECENCY_MAX}. "
            "Duži period ostaje dostupan. Stariji sačuvani zapisi ostaju i kad je period kraći."
        )
        self.recency_hint.setWordWrap(True)
        form.addRow("Ključne reči", self.keywords)
        form.addRow(f"Najviše ustanova ({MAX_ORGS_MIN}–{MAX_ORGS_MAX})", self.max_orgs)
        form.addRow(f"Period unazad, dani ({RECENCY_MIN}–{RECENCY_MAX})", self.recency)
        form.addRow("", self.recency_hint)
        form.addRow(f"Pauza između zahteva, sekunde ({INTERVAL_MIN}–{INTERVAL_MAX})", self.interval)
        layout.addLayout(form)
        self.source_boxes: dict[str, QCheckBox] = {}
        source_grid = QGridLayout()
        for index, (name, title) in enumerate(
            (
                ("contracts_finder", "Contracts Finder (UK)"),
                ("usaspending", "USAspending (SAD)"),
                ("canada_buys", "CanadaBuys (Kanada)"),
                ("ted", "TED (EU)"),
                ("github_issues", "GitHub issues"),
                ("sam_gov", "SAM.gov (traži ključ)"),
            )
        ):
            box = QCheckBox(title)
            box.setChecked(name in self.config.enabled_sources)
            self.source_boxes[name] = box
            source_grid.addWidget(box, index // 3, index % 3)
        layout.addLayout(source_grid)
        buttons = QHBoxLayout()
        self.saved_name = QLineEdit()
        self.saved_name.setPlaceholderText("Ime sačuvane pretrage")
        save_search = QPushButton("Sačuvaj pretragu")
        save_search.clicked.connect(self.save_current_search)
        self.saved_searches = QComboBox()
        self.reload_saved_searches()
        load_search = QPushButton("Učitaj")
        load_search.clicked.connect(self.load_saved_search)
        buttons.addWidget(self.saved_name)
        buttons.addWidget(save_search)
        buttons.addWidget(self.saved_searches)
        buttons.addWidget(load_search)
        layout.addLayout(buttons)
        self.source_table = QTableWidget(0, 4)
        self.source_table.setHorizontalHeaderLabels(["Izvor", "Ishod", "Odgovor", "Detalj"])
        self.source_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.source_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.source_table)
        self.search_log = QPlainTextEdit()
        self.search_log.setReadOnly(True)
        self.search_log.setPlaceholderText("Ishod pretrage i greška po izvoru pojavljuju se ovde.")
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
        self.filter_procurement.addItem("Sve nabavke", "")
        for key, label in PROCUREMENT_LABELS.items():
            self.filter_procurement.addItem(label, key)
        apply_filters = QPushButton("Filtriraj")
        apply_filters.setToolTip("Ponovo prikazuje redove iz baze. Ne briše zapise.")
        apply_filters.clicked.connect(self.apply_filters)
        filters.addWidget(QLabel("Nivo"))
        filters.addWidget(self.filter_level)
        filters.addWidget(self.filter_country)
        filters.addWidget(self.filter_format)
        filters.addWidget(self.filter_procurement)
        filters.addWidget(apply_filters)
        layout.addLayout(filters)
        deletion = QGroupBox("Brisanje zapisa")
        deletion_row = QHBoxLayout(deletion)
        self.delete_selected_button = QPushButton("Obriši izabrane zapise")
        self.delete_selected_button.setToolTip("Briše samo izabrane lidove iz baze, posle potvrde i rezervne kopije.")
        self.delete_all_button = QPushButton("Obriši sve lokalne istraživačke podatke")
        self.delete_all_button.setToolTip(
            "Briše ustanove, lidove, dokaze, beleške i istoriju pretrage. Traži potvrdu. Pravi rezervnu kopiju."
        )
        self.delete_selected_button.clicked.connect(self.delete_selected)
        self.delete_all_button.clicked.connect(self.delete_all_research)
        deletion_row.addWidget(self.delete_selected_button)
        deletion_row.addWidget(self.delete_all_button)
        note = QLabel("Ova dugmad brišu sačuvane zapise. Očisti trenutni prikaz samo skida redove sa ekrana.")
        note.setWordWrap(True)
        deletion_row.addWidget(note)
        layout.addWidget(deletion)
        splitter = QSplitter(Qt.Orientation.Vertical)
        self.table = QTableWidget(0, len(LEAD_COLUMNS))
        self.table.setHorizontalHeaderLabels([title for _key, title in LEAD_COLUMNS])
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
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
        outer = QVBoxLayout(page)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        form = QFormLayout()
        self.priority = QLineEdit(", ".join(self.config.priority_countries))
        self.deprioritized = QLineEdit(", ".join(self.config.deprioritized_countries))
        self.excluded = QLineEdit(", ".join(self.config.excluded_names))
        form.addRow("Prioritetne zemlje", self.priority)
        form.addRow("Niži prioritet", self.deprioritized)
        form.addRow("Isključene ustanove", self.excluded)
        layout.addLayout(form)
        if sys.platform == "darwin":
            store_note = "Ključevi se čuvaju u macOS Keychain-u. Ne upisuju se u config.json, dnevnik ni izvoz."
        else:
            store_note = (
                "Na macOS ključevi idu u Keychain. Van macOS-a ostaju samo u memoriji ovog procesa "
                "i ne upisuju se u config.json, dnevnik ni izvoz."
            )
        intro = QLabel(store_note + " Lozinka naloga se ne traži. Prazno polje ne briše sačuvani ključ.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        for info in SOURCE_CATALOG:
            box = QGroupBox(info["title"])
            box_layout = QVBoxLayout(box)
            box_layout.addWidget(QLabel(f"Prijava: {auth_label(info['auth'])}"))
            state = QLabel("")
            state.setWordWrap(True)
            self.credential_state[info["name"]] = state
            box_layout.addWidget(state)
            if info["credential"]:
                editor = QLineEdit()
                editor.setEchoMode(QLineEdit.EchoMode.Password)
                editor.setPlaceholderText("Novi ključ. Prazno polje ne briše sačuvani.")
                editor.setToolTip("Vrednost se ne prikazuje ponovo i ne ulazi u izvoz ni u dnevnik.")
                self.credential_editors[info["credential"]] = editor
                box_layout.addWidget(QLabel(info["credential_label"]))
                box_layout.addWidget(editor)
                remove = QPushButton(f"Ukloni sačuvani ključ — {info['title']}")
                remove.clicked.connect(partial(self.remove_credential, info["credential"]))
                box_layout.addWidget(remove)
            probe = QLabel("Proba veze još nije pokrenuta.")
            probe.setWordWrap(True)
            self.probe_state[info["name"]] = probe
            box_layout.addWidget(probe)
            test_button = QPushButton(f"Proveri vezu — {info['title']}")
            test_button.setToolTip("Šalje kratak zahtev. Provera sertifikata ostaje uključena.")
            test_button.clicked.connect(partial(self.test_source_connection, info["name"]))
            box_layout.addWidget(test_button)
            box_layout.addWidget(_link_label("Gde se dobija pristup", info["signup_url"]))
            box_layout.addWidget(_link_label("Zvanična dokumentacija", info["docs_url"]))
            instructions = QLabel(info["instructions"])
            instructions.setWordWrap(True)
            limits = QLabel(info["limits"])
            limits.setWordWrap(True)
            box_layout.addWidget(instructions)
            box_layout.addWidget(limits)
            layout.addWidget(box)
        save = QPushButton("Sačuvaj podešavanja")
        save.clicked.connect(self.save_settings)
        backup = QPushButton("Napravi rezervnu kopiju baze")
        backup.clicked.connect(self.make_backup)
        layout.addWidget(save)
        layout.addWidget(backup)
        schedule = QLabel("Zakazana pretraga ne radi kad je program zatvoren.")
        schedule.setWordWrap(True)
        layout.addWidget(schedule)
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        self._refresh_credential_labels()
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
            lines.append(
                f"- {row['source_name']}: {row['last_status']}, odgovor {row.get('last_result_count') or 0}. {row['last_error']}"
            )
        lines.append("Poslednja pokretanja:")
        for row in data["recent_runs"]:
            lines.append(f"- {row['started_at']} {outcome_label(row['status'])}")
        self.dashboard_detail.setPlainText("\n".join(lines))
        if hasattr(self, "latest_outcome"):
            self.refresh_run_status()

    def refresh_run_status(self) -> None:
        latest = self.db.latest_run()
        success = self.db.latest_successful_run()
        if latest:
            self.latest_outcome.setText("Poslednji ishod: " + outcome_label(latest["status"]))
        else:
            self.latest_outcome.setText("Poslednji ishod: pretraga još nije pokretana.")
        if success:
            stamp = success.get("finished_at") or success.get("started_at") or ""
            self.last_success.setText("Poslednji put kad je bar jedan izvor odgovorio: " + _format_stamp(stamp))
        else:
            self.last_success.setText("Poslednji put kad je bar jedan izvor odgovorio: nema.")

    def refresh_source_table_from_db(self) -> None:
        rows = self.db.dashboard()["sources"]
        reports = [
            {
                "name": row["source_name"],
                "status": row["last_status"],
                "count": row.get("last_result_count") or 0,
                "error": row.get("last_error") or "",
            }
            for row in rows
        ]
        self.show_source_reports(reports)

    def show_source_reports(self, reports: list[dict]) -> None:
        self.source_table.setRowCount(len(reports))
        for index, item in enumerate(reports):
            values = [
                str(item.get("name") or ""),
                str(item.get("status") or ""),
                str(item.get("count") if item.get("count") is not None else ""),
                str(item.get("error") or ""),
            ]
            for column, value in enumerate(values):
                self.source_table.setItem(index, column, QTableWidgetItem(value))

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
        try:
            config = self.current_config_from_form()
            validate_limits(config)
        except ConfigError as exc:
            QMessageBox.warning(self, "Pretraga", str(exc))
            return
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
        if "max_organizations" in data:
            self._assign_int_spin(self.max_orgs, data.get("max_organizations"), "Najviše ustanova")
        if "recency_days" in data:
            self._assign_int_spin(self.recency, data.get("recency_days"), "Period unazad")
        enabled = set(data.get("enabled_sources") or [])
        for name, box in self.source_boxes.items():
            box.setChecked(name in enabled)
        self.statusBar().showMessage("Sačuvana pretraga je učitana. Ključevi nisu u tom zapisu.")

    def _assign_int_spin(self, spin: QSpinBox, value: object, label: str, notify: bool = True) -> bool:
        number = value
        if isinstance(number, float) and number.is_integer():
            number = int(number)
        if isinstance(number, bool) or not isinstance(number, int):
            if notify:
                QMessageBox.warning(self, "Vrednost", f"{label} mora biti ceo broj. Izmena nije primenjena.")
            return False
        if number < spin.minimum() or number > spin.maximum():
            if notify:
                QMessageBox.warning(
                    self,
                    "Vrednost",
                    f"{label} mora biti od {spin.minimum()} do {spin.maximum()}. Uneto je {number}. Izmena nije primenjena.",
                )
            return False
        spin.setValue(number)
        return True

    def start_search(self) -> None:
        self._begin_search(repeated=False)

    def refresh_search(self) -> None:
        self._begin_search(repeated=True)

    def _begin_search(self, repeated: bool) -> None:
        if self.thread and self.thread.isRunning():
            return
        try:
            config = self.current_config_from_form()
            validate_limits(config)
        except ConfigError as exc:
            QMessageBox.warning(self, "Pretraga", str(exc))
            return
        if not config.enabled_sources:
            QMessageBox.warning(self, "Pretraga", "Uključite bar jedan izvor. Pretraga nije pokrenuta.")
            return
        self.thread = SearchThread(str(self.db.path), config)
        self.thread.progress.connect(self.append_log)
        self.thread.finished_ok.connect(self.search_finished)
        self.start_button.setEnabled(False)
        self.refresh_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        if repeated:
            self.append_log("Osvežavanje ponovo pita uključene izvore. Postojeći zapisi se ne brišu.")
        else:
            self.append_log("Pretraga je pokrenuta.")
        self.thread.start()

    def stop_search(self) -> None:
        if self.thread:
            self.thread.cancel()
            self.append_log("Zaustavljanje je zatraženo. Sačuvani zapisi ostaju.")

    def append_log(self, message: str) -> None:
        self.search_log.appendPlainText(message)

    def search_finished(self, result: dict) -> None:
        self.start_button.setEnabled(True)
        self.refresh_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        status = str(result.get("status") or "")
        self.append_log(f"{outcome_label(status)} Ustanova u ovom prolazu: {result.get('stored', 0)}.")
        reports = result.get("sources")
        if isinstance(reports, list):
            self.show_source_reports(reports)
        else:
            self.refresh_source_table_from_db()
        self.view_suppressed = False
        self.refresh_run_status()
        self.refresh_dashboard()
        self.reload_leads()
        self.statusBar().showMessage(outcome_label(status))

    def show_saved_searches(self) -> None:
        self.tabs.setCurrentWidget(self.search_page)
        self.saved_searches.setFocus()

    def show_settings(self) -> None:
        self.tabs.setCurrentWidget(self.settings_page)

    def clear_current_view(self) -> None:
        self.view_suppressed = True
        self.table.setRowCount(0)
        self.detail.clear()
        self.notes.clear()
        self.current_lead_id = None
        self.statusBar().showMessage("Prikaz je očišćen. Zapisi u bazi su ostali.")

    def apply_filters(self) -> None:
        self.view_suppressed = False
        self.reload_leads()

    def reload_leads(self) -> None:
        if self.view_suppressed:
            self.table.setRowCount(0)
            return
        filters = {
            "min_level": self.filter_level.currentText(),
            "country": self.filter_country.text().strip(),
            "format": self.filter_format.currentText(),
            "procurement": self.filter_procurement.currentData() or "",
        }
        rows = self.db.query_leads(filters)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for row_index, lead in enumerate(rows):
            for column, (key, _title) in enumerate(LEAD_COLUMNS):
                value = lead.get(key) or ""
                if key == "procurement_signal":
                    value = procurement_label(str(value))
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, lead["id"])
                self.table.setItem(row_index, column, item)
        self.table.setSortingEnabled(True)

    def selected_lead_ids(self) -> list[int]:
        ids: list[int] = []
        for index in self.table.selectionModel().selectedRows():
            item = self.table.item(index.row(), 0)
            if item is None:
                continue
            lead_id = item.data(Qt.ItemDataRole.UserRole)
            if lead_id:
                ids.append(int(lead_id))
        return ids

    def delete_selected(self) -> None:
        ids = self.selected_lead_ids()
        if not ids:
            QMessageBox.information(self, "Brisanje", "Nije izabran nijedan lid. Prikaz nije obrisan i baza nije dirana.")
            return
        answer = QMessageBox.question(
            self,
            "Potvrda brisanja",
            DELETE_SELECTED_TEXT,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.statusBar().showMessage("Brisanje je otkazano. Ništa nije obrisano.")
            return
        self._delete(lambda: delete_selected_if_confirmed(self.db, ids, True, self._backup_directory()))

    def delete_all_research(self) -> None:
        answer = QMessageBox.question(
            self,
            "Potvrda brisanja",
            DELETE_ALL_TEXT,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.statusBar().showMessage("Brisanje je otkazano. Ništa nije obrisano.")
            return
        self._delete(lambda: delete_all_if_confirmed(self.db, True, self._backup_directory()))

    def _delete(self, action) -> None:
        try:
            destination = action()
        except DeletionRefused as exc:
            QMessageBox.warning(self, "Brisanje", str(exc))
            return
        self.view_suppressed = False
        self.current_lead_id = None
        self.detail.clear()
        self.reload_leads()
        self.refresh_dashboard()
        self.statusBar().showMessage(f"Zapisi su obrisani. Rezervna kopija: {destination}")

    def _backup_directory(self) -> Path:
        return self.backup_directory or backup_dir()

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

    def _refresh_credential_labels(self) -> None:
        for info in SOURCE_CATALOG:
            label = self.credential_state[info["name"]]
            if info["auth"] == "none":
                label.setText("Ključ nije potreban.")
                continue
            field_name = info["credential"]
            if getattr(self.config, field_name, ""):
                label.setText("Ključ je sačuvan.")
            elif info["auth"] == "required":
                label.setText("Ključ nije sačuvan. Izvor se ne poziva.")
            else:
                label.setText("Ključ nije sačuvan. Izvor radi i bez njega, uz niži limit.")

    def _apply_credential_editors(self) -> None:
        for field_name, editor in self.credential_editors.items():
            if field_name in self.credential_clears:
                setattr(self.config, field_name, "")
                continue
            typed = editor.text().strip()
            if typed:
                setattr(self.config, field_name, typed)

    def save_settings(self) -> None:
        self.config.priority_countries = _split(self.priority.text())
        self.config.deprioritized_countries = _split(self.deprioritized.text())
        self.config.excluded_names = _split(self.excluded.text())
        self._apply_credential_editors()
        if not self._persist_settings():
            return
        self.statusBar().showMessage("Podešavanja su sačuvana. Ključevi nisu upisani u config.json.")

    def remove_credential(self, field_name: str, _checked: bool = False) -> None:
        answer = QMessageBox.question(
            self,
            "Uklanjanje ključa",
            "Sačuvani ključ biće uklonjen iz skladišta. Lidovi, dokazi i beleške ostaju.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.statusBar().showMessage("Ključ nije uklonjen.")
            return
        self.credential_clears.add(field_name)
        editor = self.credential_editors.get(field_name)
        if editor is not None:
            editor.clear()
        setattr(self.config, field_name, "")
        self._persist_settings()

    def _persist_settings(self) -> bool:
        try:
            save_config(self.config, self.config_file, self.vault)
        except Exception as exc:
            secrets = [str(getattr(self.config, name) or "") for name in SECRET_FIELDS]
            QMessageBox.warning(self, "Podešavanja", "Čuvanje nije uspelo. " + redact(str(exc), secrets))
            return False
        self.credential_clears.clear()
        for editor in self.credential_editors.values():
            editor.clear()
        self._refresh_credential_labels()
        return True

    def test_source_connection(self, name: str, _checked: bool = False) -> None:
        existing = self._probes.get(name)
        if existing is not None and existing.isRunning():
            return
        info = catalog_by_name()[name]
        trial = replace(self.config)
        field_name = info.get("credential") or ""
        if field_name:
            if field_name in self.credential_clears:
                setattr(trial, field_name, "")
            else:
                typed = self.credential_editors[field_name].text().strip()
                if typed:
                    setattr(trial, field_name, typed)
        self.probe_state[name].setText("Proba veze je u toku.")
        probe = ConnectionProbe(name, trial)
        probe.finished_probe.connect(self._on_probe)
        self._probes[name] = probe
        probe.start()

    def _on_probe(self, name: str, status: str, message: str) -> None:
        label = self.probe_state.get(name)
        if label is None:
            return
        title = {"ok": "Veza radi", "missing": "Ključ nedostaje", "failed": "Veza nije uspela"}.get(status, status)
        label.setText(f"Poslednja proba: {title}. {message}")

    def make_backup(self) -> None:
        destination = self._backup_directory() / "tamigo-backup.sqlite"
        self.db.backup_to(destination)
        self.statusBar().showMessage(f"Kopija: {destination}")


def _split(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _format_stamp(value: str) -> str:
    if not value:
        return "nema vremena"
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return value
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    local = moment.astimezone()
    zone = local.tzname() or "lokalno"
    return local.strftime("%Y-%m-%d %H:%M") + f" ({zone})"


def _link_label(caption: str, url: str) -> QLabel:
    label = QLabel(f'<a href="{url}">{caption}</a>')
    label.setOpenExternalLinks(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
    return label


def dumps_config(config: SearchConfig) -> str:
    return json.dumps(config.to_public_dict(), ensure_ascii=False)
