from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tamigo_intel.config import SearchConfig
from tamigo_intel.http_client import HttpClient
from tamigo_intel.sources.base import Discovered
from tamigo_intel.terms import clean_text, country_code, parse_date, procurement_level, relevant

ENDPOINT = "https://www.contractsfinder.service.gov.uk/api/rest/2/search_notices/json"


class ContractsFinderSource:
    name = "contracts_finder"

    def search(self, config: SearchConfig, client: HttpClient) -> list[Discovered]:
        found: list[Discovered] = []
        seen: set[str] = set()
        published_from = (datetime.now(timezone.utc) - timedelta(days=config.recency_days)).date().isoformat()
        for keyword in config.keywords:
            if len(found) >= config.max_per_source:
                break
            payload = {
                "searchCriteria": {
                    "keyword": keyword,
                    "statuses": ["Open", "Awarded", "Closed"],
                    "types": ["Contract"],
                    "publishedFrom": published_from,
                },
                "size": config.max_per_source,
            }
            data = client.post_json(ENDPOINT, payload)
            for entry in data.get("noticeList") or []:
                item = entry.get("item") or {}
                record_id = str(item.get("id") or "")
                if not record_id or record_id in seen:
                    continue
                title = clean_text(item.get("title") or "", 300)
                description = clean_text(item.get("description") or "", 1500)
                text = f"{title} {description}"
                if not relevant(text, config.keywords):
                    continue
                seen.add(record_id)
                status = str(item.get("noticeStatus") or "")
                deadline = parse_date(item.get("deadlineDate"))
                now = datetime.now(timezone.utc)
                if status.lower() == "open" and (deadline is None or deadline >= now):
                    signal = "open_procurement"
                elif status.lower() == "awarded":
                    signal = "past_award"
                else:
                    signal = "closed"
                amount = item.get("awardedValue")
                if not amount:
                    amount = item.get("valueLow") or None
                buyer = clean_text(item.get("organisationName") or "", 300)
                if not buyer:
                    continue
                supplier = clean_text(item.get("awardedSupplier") or "", 300)
                level = procurement_level(title, description)
                if level == "A":
                    explanation = (
                        "Predmet oglasa ili uvod opisa traži pristupačnost. "
                        "To je trag nabavke, ne potvrđen tehnički kvar."
                    )
                else:
                    explanation = (
                        "WCAG ili srodan termin postoji u oglasu, ali nije u naslovu ni u uvodu. "
                        "Predmet nabavke verovatno nije remedijacija. Nivo je C."
                    )
                if supplier:
                    explanation += f" Dobavljač naveden na oglasu: {supplier}. To nije kontakt za novu prodaju."
                found.append(
                    Discovered(
                        source_name=self.name,
                        source_record_id=record_id,
                        source_url=f"https://www.contractsfinder.service.gov.uk/Notice/{record_id}",
                        organization_name=buyer,
                        country=country_code("GB"),
                        region=clean_text(item.get("regionText") or "", 120),
                        title=title,
                        excerpt=description or title,
                        explanation=explanation,
                        limitations="Oglas ne dokazuje da postojeći sajt ili dokument ne ispunjava WCAG.",
                        kind="procurement_notice",
                        level=level,
                        published_at=item.get("publishedDate"),
                        procurement_signal=signal,
                        amount=float(amount) if amount else None,
                        supplier_name=supplier,
                        notice_status=status,
                        currency="GBP",
                        raw={"keyword": keyword, "id": record_id, "title": title, "organisationName": buyer},
                    )
                )
                if len(found) >= config.max_per_source:
                    break
        return found
