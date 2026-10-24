from __future__ import annotations

import re

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)


def published_emails(text: str) -> list[str]:
    seen: list[str] = []
    for match in EMAIL_RE.findall(text or ""):
        if match not in seen:
            seen.append(match)
    return seen


def contact_from_discovery(
    organization_id: int,
    source_url: str,
    text: str,
    department: str = "",
    *,
    email: str = "",
    name: str = "",
) -> dict | None:
    explicit = published_emails(email)
    if explicit:
        chosen = explicit[0]
        stored_name = name.strip()
    else:
        found = published_emails(text)
        if not found:
            return None
        chosen = found[0]
        stored_name = ""
    return {
        "organization_id": organization_id,
        "name": stored_name,
        "title": "",
        "department": department,
        "email": chosen,
        "email_verification": "published_in_source",
        "profile_url": "",
        "department_url": source_url,
        "source_url": source_url,
        "notes": "Adresa je prepisana iz javnog zapisa izvora. Nije proverena odgovorom primaoca.",
    }
