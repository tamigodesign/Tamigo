from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from tamigo_intel.paths import config_path
from tamigo_intel.vault import SECRET_FIELDS, default_vault

RECENCY_MIN = 1
RECENCY_MAX = 7300
DEFAULT_RECENCY_DAYS = 90
PREVIOUS_DEFAULT_RECENCY_DAYS = 1825
MAX_ORGS_MIN = 1
MAX_ORGS_MAX = 500
INTERVAL_MIN = 0
INTERVAL_MAX = 30

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
    recency_days: int = DEFAULT_RECENCY_DAYS
    max_organizations: int = 40
    max_per_source: int = 15
    request_interval_seconds: float = 1.0
    enabled_sources: list[str] = field(
        default_factory=lambda: ["contracts_finder", "usaspending", "canada_buys", "ted", "github_issues"]
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


class ConfigError(ValueError):
    pass


def validate_limits(config: SearchConfig) -> None:
    errors: list[str] = []
    _check_int(config.recency_days, "Period unazad", RECENCY_MIN, RECENCY_MAX, errors)
    _check_int(config.max_organizations, "Najviše ustanova", MAX_ORGS_MIN, MAX_ORGS_MAX, errors)
    _check_int(config.max_per_source, "Najviše po izvoru", 1, 100, errors)
    if isinstance(config.request_interval_seconds, bool) or not isinstance(config.request_interval_seconds, (int, float)):
        errors.append("Pauza između zahteva mora biti broj.")
    elif config.request_interval_seconds < INTERVAL_MIN or config.request_interval_seconds > INTERVAL_MAX:
        errors.append(f"Pauza između zahteva je od {INTERVAL_MIN} do {INTERVAL_MAX} sekundi.")
    if errors:
        raise ConfigError(" ".join(errors))


def _check_int(value: object, label: str, low: int, high: int, errors: list[str]) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        errors.append(f"{label} mora biti ceo broj od {low} do {high}.")
        return
    if value < low or value > high:
        errors.append(f"{label} mora biti od {low} do {high}.")


def load_config(path: Path | None = None, vault=None) -> SearchConfig:
    target = path or config_path()
    store = vault or default_vault()
    if not target.exists():
        config = default_config()
        _load_secrets(config, store)
        return config
    raw = json.loads(target.read_text(encoding="utf-8"))
    known = {field.name for field in SearchConfig.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    filtered = {key: value for key, value in raw.items() if key in known}
    base = default_config()
    for key, value in filtered.items():
        setattr(base, key, value)
    if not base.weights:
        base.weights = dict(DEFAULT_WEIGHTS)
    revision = int(raw.get("defaults_revision") or 1)
    migrated_default = False
    if revision < 2 and base.recency_days == PREVIOUS_DEFAULT_RECENCY_DAYS:
        base.recency_days = DEFAULT_RECENCY_DAYS
        migrated_default = True
    migrated_secret = False
    for field_name in SECRET_FIELDS:
        leftover = str(filtered.get(field_name) or "")
        if leftover:
            store.set(field_name, leftover)
            migrated_secret = True
    _load_secrets(base, store)
    if migrated_default or migrated_secret or revision < 2:
        save_config(base, target, store)
    return base


def _load_secrets(config: SearchConfig, vault) -> None:
    for field_name in SECRET_FIELDS:
        try:
            value = vault.get(field_name) or ""
        except Exception:
            value = ""
        setattr(config, field_name, value)


def save_config(config: SearchConfig, path: Path | None = None, vault=None) -> None:
    target = path or config_path()
    store = vault or default_vault()
    for field_name in SECRET_FIELDS:
        try:
            store.set(field_name, getattr(config, field_name) or "")
        except Exception:
            if getattr(config, field_name):
                raise
    data = asdict(config)
    for field_name in SECRET_FIELDS:
        data[field_name] = ""
    data["defaults_revision"] = 2
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
