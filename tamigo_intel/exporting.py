from __future__ import annotations

import csv
import json
from pathlib import Path

from tamigo_intel.classification import evidence_label, opportunity_label
from tamigo_intel.db import Database
from tamigo_intel.terms import procurement_label


def _contact_cell(contacts: list[dict]) -> tuple[str, str]:
    if not contacts:
        return "", "not_found"
    contact = contacts[0]
    verification = contact.get("email_verification") or "not_found"
    if verification != "published_in_source":
        verification = verification if verification in {"unverified", "not_found", "published_in_source"} else "unverified"
    return contact.get("email") or "", verification


def export_json(db: Database, destination: Path, qualified_only: bool = False) -> int:
    rows = []
    for bundle in db.export_rows(qualified_only=qualified_only):
        lead = bundle["lead"]
        email, verification = _contact_cell(bundle["contacts"])
        rows.append(
            {
                "organization": lead["organization"],
                "country": lead["country"],
                "website": lead["website"],
                "category": lead["category"],
                "category_verification": lead["category_verification"],
                "evidence_level": lead["evidence_level"],
                "total_score": lead["total_score"],
                "procurement_signal": lead["procurement_signal"],
                "evidence_timing": procurement_label(lead["procurement_signal"]),
                "formats": lead["formats"],
                "verification_status": lead["verification_status"],
                "compliance_judgment": lead["compliance_judgment"],
                "summary": lead["summary"],
                "next_action": lead["next_action"],
                "email": email,
                "email_verification": verification,
                "evidence_class": evidence_label(lead["evidence_level"], lead["procurement_signal"]),
                "opportunity_status": opportunity_label(lead["procurement_signal"]),
                "evidence": [
                    {
                        "title": item["title"],
                        "excerpt": item["excerpt"],
                        "source_url": item["source_url"],
                        "discovered_at": item["discovered_at"],
                        "published_at": item["published_at"],
                        "level": item["level"],
                        "limitations": item["limitations"],
                        "explanation": item["explanation"],
                    }
                    for item in bundle["evidence"]
                ],
            }
        )
    destination.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(rows)


def export_csv(db: Database, destination: Path, qualified_only: bool = False) -> int:
    bundles = db.export_rows(qualified_only=qualified_only)
    fieldnames = [
        "organization",
        "country",
        "website",
        "category",
        "evidence_level",
        "total_score",
        "procurement_signal",
        "evidence_timing",
        "formats",
        "verification_status",
        "email",
        "email_verification",
        "source_urls",
        "evidence_titles",
        "discovered_at",
        "limitations",
        "next_action",
        "evidence_class",
        "opportunity_status",
    ]
    with destination.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for bundle in bundles:
            lead = bundle["lead"]
            email, verification = _contact_cell(bundle["contacts"])
            if verification == "unverified":
                assert verification != "verified"
            writer.writerow(
                {
                    "organization": lead["organization"],
                    "country": lead["country"],
                    "website": lead["website"],
                    "category": lead["category"],
                    "evidence_level": lead["evidence_level"],
                    "total_score": lead["total_score"],
                    "procurement_signal": lead["procurement_signal"],
                    "evidence_timing": procurement_label(lead["procurement_signal"]),
                    "formats": lead["formats"],
                    "verification_status": lead["verification_status"],
                    "email": email,
                    "email_verification": verification,
                    "source_urls": " | ".join(item["source_url"] for item in bundle["evidence"]),
                    "evidence_titles": " | ".join(item["title"] for item in bundle["evidence"]),
                    "discovered_at": " | ".join(item["discovered_at"] or "" for item in bundle["evidence"]),
                    "limitations": " | ".join(item["limitations"] for item in bundle["evidence"]),
                    "next_action": lead["next_action"],
                    "evidence_class": evidence_label(lead["evidence_level"], lead["procurement_signal"]),
                    "opportunity_status": opportunity_label(lead["procurement_signal"]),
                }
            )
    return len(bundles)
