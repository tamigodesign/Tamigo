from __future__ import annotations

import json
from datetime import datetime, timezone

from tamigo_intel.config import SearchConfig
from tamigo_intel.contacts import contact_from_discovery
from tamigo_intel.http_client import HttpClient
from tamigo_intel.sources.canada_buys import (
    CanadaBuysSource,
    award_csv_urls,
    notice_url,
    parse_canada_csv,
)


OPEN = """referenceNumber-numeroReference,amendmentNumber-numeroModification,title-titre-eng,tenderDescription-descriptionAppelOffres-eng,publicationDate-datePublication,tenderClosingDate-appelOffresDateCloture,tenderStatus-appelOffresStatut-eng,contractingEntityName-nomEntitContractante-eng,contractingEntityAddressProvince-entiteContractanteAdresseProvince-eng,contactInfoName-informationsContactNom,contactInfoEmail-informationsContactCourriel,noticeURL-URLavis-eng,endUserEntitiesName-nomEntitesUtilisateurFinal-eng
cb-100,000,WCAG 2.2 remediation of public PDFs,Request for PDF accessibility remediation against WCAG 2.2.,2026-10-01,2026-11-15T14:00:00,Open,Library and Archives Canada,ON,Ada Public,ada.public@example.gc.ca,https://example.test/external,
cb-200,000,Catering for a conference,Meals and rooms. {padding} Artworks must follow brand guidelines and mention WCAG only as a late clause.,2026-10-02,2026-11-01T14:00:00,Open,Parks Canada,BC,,,,
cb-300,000,Snow removal,Plow the parking lot before Monday.,2026-10-03,2026-10-20T14:00:00,Open,Public Services and Procurement Canada,QC,,,,
"""

AWARD = """referenceNumber-numeroReference,amendmentNumber-numeroModification,title-titre-eng,awardDescription-descriptionAttribution-eng,publicationDate-datePublication,contractAwardDate-dateAttributionContrat,awardStatus-attributionStatut-eng,contractingEntityName-nomEntitContractante-eng,endUserEntitiesName-nomEntitesUtilisateurFinal-eng,supplierLegalName-nomLegalFournisseur-eng,totalContractValue-valeurTotaleContrat,contractAmount-montantContrat,contractCurrency-contratMonnaie,contactInfoName-informationsContactNom,contactInfoEmail-informationsContactCourriel,contractingEntityAddressProvince-entiteContractanteAdresseProvince-eng
cb-748,001,Application of Accessibility Standards,Standing Offer for Accessibility Services (Stream 1: Creation of accessible PDFs),2026-06-02,2026-06-08,Active,Public Services and Procurement Canada,Department of Natural Resources,Accurate Design and Communication Inc.,0.00,0.00,CAD,Marie Example,marie.example@nrcan-rncan.gc.ca,ON
cb-900,000,ACCESSIBILITY TESTING,Addendum for accessibility testing of the public website.,2026-05-11,2026-03-04,Active,Department of Fisheries and Oceans,Department of Fisheries and Oceans,Fable Example Inc.,45200.00,0.00,CAD,Meenu Example,meenu.example@dfo-mpo.gc.ca,ON
cb-901,000,Cancelled accessibility audit,The accessibility audit was cancelled before award.,2024-01-01,2024-01-02,Cancelled,Health Canada,,Vendor Inc.,1000,1000,CAD,,,ON
"""


def config() -> SearchConfig:
    return SearchConfig(
        keywords=["WCAG", "PDF accessibility", "accessibility remediation", "accessibility audit"],
        recency_days=1825,
        max_per_source=10,
        request_interval_seconds=0,
    )


def test_award_urls_cover_two_latest_fiscal_years():
    now = datetime(2026, 10, 23, tzinfo=timezone.utc)
    urls = award_csv_urls(now, 1825)
    assert urls == [
        "https://canadabuys.canada.ca/opendata/pub/2026-2027-awardNotice-avisAttribution.csv",
        "https://canadabuys.canada.ca/opendata/pub/2025-2026-awardNotice-avisAttribution.csv",
    ]
    assert award_csv_urls(now, 30) == [
        "https://canadabuys.canada.ca/opendata/pub/2026-2027-awardNotice-avisAttribution.csv"
    ]


def test_notice_url_matches_the_public_page_pattern():
    assert notice_url("cb-748-24542208", "award") == (
        "https://canadabuys.canada.ca/en/tender-opportunities/award-notice/cb-748-24542208"
    )
    assert notice_url("MX-443841357513", "tender").endswith("/tender-notice/MX-443841357513")


