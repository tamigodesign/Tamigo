from __future__ import annotations

import json
import logging
from pathlib import Path

from tamigo_intel.analysis.common import AnalysisResult
from tamigo_intel.analysis.epub_check import analyze_epub
from tamigo_intel.analysis.html_check import analyze_html
from tamigo_intel.analysis.pdf_check import analyze_pdf
from tamigo_intel.cancel import Cancelled, CancelToken
from tamigo_intel.config import SearchConfig, validate_limits
from tamigo_intel.contacts import contact_from_discovery
from tamigo_intel.db import Database, utc_now
from tamigo_intel.http_client import HttpClient, HttpError
from tamigo_intel.qualify import score_lead
from tamigo_intel.redact import redact
from tamigo_intel.sources.base import Discovered
from tamigo_intel.sources.canada_buys import CanadaBuysSource
from tamigo_intel.sources.contracts_finder import ContractsFinderSource
from tamigo_intel.sources.github_issues import GitHubIssuesSource
from tamigo_intel.sources.sam_gov import SamGovSource, SourceUnavailable
from tamigo_intel.sources.ted import TedSource
from tamigo_intel.sources.usaspending import UsaSpendingSource
from tamigo_intel.status_text import outcome_label, overall_status
from tamigo_intel.terms import clean_text, detect_formats, infer_category, normalize_name, relevant

log = logging.getLogger("tamigo_intel")

SOURCE_TYPES = {
    "contracts_finder": ContractsFinderSource,
    "usaspending": UsaSpendingSource,
    "canada_buys": CanadaBuysSource,
    "ted": TedSource,
    "github_issues": GitHubIssuesSource,
    "sam_gov": SamGovSource,
}


def build_sources(config: SearchConfig) -> list:
    sources = []
    for name in config.enabled_sources:
        factory = SOURCE_TYPES.get(name)
        if factory:
            sources.append(factory())
    return sources


def _excluded(item: Discovered, config: SearchConfig) -> bool:
    name = normalize_name(item.organization_name)
    if any(normalize_name(blocked) == name for blocked in config.excluded_names):
        return True
    domain = (item.website or "").lower()
    return any(blocked.lower() in domain for blocked in config.excluded_domains if blocked)


def _category_allowed(category: str, verification: str, config: SearchConfig) -> bool:
    if not config.categories:
        return True
    if category in config.categories:
        return True
    return config.include_uncategorized and verification == "not_verified"


def _store(db: Database, conn, item: Discovered, config: SearchConfig) -> int | None:
    if item.kind != "technical_finding" and not relevant(f"{item.title} {item.excerpt}", config.keywords):
        return None
    category, category_verification = infer_category(item.organization_name, f"{item.title} {item.excerpt}")
    if not _category_allowed(category, category_verification, config):
        return None
    if config.exclude_deprioritized and (item.country or "").upper() in {c.upper() for c in config.deprioritized_countries}:
        return None
    formats = detect_formats(f"{item.title} {item.excerpt}")
    if config.formats_focus and formats and not set(formats) & set(config.formats_focus):
        return None
    org_id = db.upsert_organization(
        conn,
        {
            "name": clean_text(item.organization_name, 300),
            "normalized_name": normalize_name(item.organization_name),
            "country": item.country or "",
            "region": item.region,
            "category": category,
            "category_verification": category_verification,
            "website": item.website,
        },
    )
    evidence_id, changed = db.add_or_update_evidence(
        conn,
        {
            "organization_id": org_id,
            "kind": item.kind,
            "level": item.level,
            "title": item.title,
            "excerpt": item.excerpt,
            "explanation": item.explanation,
            "limitations": item.limitations,
            "source_name": item.source_name,
            "source_record_id": item.source_record_id,
            "source_url": item.source_url,
            "published_at": item.published_at,
            "content_hash": item.content_hash,
            "procurement_signal": item.procurement_signal,
            "amount": item.amount,
            "formats": formats,
            "raw_json": item.raw_json(),
        },
    )
    if item.kind in {"procurement_notice", "award"}:
        db.add_procurement(
            conn,
            {
                "evidence_id": evidence_id,
                "notice_status": item.notice_status,
                "buyer_name": item.organization_name,
                "supplier_name": item.supplier_name,
                "amount": "" if item.amount is None else str(item.amount),
                "currency": item.currency,
                "country": item.country,
            },
        )
    contact = contact_from_discovery(
        org_id,
        item.source_url,
        f"{item.title}\n{item.excerpt}",
        item.organization_name,
        email=item.contact_email,
        name=item.contact_name,
    )
    has_contact = False
    if contact:
        db.add_contact(conn, contact)
        has_contact = contact["email_verification"] == "published_in_source"
    lead_id = db.ensure_lead(conn, org_id)
    rows = db.evidence_for_org(conn, org_id)
    org = conn.execute("SELECT name, country FROM organizations WHERE id = ?", (org_id,)).fetchone()
    scored = score_lead(
        org["name"],
        org["country"],
        rows,
        weights=config.weights,
        priority_countries=config.priority_countries,
        deprioritized_countries=config.deprioritized_countries,
        has_published_contact=has_contact or _has_published_contact(conn, org_id),
    )
    db.save_score(conn, lead_id, scored.__dict__)
    if changed:
        db.add_event(conn, lead_id, "evidence", f"{item.source_name}:{item.source_record_id}")
    return org_id


