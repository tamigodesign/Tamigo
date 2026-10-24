from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from tamigo_intel.config import SearchConfig
from tamigo_intel.http_client import HttpClient
from tamigo_intel.sources.base import Discovered
from tamigo_intel.terms import clean_text, relevant


class SourceUnavailable(Exception):
    pass


class SamGovSource:
    name = "sam_gov"
    countries = ("US",)

    def search(self, config: SearchConfig, client: HttpClient) -> list[Discovered]:
        if not config.sam_api_key:
            raise SourceUnavailable(
                "SAM.gov traži API ključ sa api.data.gov. Ključ nije unet, pa ovaj izvor nije pozvan."
            )
        start = datetime.now(timezone.utc) - timedelta(days=min(config.recency_days, 365))
        params = {
            "api_key": config.sam_api_key,
            "keywords": config.keywords[0] if config.keywords else "accessibility",
            "limit": str(min(10, config.max_per_source)),
            "postedFrom": start.strftime("%m/%d/%Y"),
            "postedTo": datetime.now(timezone.utc).strftime("%m/%d/%Y"),
        }
        url = "https://api.sam.gov/opportunities/v2/search?" + urlencode(params)
        data = client.get_json(url)
        found: list[Discovered] = []
        for item in data.get("opportunitiesData") or []:
            title = clean_text(item.get("title") or "", 300)
            description = clean_text(item.get("description") or "", 1500)
            office = clean_text(item.get("fullParentPathName") or item.get("organizationName") or "", 300)
            text = f"{title} {description}"
            if not office or not relevant(text, config.keywords):
                continue
            notice_id = str(item.get("noticeId") or "")
            link = item.get("uiLink") or ""
            if not notice_id or not link:
                continue
            found.append(
                Discovered(
                    source_name=self.name,
                    source_record_id=notice_id,
                    source_url=link,
                    organization_name=office,
                    country="US",
                    title=title,
                    excerpt=description or title,
                    explanation="SAM.gov oglas. Tekst je javni poziv, ne tehnički nalaz.",
                    limitations="Bez otvaranja oglasa nije poznato da li je rok još otvoren.",
                    kind="procurement_notice",
                    level="A",
                    published_at=item.get("postedDate"),
                    procurement_signal="open_procurement",
                    notice_status=str(item.get("type") or ""),
                    raw={"noticeId": notice_id, "title": title},
                )
            )
        return found
