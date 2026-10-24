from __future__ import annotations

from urllib.parse import quote

from tamigo_intel.config import SearchConfig
from tamigo_intel.http_client import HttpClient
from tamigo_intel.sources.base import Discovered
from tamigo_intel.terms import clean_text, relevant


class GitHubIssuesSource:
    name = "github_issues"

    def search(self, config: SearchConfig, client: HttpClient) -> list[Discovered]:
        keyword = next((item for item in config.keywords if " " in item), "accessibility remediation")
        query = quote(f'"{keyword}" is:issue')
        url = f"https://api.github.com/search/issues?q={query}&per_page={min(5, config.max_per_source)}"
        headers = {"Accept": "application/vnd.github+json"}
        if config.github_token:
            headers["Authorization"] = f"Bearer {config.github_token}"
        data = client.get_json(url, headers=headers)
        found: list[Discovered] = []
        for item in data.get("items") or []:
            title = clean_text(item.get("title") or "", 300)
            body = clean_text(item.get("body") or "", 1200)
            text = f"{title} {body}"
            if not relevant(text, config.keywords):
                continue
            repo_url = item.get("repository_url") or ""
            owner = repo_url.rstrip("/").split("/")[-2] if repo_url.count("/") >= 2 else "nepoznat repozitorijum"
            number = str(item.get("number") or item.get("id") or "")
            html = item.get("html_url") or ""
            if not html or not number:
                continue
            found.append(
                Discovered(
                    source_name=self.name,
                    source_record_id=f"{owner}#{number}",
                    source_url=html,
                    organization_name=owner,
                    country="",
                    title=title,
                    excerpt=body or title,
                    explanation=(
                        "Javni GitHub issue pominje pristupačnost. Vlasnik repozitorijuma nije automatski ustanova "
                        "koja kupuje remedijaciju, niti je issue dokaz pravne neusklađenosti."
                    ),
                    limitations="Nivo je C. Komercijalni fit je nizak dok se vlasnik ručno ne prepozna.",
                    kind="public_issue",
                    level="C",
                    published_at=item.get("created_at"),
                    procurement_signal="none",
                    raw={"repository": repo_url, "number": number},
                )
            )
        return found
