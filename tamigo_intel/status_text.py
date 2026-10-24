"""Ishodi pretrage. Uspeh znači da je bar jedan izvor stvarno odgovorio."""

from __future__ import annotations

STATUS_LABELS = {
    "completed_with_results": "Pretraga je završena. Izvori su odgovorili i ima sačuvanih tragova.",
    "completed_empty": "Pretraga je uspela. Izvori su odgovorili, ali u ovom prolazu nema sačuvanih tragova.",
    "partial": "Pretraga je delimično uspela. Neki izvori nisu odgovorili.",
    "failed": "Pretraga nije uspela. Nijedan uključeni izvor nije uspešno odgovorio.",
    "cancelled": "Pretraga je zaustavljena. Sačuvani zapisi ostaju.",
    "error": "Pretraga je prekinuta greškom.",
    "needs_configuration": "Pretraga čeka podešavanje. Nijedan uključeni izvor nije mogao da se pozove.",
    "completed": "Stariji zapis: pretraga je označena kao završena.",
}


def outcome_label(status: str) -> str:
    return STATUS_LABELS.get(status or "", status or "nepoznat ishod")


def overall_status(reports: list[dict], stored: int) -> str:
    if not reports:
        return "failed"
    considered = [item for item in reports if item.get("status") != "skipped"]
    if not considered:
        return "completed_empty"
    ok = [item for item in considered if item.get("status") == "ok"]
    failed = [item for item in considered if item.get("status") != "ok"]
    if not ok:
        if all(item.get("status") == "unavailable" for item in considered):
            return "needs_configuration"
        return "failed"
    if failed:
        return "partial"
    if stored > 0:
        return "completed_with_results"
    return "completed_empty"
