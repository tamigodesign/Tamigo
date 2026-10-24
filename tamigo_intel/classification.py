"""Odvajanje dokaza od statusa prilike. Ne menja postojeći bodovni zbir."""

from __future__ import annotations

EVIDENCE_LABELS = {
    "explicit_procurement": "Izričita nabavka ili zahtev za pristupačnost",
    "strong_demand": "Jak trag potražnje",
    "technical_indicator": "Automatski indikator, nije potvrda neusklađenosti",
    "needs_verification": "Moguć trag, traži proveru",
    "historical": "Samo istorijski dokaz",
    "insufficient": "Nedovoljan dokaz",
}

OPPORTUNITY_LABELS = {
    "active": "Aktivna prilika",
    "historical_award": "Istorijska dodela ili ugovor",
    "closed": "Zatvorena ili istekla prilika",
    "organization_prospect": "Trag na nivou ustanove, bez otvorenog oglasa",
}


def evidence_class(level: str, procurement_signal: str, kind: str = "") -> str:
    signal = procurement_signal or "none"
    if signal == "past_award":
        return "historical"
    if signal == "open_procurement" and level in {"A", "B"}:
        return "explicit_procurement"
    if level == "A":
        return "strong_demand"
    if level == "B" or kind == "technical_finding":
        return "technical_indicator"
    if level == "C":
        return "needs_verification"
    return "insufficient"


def opportunity_status(procurement_signal: str) -> str:
    return {
        "open_procurement": "active",
        "past_award": "historical_award",
        "closed": "closed",
        "none": "organization_prospect",
    }.get(procurement_signal or "none", "organization_prospect")


def evidence_label(level: str, procurement_signal: str, kind: str = "") -> str:
    return EVIDENCE_LABELS[evidence_class(level, procurement_signal, kind)]


def opportunity_label(procurement_signal: str) -> str:
    return OPPORTUNITY_LABELS[opportunity_status(procurement_signal)]
