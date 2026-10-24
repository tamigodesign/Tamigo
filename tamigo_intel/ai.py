from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Claim:
    text: str
    status: str
    evidence_ids: list[int]
    source_url: str = ""

    @property
    def confirmed(self) -> bool:
        return self.status in {"quoted", "paraphrase", "test_result"} and bool(self.evidence_ids)


def admit_claims(claims: list[Claim]) -> list[Claim]:
    """Tvrdnja bez izvora ne može ostati potvrđena."""
    admitted: list[Claim] = []
    for claim in claims:
        if claim.status in {"quoted", "paraphrase", "test_result"} and not claim.evidence_ids:
            admitted.append(
                Claim(
                    text=claim.text,
                    status="not_verified",
                    evidence_ids=[],
                    source_url=claim.source_url,
                )
            )
        elif claim.status not in {"quoted", "paraphrase", "test_result", "hypothesis", "not_verified"}:
            admitted.append(Claim(text=claim.text, status="not_verified", evidence_ids=[], source_url=claim.source_url))
        else:
            admitted.append(claim)
    return admitted


def confirmed_only(claims: list[Claim]) -> list[Claim]:
    return [claim for claim in admit_claims(claims) if claim.confirmed]


def rule_based_claims(evidence_rows: list[dict]) -> list[Claim]:
    claims: list[Claim] = []
    for row in evidence_rows:
        claims.append(
            Claim(
                text=row.get("excerpt") or row.get("title") or "",
                status="paraphrase",
                evidence_ids=[int(row["id"])] if row.get("id") else [],
                source_url=row.get("source_url") or "",
            )
        )
    claims.append(
        Claim(
            text="Postojanje traga ne znači da ustanova namerava da kupi uslugu.",
            status="hypothesis",
            evidence_ids=[],
        )
    )
    return admit_claims(claims)


class OptionalSummarizer:
    """LLM je isključen dok operator ne unese ključ. Podrazumevani rezime je iz pravila."""

    def __init__(self, api_key: str = "", base_url: str = "") -> None:
        self.api_key = api_key
        self.base_url = base_url

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.base_url)

    def summarize(self, evidence_rows: list[dict]) -> list[Claim]:
        if not self.enabled:
            return rule_based_claims(evidence_rows)
        return rule_based_claims(evidence_rows)
