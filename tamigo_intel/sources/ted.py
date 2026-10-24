from __future__ import annotations

from datetime import datetime, timezone

from tamigo_intel.config import SearchConfig
from tamigo_intel.http_client import HttpClient
from tamigo_intel.sources.base import Discovered
from tamigo_intel.terms import age_days, clean_text, country_code, procurement_level, relevant

ENDPOINT = "https://api.ted.europa.eu/v3/notices/search"


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(_text(item) for item in value)
    if isinstance(value, dict):
        for key in ("eng", "en", "nld", "deu", "fra"):
            if key in value:
                return _text(value[key])
        if value:
            return _text(next(iter(value.values())))
    return str(value)


class TedSource:
    name = "ted"

    def search(self, config: SearchConfig, client: HttpClient) -> list[Discovered]:
        clauses = []
        for keyword in config.keywords:
            safe = keyword.replace('"', "").strip()
            if not safe:
                continue
            # Pretraga ide samo po naslovu. Pun tekst vraća oglase u kojima termina nema
            # u naslovu, a telo oglasa se ne čuva, pa takav pogodak nema dokaz.
            if " " in safe:
                clauses.append(f'(notice-title ~ "{safe}")')
            else:
                clauses.append(f"(notice-title ~ {safe})")
        if not clauses:
            return []
        cap = 12 if config.multilingual else 8
        query = " OR ".join(clauses[:cap])
        payload = {
            "query": query,
            "fields": ["publication-number", "publication-date", "notice-title", "buyer-name", "buyer-country"],
            "limit": config.max_per_source,
            "page": 1,
            "scope": "ALL",
            "paginationMode": "PAGE_NUMBER",
        }
        data = client.post_json(ENDPOINT, payload)
        found: list[Discovered] = []
        for notice in data.get("notices") or []:
            number = str(notice.get("publication-number") or "")
            if not number:
                continue
            title = clean_text(_text(notice.get("notice-title")), 400)
            buyer = clean_text(_text(notice.get("buyer-name")), 300)
            if not buyer or not relevant(title, config.keywords):
                continue
            country = country_code(_text(notice.get("buyer-country")))
            published = notice.get("publication-date")
            days = age_days(published, datetime.now(timezone.utc))
            recent = days is not None and days <= 45
            found.append(
                Discovered(
                    source_name=self.name,
                    source_record_id=number,
                    source_url=f"https://ted.europa.eu/en/notice/-/detail/{number}",
                    organization_name=buyer,
                    country=country,
                    title=title,
                    excerpt=title,
                    explanation=(
                        "TED je službeni oglas javne nabavke. Naslov pominje pristupačnost. "
                        "Zemlja ostaje prazna ako je API nije vratio. To nije zaključak iz naslova."
                    ),
                    limitations=(
                        "Status oglasa nije preuzet. Samo objava mlađa od 45 dana računa se kao moguće otvoren poziv. "
                        "Oglas nije tehnički nalaz. Tekst van naslova nije preuzet."
                    ),
                    kind="procurement_notice",
                    level=procurement_level(title, title),
                    published_at=published,
                    procurement_signal="open_procurement" if recent else "closed",
                    notice_status="ted_recent" if recent else "ted_older",
                    raw={"publication-number": number, "buyer-name": buyer, "notice-title": title},
                )
            )
            if len(found) >= config.max_per_source:
                break
        return found
