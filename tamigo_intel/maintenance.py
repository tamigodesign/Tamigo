"""Brisanje samo uz izričitu potvrdu. Pre toga se pravi rezervna kopija."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from tamigo_intel.db import Database


class DeletionRefused(Exception):
    pass


DELETE_SELECTED_TEXT = (
    "Biće obrisani samo izabrani lidovi, njihovi dokazi, kontakti i beleške. "
    "Ostali lidovi ostaju. Pre brisanja pravi se rezervna kopija baze. "
    "Ovo nije čišćenje prikaza."
)

DELETE_ALL_TEXT = (
    "Biće obrisane sve lokalno sačuvane ustanove, lidovi, dokazi, kontakti, beleške i istorija pretrage. "
    "Sačuvane pretrage, podešavanja i API ključevi ostaju. "
    "Pre brisanja pravi se rezervna kopija baze. "
    "Ovo nije čišćenje prikaza i ne dešava se pri osvežavanju pretrage."
)


def _backup(db: Database, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = directory / f"pre-brisanja-{stamp}.sqlite"
    db.backup_to(destination)
    return destination


def delete_selected_if_confirmed(db: Database, lead_ids: list[int], confirmed: bool, backup_directory: Path) -> Path:
    if not confirmed:
        raise DeletionRefused("Brisanje izabranih lidova traži potvrdu.")
    if not lead_ids:
        raise DeletionRefused("Nije izabran nijedan lid.")
    destination = _backup(db, backup_directory)
    db.delete_leads(lead_ids)
    return destination


def delete_all_if_confirmed(db: Database, confirmed: bool, backup_directory: Path) -> Path:
    if not confirmed:
        raise DeletionRefused("Brisanje svih istraživačkih podataka traži potvrdu.")
    destination = _backup(db, backup_directory)
    db.delete_all_research()
    return destination