def _has_published_contact(conn, organization_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM contacts WHERE organization_id = ? AND email_verification = 'published_in_source'",
        (organization_id,),
    ).fetchone()
    return row is not None


def run_search(
    db: Database,
    config: SearchConfig,
    client: HttpClient | None = None,
    cancel: CancelToken | None = None,
    sources: list | None = None,
    on_progress=None,
) -> dict:
    def progress(message: str) -> None:
        log.info(message)
        if on_progress:
            on_progress(message)

    validate_limits(config)
    cancel = cancel or CancelToken()
    client = client or HttpClient(min_interval=config.request_interval_seconds, cancel=cancel, secrets=_secrets(config))
    client.cancel = cancel
    client.secrets = _secrets(config)
    run_id = db.start_run(json.dumps(config.to_public_dict(), ensure_ascii=False))
    lines: list[str] = []
    reports: list[dict] = []
    seen_orgs: set[int] = set()
    chosen = build_sources(config) if sources is None else list(sources)
    try:
        if not chosen:
            lines.append("Nijedan izvor nije uključen, pa nema uspešnog upita.")
            progress(lines[-1])
        for source in chosen:
            cancel.raise_if_cancelled()
            progress(f"Izvor {source.name} počinje.")
            try:
                items = source.search(config, client)
            except Cancelled:
                raise
            except SourceUnavailable as exc:
                message = _safe(exc, config)
                db.set_source_state(source.name, "unavailable", message, 0)
                reports.append({"name": source.name, "status": "unavailable", "count": 0, "error": message})
                lines.append(f"{source.name}: nedostupan. {message}")
                progress(lines[-1])
                continue
            except (HttpError, OSError, ValueError, KeyError) as exc:
                message = _safe(exc, config)
                db.set_source_state(source.name, "failed", message, 0)
                reports.append({"name": source.name, "status": "failed", "count": 0, "error": message})
                lines.append(f"{source.name}: greška. {message}")
                progress(lines[-1])
                continue
            stored_here = 0
            with db.connect() as conn:
                for item in items:
                    cancel.raise_if_cancelled()
                    if _excluded(item, config):
                        continue
                    if len(seen_orgs) >= config.max_organizations:
                        break
                    org_id = _store(db, conn, item, config)
                    conn.commit()
                    if org_id and org_id not in seen_orgs:
                        seen_orgs.add(org_id)
                        stored_here += 1
                        progress(f"Sačuvan trag: {item.organization_name} ({item.source_name})")
            db.set_source_state(source.name, "ok", "", len(items))
            reports.append(
                {"name": source.name, "status": "ok", "count": len(items), "stored": stored_here, "error": ""}
            )
            lines.append(f"{source.name}: uspeo, odgovor {len(items)}, sačuvanih ustanova {stored_here}.")
            progress(lines[-1])
            if len(seen_orgs) >= config.max_organizations:
                lines.append("Dostignut je zadati maksimum ustanova. Ostali izvori nisu pitani i nisu neuspeh.")
                progress(lines[-1])
                break
        status = overall_status(reports, len(seen_orgs))
        summary = outcome_label(status)
        lines.append(summary)
        progress(summary)
        db.finish_run(run_id, status, "\n".join(lines))
        return {
            "status": status,
            "stored": len(seen_orgs),
            "run_id": run_id,
            "log": lines,
            "sources": reports,
        }
    except Cancelled:
        lines.append(outcome_label("cancelled"))
        db.finish_run(run_id, "cancelled", "\n".join(lines))
        return {"status": "cancelled", "stored": len(seen_orgs), "run_id": run_id, "log": lines, "sources": reports}
    except Exception as exc:
        message = _safe(exc, config)
        lines.append(message)
        db.finish_run(run_id, "error", "\n".join(lines), message)
        raise


