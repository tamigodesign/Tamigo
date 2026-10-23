from __future__ import annotations

from datetime import datetime, timedelta, timezone


def should_run_scheduled(last_run: datetime | None, interval_hours: int, now: datetime | None = None, app_open: bool = True) -> bool:
    """Nema pozadinske usluge. Zakazana pretraga važi samo dok je program otvoren."""
    if not app_open or interval_hours <= 0:
        return False
    moment = now or datetime.now(timezone.utc)
    if last_run is None:
        return True
    return moment - last_run >= timedelta(hours=interval_hours)
