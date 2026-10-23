from __future__ import annotations

import threading


class Cancelled(Exception):
    """Pretraga je zaustavljena. Već upisani zapisi ostaju u bazi."""


class CancelToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise Cancelled()
