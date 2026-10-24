"""Find a Tender, zvanični OCDS API. Nije pretraga celog arhiva po ključnoj reči.

Čitaju se najnovija izdanja u zadatom prozoru, najviše nekoliko stranica, pa se
naslov i opis filtriraju lokalno. HTML stranica oglasa sa nekih mreža vraća 403.
Zapis je uzet iz API-ja. Provera sertifikata ostaje uključena.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tamigo_intel.config import SearchConfig
from tamigo_intel.http_client import HttpClient
from tamigo_intel.sources.base import Discovered
from tamigo_intel.terms import clean_text, parse_date, procurement_level, relevant

ENDPOINT = "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages"
MAX_PAGES = 4
PAGE_LIMIT = 25


class FindTenderSource:
    name = "find_tender"
    countries = ("GB",)

    def search(self, config: SearchConfig, client: HttpClient, now: datetime | None = None) -> list[Discovered]:
        moment = now or datetime.now(timezone.utc)
        start = (moment - timedelta(days=max(1, config.recency_days))).date().isoformat()
        url = f"{ENDPOINT}?limit={PAGE_LIMIT}&updatedFrom={start}T00:00:00"
        found: list[Discovered] = []
        for _page in range(MAX_PAGES):
            data = client.get_json(url)
            for release in data.get("releases") or []:
                item = release_to_item(release, config.keywords)
                if item is None:
                    continue
                found.append(item)
                if len(found) >= config.max_per_source:
                    return found
            url = str((data.get("links") or {}).get("next") or "")
            if not url:
                break
        return found


def release_to_item(release: dict, keywords: list[str]) -> Discovered | None:
    tender = release.get("tender") or {}
    title = clean_text(str(tender.get("title") or ""), 400)
    description = clean_text(str(tender.get("description") or ""), 700)
    if not title or not relevant(f"{title} {description}", keywords):
        return None
    buyer = clean_text(str((release.get("buyer") or {}).get("name") or ""), 300)
    if not buyer:
        return None
    notice_id = str(release.get("id") or "")
    ocid = str(release.get("ocid") or notice_id)
    if not ocid:
        return None
    signal = _signal(release.get("tag") or [], tender)
    amount = _amount((tender.get("value") or {}).get("amount"))
    currency = str((tender.get("value") or {}).get("currency") or "")
    notice_url = (
        f"https://www.find-tender.service.gov.uk/Notice/{notice_id}"
        if notice_id
        else ENDPOINT
    )
    level = procurement_level(title, description)
    return Discovered(
        source_name="find_tender",
        source_record_id=ocid,
        source_url=notice_url,
        organization_name=buyer,
        country="GB",
        title=title,
        excerpt=description or title,
        explanation=(
            "Find a Tender OCDS. Čitan je naslov i opis iz API izdanja. "
            "HTML stranica oglasa nije preuzeta."
        ),
        limitations=(
            "Ovo nije pretraga celog arhiva. Gledaju se najnovija izdanja u prozoru, "
            "najviše četiri stranice. HTML adresa oglasa sa nekih mreža vraća HTTP 403, "
            "što nije greška sertifikata. Iznos je onaj iz OCDS zapisa, ako postoji."
        ),
        level=level,
        kind="award" if signal == "past_award" else "procurement_notice",
        published_at=str(release.get("date") or "") or None,
        procurement_signal=signal,
        amount=amount,
        currency=currency,
        notice_status=signal,
        raw={"ocid": ocid, "notice_id": notice_id, "tags": list(release.get("tag") or [])},
    )


def _signal(tags: list, tender: dict) -> str:
    names = {str(tag) for tag in tags}
    if "award" in names or "contract" in names:
        return "past_award"
    if "tender" not in names:
        return "closed"
    end = parse_date(str((tender.get("tenderPeriod") or {}).get("endDate") or ""))
    if end is not None and end < datetime.now(timezone.utc):
        return "closed"
    return "open_procurement"


def _amount(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value <= 0:
        return None
    return float(value)
