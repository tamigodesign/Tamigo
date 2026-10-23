from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tamigo_intel.config import SearchConfig
from tamigo_intel.http_client import HttpClient
from tamigo_intel.sources.base import Discovered
from tamigo_intel.terms import clean_text, procurement_level, relevant

ENDPOINT = "https://api.usaspending.gov/api/v2/search/spending_by_award/"


class UsaSpendingSource:
    name = "usaspending"

    def search(self, config: SearchConfig, client: HttpClient) -> list[Discovered]:
        found: list[Discovered] = []
        seen: set[str] = set()
        start = (datetime.now(timezone.utc) - timedelta(days=config.recency_days)).date().isoformat()
        end = datetime.now(timezone.utc).date().isoformat()
        for keyword in config.keywords:
            if len(found) >= config.max_per_source:
                break
            payload = {
                "filters": {
                    "keywords": [keyword],
                    "time_period": [{"start_date": start, "end_date": end}],
                    "award_type_codes": ["A", "B", "C", "D"],
                },
                "fields": [
                    "Award ID",
                    "Recipient Name",
                    "Description",
                    "Awarding Agency",
                    "Award Amount",
                    "Start Date",
                    "generated_internal_id",
                ],
                "limit": min(20, config.max_per_source),
                "page": 1,
            }
            data = client.post_json(ENDPOINT, payload)
            for item in data.get("results") or []:
                award_id = str(item.get("generated_internal_id") or item.get("Award ID") or "")
                if not award_id or award_id in seen:
                    continue
                description = clean_text(str(item.get("Description") or ""), 1500)
                agency = clean_text(str(item.get("Awarding Agency") or ""), 300)
                recipient = clean_text(str(item.get("Recipient Name") or ""), 300)
                if not agency or not relevant(description, config.keywords):
                    continue
                seen.add(award_id)
                amount = item.get("Award Amount")
                level = procurement_level(description[:180], description)
                found.append(
                    Discovered(
                        source_name=self.name,
                        source_record_id=award_id,
                        source_url=f"https://www.usaspending.gov/award/{award_id}",
                        organization_name=agency,
                        country="US",
                        title=description[:180] or award_id,
                        excerpt=description,
                        explanation=(
                            "USAspending prikazuje dodeljen ugovor čiji opis pominje pristupačnost. "
                            f"Primalac sredstava je {recipient or 'nije naveden'}. "
                            "Primalac je postojeći dobavljač, ne ustanova kojoj se nudi usluga. "
                            "Naručilac je ustanova koja je već kupila ovu vrstu rada."
                        ),
                        limitations="Dodela nije otvoren poziv i nije dokaz trenutnog kvara na dokumentu ili sajtu.",
                        kind="award",
                        level=level,
                        published_at=item.get("Start Date"),
                        procurement_signal="past_award",
                        amount=float(amount) if amount not in (None, "") else None,
                        supplier_name=recipient,
                        notice_status="awarded",
                        currency="USD",
                        raw={
                            "Award ID": item.get("Award ID"),
                            "Awarding Agency": agency,
                            "Recipient Name": recipient,
                            "Description": description,
                        },
                    )
                )
                if len(found) >= config.max_per_source:
                    break
        return found