def test_open_notice_is_not_an_award_and_side_mention_stays_c():
    text = OPEN.format(padding="note " * 80)
    found = parse_canada_csv(
        text,
        "tender",
        config(),
        "https://canadabuys.canada.ca/opendata/pub/openTenderNotice-ouvertAvisAppelOffres.csv",
        datetime(2026, 10, 23, tzinfo=timezone.utc),
    )
    by_id = {item.source_record_id: item for item in found}
    assert "cb-300:0" not in by_id
    primary = by_id["cb-100:000"]
    assert primary.procurement_signal == "open_procurement"
    assert primary.level == "A"
    assert primary.organization_name == "Library and Archives Canada"
    assert primary.country == "CA"
    assert primary.contact_email == "ada.public@example.gc.ca"
    assert primary.supplier_name == ""
    side = by_id["cb-200:000"]
    assert side.level == "C"
    assert side.procurement_signal == "open_procurement"


def test_award_keeps_buyer_not_supplier_and_zero_amount_is_absent():
    found = parse_canada_csv(
        AWARD,
        "award",
        config(),
        "https://canadabuys.canada.ca/opendata/pub/2026-2027-awardNotice-avisAttribution.csv",
        datetime(2026, 10, 23, tzinfo=timezone.utc),
    )
    by_ref = {item.source_record_id.split(":")[0]: item for item in found}
    nrcan = by_ref["cb-748"]
    assert nrcan.organization_name == "Department of Natural Resources"
    assert nrcan.supplier_name == "Accurate Design and Communication Inc."
    assert "Accurate Design" not in nrcan.organization_name
    assert nrcan.procurement_signal == "past_award"
    assert nrcan.level == "A"
    assert nrcan.amount is None
    assert "nije otvoren poziv" in nrcan.limitations.lower() or "Dodele nisu otvoren poziv" in nrcan.limitations
    assert nrcan.source_url.endswith("/award-notice/cb-748")
    contact = contact_from_discovery(1, nrcan.source_url, nrcan.excerpt, nrcan.organization_name, email=nrcan.contact_email, name=nrcan.contact_name)
    assert contact is not None
    assert contact["email"] == "marie.example@nrcan-rncan.gc.ca"
    assert contact["name"] == "Marie Example"
    assert contact["email_verification"] == "published_in_source"
    dfo = by_ref["cb-900"]
    assert dfo.organization_name == "Department of Fisheries and Oceans"
    assert dfo.amount == 45200.0
    assert dfo.procurement_signal == "past_award"
    cancelled = by_ref["cb-901"]
    assert cancelled.procurement_signal == "closed"
    assert cancelled.procurement_signal != "open_procurement"


def test_source_reads_bytes_and_skips_a_truncated_file(monkeypatch):
    now = datetime(2026, 10, 23, tzinfo=timezone.utc)
    pages = {
        "https://canadabuys.canada.ca/opendata/pub/openTenderNotice-ouvertAvisAppelOffres.csv": OPEN.format(padding="note"),
        "https://canadabuys.canada.ca/opendata/pub/2026-2027-awardNotice-avisAttribution.csv": AWARD,
    }

    def transport(method, url, body, headers, timeout):
        if url not in pages:
            return 404, b"missing", {}
        return 200, pages[url].encode("utf-8"), {"Content-Type": "text/csv"}

    client = HttpClient(transport=transport, min_interval=0)
    found = CanadaBuysSource().search(config(), client, now=now)
    names = {item.organization_name for item in found}
    assert "Library and Archives Canada" in names
    assert "Department of Natural Resources" in names
    assert all(item.organization_name != "Accurate Design and Communication Inc." for item in found)
    assert all(item.procurement_signal != "open_procurement" or item.kind == "procurement_notice" for item in found)
    raw = json.loads(found[0].raw_json())
    assert raw["file_url"].startswith("https://canadabuys.canada.ca/opendata/pub/")

    award_bytes = AWARD.encode("utf-8")
    monkeypatch.setattr("tamigo_intel.sources.canada_buys.FILE_CAP", len(award_bytes) + 8)

    def truncated(method, url, body, headers, timeout):
        if url.endswith("openTenderNotice-ouvertAvisAppelOffres.csv"):
            return 200, b"x" * (len(award_bytes) + 8), {}
        if url.endswith("2026-2027-awardNotice-avisAttribution.csv"):
            return 200, award_bytes, {}
        return 404, b"missing", {}

    kept = CanadaBuysSource().search(config(), HttpClient(transport=truncated, min_interval=0), now=now)
    assert any(item.organization_name == "Department of Natural Resources" for item in kept)
    assert all("Deo fajlova nije preuzet" in item.limitations for item in kept)
    assert all(item.organization_name != "Library and Archives Canada" for item in kept)
