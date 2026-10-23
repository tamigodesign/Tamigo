from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from tamigo_intel.config import DEFAULT_WEIGHTS
from tamigo_intel.terms import age_days, detect_formats

LEVEL_RANK = {"A": 4, "B": 3, "C": 2, "D": 1}
SIGNAL_RANK = {"none": 0, "closed": 1, "past_award": 2, "open_procurement": 3}


@dataclass
class Score:
    evidence_level: str
    evidence_strength: int
    recency_score: int
    relevance_score: int
    scale_score: int
    procurement_score: int
    activity_score: int
    contact_score: int
    geo_score: int
    total_score: int
    procurement_signal: str
    formats: list[str]
    explanation: str
    summary: str
    next_action: str
    verification_status: str = "unverified_prospect"
    compliance_judgment: str = "none"
    lines: list[str] = field(default_factory=list)


def best_level(levels: list[str]) -> str:
    if not levels:
        return "D"
    return max(levels, key=lambda level: LEVEL_RANK.get(level, 0))


def best_signal(signals: list[str]) -> str:
    if not signals:
        return "none"
    return max(signals, key=lambda signal: SIGNAL_RANK.get(signal, 0))


def _base_evidence_points(level: str) -> int:
    return {"A": 40, "B": 25, "C": 12, "D": 0}.get(level, 0)


def _recency_points(days: int | None) -> int:
    if days is None:
        return 2
    if days <= 548:
        return 15
    if days <= 1095:
        return 8
    return 2


def _scale_points(amount: float | None) -> int:
    if amount is None:
        return 0
    if amount < 25_000:
        return 4
    if amount < 100_000:
        return 8
    if amount < 500_000:
        return 12
    return 16


def _procurement_points(signal: str) -> int:
    return {"open_procurement": 20, "past_award": 8, "closed": 4, "none": 0}.get(signal, 0)


def _geo_points(country: str, priority: list[str], deprioritized: list[str]) -> int:
    code = (country or "").upper()
    if code in {item.upper() for item in deprioritized}:
        return 1
    if code in {item.upper() for item in priority}:
        return 10 if code == "US" else 8
    if not code:
        return 3
    return 4


def classify_without_evidence(category: str = "") -> Score:
    """Pripadnost sektoru sama po sebi nije dokaz ni nalaz."""
    explanation = (
        "Nema javnog traga. Kategorija ustanove nije dokaz potrebe za remedijacijom "
        f"i nije ocena neusklađenosti. Kategorija: {category or 'nije utvrđena'}."
    )
    return Score(
        evidence_level="D",
        evidence_strength=0,
        recency_score=0,
        relevance_score=0,
        scale_score=0,
        procurement_score=0,
        activity_score=0,
        contact_score=0,
        geo_score=0,
        total_score=0,
        procurement_signal="none",
        formats=[],
        explanation=explanation,
        summary="Nema proverljivog traga. " + explanation,
        next_action="Ne tretirati kao klijenta dok se ne nađe izvor.",
        compliance_judgment="none",
        lines=[explanation],
    )


def score_lead(
    organization_name: str,
    country: str,
    evidence: list[dict],
    weights: dict[str, float] | None = None,
    priority_countries: list[str] | None = None,
    deprioritized_countries: list[str] | None = None,
    has_published_contact: bool = False,
    now: datetime | None = None,
) -> Score:
    if not evidence:
        return classify_without_evidence()
    weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    priority = priority_countries or ["US", "CA", "GB", "AU"]
    deprioritized = deprioritized_countries or []
    moment = now or datetime.now(timezone.utc)
    level = best_level([item.get("level", "D") for item in evidence])
    signal = best_signal([item.get("procurement_signal", "none") for item in evidence])
    formats: set[str] = set()
    amounts: list[float] = []
    lines = [
        "Ocena je zbir dokumentovanih pravila. Veći broj ne pretvara slab trag u jak.",
        "Ovo nije ocena neusklađenosti.",
        f"Nivo traga je najjači pojedinačni dokaz ({level}), ne ukupni bodovi.",
    ]
    strength = _base_evidence_points(level)
    lines.append(f"Jačina dokaza: {strength} za nivo {level}.")
    recency_values = []
    for item in evidence:
        recency_values.append(_recency_points(age_days(item.get("published_at"), moment)))
        formats.update(item.get("formats") or detect_formats(f"{item.get('title','')} {item.get('excerpt','')}"))
        if item.get("amount") is not None:
            amounts.append(float(item["amount"]))
    recency = max(recency_values) if recency_values else 2
    lines.append(f"Svežina: {recency}.")
    relevance = 10 if formats else 4
    lines.append(f"Relevantnost formata ({', '.join(sorted(formats)) or 'nije prepoznat'}): {relevance}.")
    scale = _scale_points(max(amounts) if amounts else None)
    lines.append(
        "Obim: vrednost javnog ugovora ako je objavljena, nije procena budžeta za novi angažman. "
        f"Bodovi: {scale}."
    )
    procurement = _procurement_points(signal)
    lines.append(f"Signal nabavke ({signal}): {procurement}.")
    activity = 6 if any(item.get("kind") == "technical_finding" for item in evidence) else 3
    lines.append(f"Aktivnost oko pristupačnosti: {activity}.")
    contact = 5 if has_published_contact else 0
    lines.append(f"Javni kontakt: {contact}.")
    geo = _geo_points(country, priority, deprioritized)
    lines.append(f"Geografski fit za {country or 'nepoznatu zemlju'}: {geo}.")
    parts = {
        "evidence": strength,
        "recency": recency,
        "relevance": relevance,
        "scale": scale,
        "procurement": procurement,
        "activity": activity,
        "contact": contact,
        "geo": geo,
    }
    total = round(sum(parts[name] * float(weights.get(name, 1)) for name in parts))
    lines.append(f"Zbir posle težina: {total}.")
    summary_lines = [
        f"{organization_name}: {len(evidence)} javnih tragova, nivo {level}.",
        "Ovo nije ocena neusklađenosti.",
    ]
    for item in evidence:
        summary_lines.append(f"- {item.get('title', '')}")
        summary_lines.append(f"  Izvor: {item.get('source_url', '')}")
        summary_lines.append(f"  Navedeno: {item.get('excerpt', '')[:400]}")
        summary_lines.append(f"  Zašto je u spisku: {item.get('explanation', '')}")
        summary_lines.append(f"  Ograničenje: {item.get('limitations', '')}")
    if signal == "open_procurement":
        action = "Otvoriti izvorni oglas i proveriti rok, predmet i uslove."
    elif signal == "past_award":
        action = "Proveriti da li je ugovor još aktivan i ko je naručilac. Navedeni dobavljač nije prodajni kontakt."
    elif level == "B":
        action = "Ručno proveriti tehnički indikator. Automatika nije potvrda WCAG neusaglašenosti."
    else:
        action = "Trag je slab ili indirektan. Ne tretirati kao spremnog klijenta dok se izvor ne pročita."
    return Score(
        evidence_level=level,
        evidence_strength=strength,
        recency_score=recency,
        relevance_score=relevance,
        scale_score=scale,
        procurement_score=procurement,
        activity_score=activity,
        contact_score=contact,
        geo_score=geo,
        total_score=total,
        procurement_signal=signal,
        formats=sorted(formats),
        explanation="\n".join(lines),
        summary="\n".join(summary_lines),
        next_action=action,
        lines=lines,
    )
