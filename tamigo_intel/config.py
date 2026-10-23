from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from tamigo_intel.paths import config_path

DEFAULT_KEYWORDS = [
    "WCAG",
    "PDF accessibility",
    "EPUB accessibility",
    "Section 508",
    "accessibility remediation",
    "accessibility audit",
    "PDF/UA",
]

DEFAULT_WEIGHTS = {
    "evidence": 1.0,
    "recency": 1.0,
    "relevance": 1.0,
    "scale": 1.0,
    "procurement": 1.0,
    "activity": 1.0,
    "contact": 1.0,
    "geo": 1.0,
}


@dataclass
class SearchConfig:
    keywords: list[str] = field(default_factory=lambda: list(DEFAULT_KEYWORDS))
    priority_countries: list[str] = field(
        default_factory=lambda: ["US", "CA", "GB", "AU"]
    )
    deprioritized_countries: list[str] = field(
        default_factory=lambda: ["RS", "BA", "HR", "ME", "MK", "AL", "XK", "BG", "RO", "HU", "SI"]
    )
    exclude_deprioritized: bool = False
    categories: list[str] = field(default_factory=list)
    include_uncategorized: bool = True
    formats_focus: list[str] = field(default_factory=lambda: ["pdf", "epub", "web"])
    recency_days: int = 1825
    max_organizations: int = 40
    max_per_source: int = 15
    request_interval_seconds: float = 1.0
    enabled_sources: list[str] = field(
        default_factory=lambda: ["contracts_finder", "usaspending", "ted", "github_issues"]
    )
    excluded_names: list[str] = field(default_factory=list)
    excluded_domains: list[str] = field(default_factory=list)
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    sam_api_key: str = ""
    github_token: str = ""
    openai_api_key: str = ""
    openai_base_url: str = ""
    schedule_hours: int = 0

    def to_public_dict(self) -> dict:
        data = asdict(self)
        for key in ("sam_api_key", "github_token", "openai_api_key"):
            data[key] = "set" if data.get(key) else ""
        return data


def default_config() -> SearchConfig:
    return SearchConfig()


def load_config(path: Path | None = None) -> SearchConfig:
    target = path or config_path()
    if not target.exists():
        return default_config()
    raw = json.loads(target.read_text(encoding="utf-8"))
    known = {field.name for field in SearchConfig.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    filtered = {key: value for key, value in raw.items() if key in known}
    base = default_config()
    for key, value in filtered.items():
        setattr(base, key, value)
    if not base.weights:
        base.weights = dict(DEFAULT_WEIGHTS)
    return base


def save_config(config: SearchConfig, path: Path | None = None) -> None:
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(asdict(config), indent=2, ensure_ascii=False), encoding="utf-8")
