from __future__ import annotations

import os

import pytest


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    # PySide6 u ovom Linux okruženju ruši proces pri gašenju interpreterа
    # iako su testovi prošli. Izlazni kod ostaje onaj koji je pytest izračunao.
    if os.environ.get("TAMIGO_KEEP_QT_SHUTDOWN") == "1":
        return
    os._exit(exitstatus)