def _safe(exc: Exception, config: SearchConfig) -> str:
    return redact(str(exc), _secrets(config))


def _secrets(config: SearchConfig) -> list[str]:
    return [value for value in (config.sam_api_key, config.github_token, config.openai_api_key) if value]


def attach_analysis(db: Database, organization_id: int, result: AnalysisResult, source_url: str, config: SearchConfig, local_path: str = "") -> int | None:
    with db.connect() as conn:
        document_id = db.add_document(
            conn,
            {
                "organization_id": organization_id,
                "url": source_url,
                "format": result.format,
                "reason": "Ručno pokrenuta provera javnog ili lokalnog fajla.",
                "local_path": local_path,
                "analysis_json": json.dumps(
                    {"conformance": result.conformance, "notes": result.notes, "limitations": result.limitations},
                    ensure_ascii=False,
                ),
            },
        )
        evidence_id = None
        if result.indicators:
            summaries = "; ".join(item.summary for item in result.indicators)
            from tamigo_intel.sources.base import Discovered

            item = Discovered(
                source_name=f"local_{result.format}",
                source_record_id=hashlib_of(source_url, summaries),
                source_url=source_url or f"file://{local_path}",
                organization_name=conn.execute("SELECT name FROM organizations WHERE id = ?", (organization_id,)).fetchone()["name"],
                country=conn.execute("SELECT country FROM organizations WHERE id = ?", (organization_id,)).fetchone()["country"],
                title=f"Automatski indikatori ({result.format})",
                excerpt=summaries,
                explanation="Alat je prijavio tehnički indikator na dostavljenom fajlu.",
                limitations=result.limitations,
                kind="technical_finding",
                level="B",
                published_at=utc_now(),
                raw={"notes": result.notes},
            )
            evidence_id, _changed = db.add_or_update_evidence(
                conn,
                {
                    "organization_id": organization_id,
                    "kind": item.kind,
                    "level": "B",
                    "title": item.title,
                    "excerpt": item.excerpt,
                    "explanation": item.explanation,
                    "limitations": item.limitations,
                    "source_name": item.source_name,
                    "source_record_id": item.source_record_id,
                    "source_url": item.source_url,
                    "published_at": item.published_at,
                    "content_hash": item.content_hash,
                    "procurement_signal": "none",
                    "amount": None,
                    "formats": [result.format if result.format in {"pdf", "epub"} else "web"],
                    "raw_json": item.raw_json(),
                },
            )
            for indicator in result.indicators:
                db.add_finding(
                    conn,
                    {
                        "document_id": document_id,
                        "evidence_id": evidence_id,
                        "tool": indicator.tool,
                        "rule_id": indicator.rule_id,
                        "summary": indicator.summary,
                        "status": indicator.status,
                        "wcag_hint": indicator.wcag_hint,
                        "details": indicator.details,
                    },
                )
            lead_id = db.ensure_lead(conn, organization_id)
            org = conn.execute("SELECT name, country FROM organizations WHERE id = ?", (organization_id,)).fetchone()
            scored = score_lead(
                org["name"],
                org["country"],
                db.evidence_for_org(conn, organization_id),
                weights=config.weights,
                priority_countries=config.priority_countries,
                deprioritized_countries=config.deprioritized_countries,
            )
            db.save_score(conn, lead_id, scored.__dict__)
        else:
            lead_id = db.ensure_lead(conn, organization_id)
            db.add_event(
                conn,
                lead_id,
                "analysis_clear",
                "Automatska provera nije prijavila indikatore. To ne znači usklađenost. " + result.limitations,
            )
        conn.commit()
        return evidence_id


def hashlib_of(*parts: str) -> str:
    import hashlib

    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]


def analyze_path(db: Database, organization_id: int, path: Path, config: SearchConfig) -> AnalysisResult:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        result = analyze_pdf(path)
    elif suffix == ".epub":
        result = analyze_epub(path)
    elif suffix in {".html", ".htm", ".xhtml"}:
        result = analyze_html(path.read_text(encoding="utf-8", errors="replace"))
    else:
        result = AnalysisResult(format=suffix.lstrip(".") or "unknown", conformance="not_run", notes="Format nije podržan.")
    attach_analysis(db, organization_id, result, "", config, local_path=str(path))
    return result
