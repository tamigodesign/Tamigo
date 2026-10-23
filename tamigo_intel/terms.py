from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone

STRONG_TERMS = (
    "wcag",
    "pdf/ua",
    "pdfua",
    "epub accessibility",
    "section 508",
    "accessibility remediation",
    "accessibility audit",
    "accessibility testing",
    "digital accessibility",
    "screen reader",
    "untagged pdf",
    "vpat",
    "accessibility conformance",
    "pdf accessibility",
    "accessible pdf",
    "website accessibility",
    "web accessibility",
    "accessible epub",
    "epub accessibility 1.1",
)

GENERIC_KEYWORDS = {
    "accessibility",
    "access",
    "remediation",
    "audit",
    "testing",
    "document",
    "pdf",
    "epub",
    "website",
}

CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("izdavac", ("publisher", "publishing", "university press", "izdava")),
    ("univerzitet", ("university", "college", "faculty", "univerzitet")),
    ("biblioteka", ("library", "libraries", "bibliotek")),
    ("muzej_arhiv", ("museum", "archive", "archives", "muzej")),
    ("vlada", ("department", "ministry", "council", "county", "agency", "government", "digital service", "municipality")),
    ("zdravstvo", ("hospital", "health", "nhs", "clinic", "medical center")),
    ("udruzenje", ("association", "foundation", "nonprofit", "charity")),
    ("istrazivacki_institut", ("research institute", "laboratory")),
]


def normalize_name(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_text(value: str, limit: int = 4000) -> str:
    value = value.replace("\x00", " ")
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit]


PRIMARY_PROCUREMENT_PHRASES = (
    "accessibility audit",
    "accessibility remediation",
    "accessibility testing",
    "accessibility review",
    "accessibility scan",
    "accessibility scanning",
    "pdf accessibility",
    "epub accessibility",
    "section 508",
    "document remediation",
    "508 accessibility",
    "508 document",
    "wcag",
    "accessible pdf",
    "accessible epub",
)


def procurement_level(title: str, excerpt: str) -> str:
    """A samo kad je pristupačnost predmet oglasa, ne sporedna rečenica."""
    title_l = title.lower()
    head = f"{title}\n{excerpt[:350]}".lower()
    if any(phrase in title_l or phrase in head for phrase in PRIMARY_PROCUREMENT_PHRASES):
        return "A"
    if relevant(f"{title} {excerpt}"):
        return "C"
    return "D"


def relevant(text: str, keywords: list[str] | None = None) -> bool:
    low = text.lower()
    if any(term in low for term in STRONG_TERMS):
        return True
    for keyword in keywords or []:
        key = keyword.lower().strip().strip('"')
        if len(key) >= 5 and key not in GENERIC_KEYWORDS and key in low:
            return True
    return False


def infer_category(name: str, text: str = "") -> tuple[str, str]:
    blob = f"{name} {text}".lower()
    for category, needles in CATEGORY_RULES:
        if any(needle in blob for needle in needles):
            return category, "inferred_from_name"
    return "", "not_verified"


def detect_formats(text: str) -> list[str]:
    low = text.lower()
    found: list[str] = []
    if any(token in low for token in ("pdf", "pdf/ua", "pdfua", "untagged")):
        found.append("pdf")
    if "epub" in low:
        found.append("epub")
    if any(token in low for token in ("wcag", "website", "web accessibility", "section 508", "screen reader", "vpat")):
        found.append("web")
    return found


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    for candidate in (text, text.split("T")[0]):
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def age_days(value: str | None, now: datetime | None = None) -> int | None:
    parsed = parse_date(value)
    if parsed is None:
        return None
    moment = now or datetime.now(timezone.utc)
    return max(0, (moment - parsed).days)


PROCUREMENT_LABELS = {
    "open_procurement": "Otvorena nabavka",
    "past_award": "Istorijska dodela (nije otvoren poziv)",
    "closed": "Zatvoren ili stariji oglas (nije otvoren poziv)",
    "none": "Nema zapisa o nabavci",
}


def procurement_label(signal: str | None) -> str:
    return PROCUREMENT_LABELS.get(signal or "none", PROCUREMENT_LABELS["none"])


def country_code(value: str | None) -> str:
    if not value:
        return ""
    text = value.strip()
    mapping = {
        "united states": "US",
        "usa": "US",
        "us": "US",
        "united kingdom": "GB",
        "uk": "GB",
        "great britain": "GB",
        "gb": "GB",
        "canada": "CA",
        "ca": "CA",
        "australia": "AU",
        "au": "AU",
        "nld": "NL",
        "netherlands": "NL",
        "nederland": "NL",
        "deu": "DE",
        "germany": "DE",
        "fra": "FR",
        "france": "FR",
        "irl": "IE",
        "ireland": "IE",
    }
    key = text.lower()
    if key in mapping:
        return mapping[key]
    if len(text) == 2:
        return text.upper()
    if len(text) == 3 and text.isalpha():
        return text.upper()
    return text.upper()
