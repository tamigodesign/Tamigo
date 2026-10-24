from __future__ import annotations

from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

from tamigo_intel.http_client import USER_AGENT, HttpClient, HttpError


def robots_allow(url: str, client: HttpClient) -> tuple[bool, str]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False, "Dozvoljeni su samo http i https."
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        body = client.get_bytes(robots_url, headers={"Accept": "text/plain"}, max_bytes=200_000)
    except HttpError as exc:
        if exc.status == 404:
            return True, "robots.txt ne postoji."
        return False, f"robots.txt nije pročitan ({exc}). Stranica nije preuzeta."
    parser = RobotFileParser()
    parser.parse(body.decode("utf-8", "replace").splitlines())
    allowed = parser.can_fetch(USER_AGENT, url)
    if not allowed:
        return False, "robots.txt zabranjuje preuzimanje ovog URL-a."
    return True, "robots.txt dozvoljava preuzimanje."


def fetch_html(url: str, client: HttpClient, max_bytes: int = 2_000_000) -> tuple[str, str]:
    allowed, reason = robots_allow(url, client)
    if not allowed:
        raise PermissionError(reason)
    data = client.get_bytes(url, headers={"Accept": "text/html"}, max_bytes=max_bytes)
    return data.decode("utf-8", "replace"), reason


def find_document_links(markup: str, base_url: str) -> list[str]:
    from html.parser import HTMLParser

    class Links(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.found: list[str] = []

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if tag != "a":
                return
            href = dict(attrs).get("href") or ""
            low = href.lower()
            if low.endswith(".pdf") or low.endswith(".epub"):
                self.found.append(urljoin(base_url, href))

    parser = Links()
    parser.feed(markup)
    unique: list[str] = []
    for item in parser.found:
        if item not in unique:
            unique.append(item)
    return unique
