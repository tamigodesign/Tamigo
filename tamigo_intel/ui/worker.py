from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from tamigo_intel.cancel import CancelToken
from tamigo_intel.config import SearchConfig
from tamigo_intel.db import Database
from tamigo_intel.http_client import HttpClient
from tamigo_intel.pipeline import run_search
from tamigo_intel.redact import redact


class SearchThread(QThread):
    progress = Signal(str)
    finished_ok = Signal(dict)

    def __init__(self, db_path: str, config: SearchConfig) -> None:
        super().__init__()
        self.db_path = db_path
        self.config = config
        self.cancel_token = CancelToken()

    def cancel(self) -> None:
        self.cancel_token.cancel()

    def run(self) -> None:
        db = Database(self.db_path)
        secrets = [
            value
            for value in (self.config.sam_api_key, self.config.github_token, self.config.openai_api_key)
            if value
        ]
        client = HttpClient(
            min_interval=self.config.request_interval_seconds,
            cancel=self.cancel_token,
            secrets=secrets,
        )
        try:
            result = run_search(
                db,
                self.config,
                client=client,
                cancel=self.cancel_token,
                on_progress=self.progress.emit,
            )
        except Exception as exc:
            message = redact(str(exc), secrets)
            result = {"status": "error", "stored": 0, "log": [message], "error": message, "sources": []}
        self.finished_ok.emit(result)
