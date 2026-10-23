from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Protocol

from tamigo_intel.config import SearchConfig
from tamigo_intel.http_client import HttpClient


@dataclass
class Discovered:
    source_name: str
    source_record_id: str
    source_url: str
    organization_name: str
    country: str
    region: str = ""
    title: str = ""
    excerpt: str = ""
    explanation: str = ""
    limitations: str = ""
    kind: str = "procurement_notice"
    level: str = "D"
    published_at: str | None = None
    procurement_signal: str = "none"
    amount: float | None = None
    supplier_name: str = ""
    notice_status: str = ""
    currency: str = ""
    website: str = ""
    raw: dict = field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        payload = f"{self.title}|{self.excerpt}|{self.notice_status}|{self.amount}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def raw_json(self) -> str:
        return json.dumps(self.raw, ensure_ascii=False, default=str)[:20000]


class Source(Protocol):
    name: str

    def search(self, config: SearchConfig, client: HttpClient) -> list[Discovered]:
        ...
