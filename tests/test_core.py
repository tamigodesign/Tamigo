from __future__ import annotations

import csv
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tamigo_intel.ai import Claim, admit_claims, confirmed_only
from tamigo_intel.analysis.epub_check import analyze_epub
from tamigo_intel.analysis.fetch import find_document_links, robots_allow
from tamigo_intel.analysis.html_check import analyze_html
from tamigo_intel.analysis.pdf_check import analyze_pdf
from tamigo_intel.cancel import CancelToken
from tamigo_intel.config import SearchConfig
from tamigo_intel.contacts import published_emails
from tamigo_intel.db import Database
from tamigo_intel.exporting import export_csv, export_json
from tamigo_intel.http_client import HttpClient, HttpError
from tamigo_intel.monitor import should_run_scheduled
from tamigo_intel.pipeline import _store, run_search
from tamigo_intel.qualify import classify_without_evidence, score_lead
from tamigo_intel.redact import RedactFilter, redact
from tamigo_intel.sources.base import Discovered
from tamigo_intel.sources.contracts_finder import ContractsFinderSource
from tamigo_intel.sources.sam_gov import SamGovSource, SourceUnavailable
from tamigo_intel.sources.ted import TedSource
from tamigo_intel.sources.usaspending import UsaSpendingSource


def config() -> SearchConfig:
    return SearchConfig(keywords=["WCAG", "PDF accessibility"], request_interval_seconds=0, max_per_source=10, max_organizations=10)


def discovery(**kwargs) -> Discovered:
    base = dict(
        source_name="fixture",
        source_record_id="1",
        source_url="https://example.test/notice/1",
        organization_name="Example Agency",
        country="US",
        title="WCAG 2.2 remediation services",
        excerpt="Open request for PDF accessibility remediation and WCAG 2.2 AA.",
        explanation="Test trag.",
        limitations="Nije tehnički nalaz.",
        kind="procurement_notice",
        level="A",
        published_at="2026-01-15T00:00:00Z",
        procurement_signal="open_procurement",
        amount=120000,
    )
    base.update(kwargs)
    return Discovered(**base)


def test_side_mention_of_wcag_is_not_level_a():
    from tamigo_intel.terms import procurement_level

    catering = (
        "Supply of catering point-of-sale print. " * 30
        + "Artworks are required to meet accessibility guidelines: Understanding WCAG 2.2."
    )
    assert procurement_level("Catering print contract", catering) == "C"
    assert procurement_level("Accessibility audit of the public website", "WCAG 2.2 testing") == "A"


def test_sector_alone_is_not_a_compliance_judgment():
    score = classify_without_evidence("univerzitet")
    assert score.evidence_level == "D"
    assert score.compliance_judgment == "none"
    assert score.total_score == 0
    assert "nije ocena neusklađenosti" in score.explanation


def test_score_does_not_upgrade_weak_evidence():
    weak = score_lead(
        "Library",
        "US",
        [
            {
                "level": "C",
                "procurement_signal": "none",
                "published_at": "2026-02-01",
                "title": "Katalog",
                "excerpt": "digital accessibility requirement mentioned",
                "source_url": "https://example.test/a",
                "explanation": "indirektno",
                "limitations": "nema kvara",
                "kind": "indirect",
                "amount": 5_000_000,
                "formats": ["web"],
            }
        ],
    )
    assert weak.evidence_level == "C"
    assert weak.total_score > 40
    assert weak.compliance_judgment == "none"


def test_database_dedup_history_and_injection(tmp_path: Path):
    db = Database(tmp_path / "t.sqlite")
    cfg = config()
    with db.connect() as conn:
        first = _store(db, conn, discovery(organization_name="Agency'; DROP TABLE leads;--"), cfg)
        again = _store(db, conn, discovery(organization_name="Agency'; DROP TABLE leads;--"), cfg)
        changed = _store(
            db,
            conn,
            discovery(
                organization_name="Agency'; DROP TABLE leads;--",
                excerpt="Updated WCAG remediation excerpt with a new date.",
                source_record_id="1",
            ),
            cfg,
        )
        conn.commit()
    assert first == again == changed
    assert db.dashboard()["organizations"] == 1
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM evidence_history").fetchone()[0] == 1
        name = conn.execute("SELECT name FROM organizations").fetchone()["name"]
    assert "DROP TABLE" in name
    bundle = db.lead_bundle(1)
    assert bundle["lead"]["compliance_judgment"] == "none"
    assert len(bundle["evidence"]) == 1
    assert "https://example.test/notice/1" in bundle["evidence"][0]["source_url"]


def test_rescore_keeps_operator_verification(tmp_path: Path):
    db = Database(tmp_path / "t.sqlite")
    with db.connect() as conn:
        _store(db, conn, discovery(), config())
        conn.commit()
    db.update_lead_operator(1, "qualified", "provereno ručno", "2026-11-01", "manually_verified")
    with db.connect() as conn:
        _store(db, conn, discovery(source_record_id="2", title="Additional WCAG audit"), config())
        conn.commit()
    bundle = db.lead_bundle(1)
    assert bundle["lead"]["verification_status"] == "manually_verified"
    assert bundle["lead"]["status"] == "qualified"
    assert len(bundle["evidence"]) == 2


def test_irrelevant_sector_text_is_not_stored(tmp_path: Path):
    db = Database(tmp_path / "t.sqlite")
    item = discovery(
        organization_name="State University",
        title="Annual campus report",
        excerpt="The university published a catalog of courses.",
        level="D",
        kind="indirect",
    )
    with db.connect() as conn:
        assert _store(db, conn, item, config()) is None
        conn.commit()
    assert db.dashboard()["leads"] == 0


def test_unverified_email_is_not_exported_as_verified(tmp_path: Path):
    db = Database(tmp_path / "t.sqlite")
    with db.connect() as conn:
        _store(db, conn, discovery(excerpt="Write to press@example.test about WCAG remediation."), config())
        org_id = conn.execute("SELECT id FROM organizations").fetchone()["id"]
        db.add_contact(
            conn,
            {
                "organization_id": org_id,
                "name": "",
                "email": "guess@example.test",
                "email_verification": "unverified",
                "source_url": "https://example.test/guess",
                "notes": "nije objavljeno",
            },
        )
        conn.commit()
    # Prvi kontakt je objavljen u izvoru. Drugi je neverifikovan i ne sme biti prikazan kao verified.
    with db.connect() as conn:
        rows = list(conn.execute("SELECT email, email_verification FROM contacts ORDER BY id"))
    assert rows[0]["email_verification"] == "published_in_source"
    assert rows[1]["email_verification"] == "unverified"
    destination = tmp_path / "out.csv"
    export_csv(db, destination)
    text = destination.read_text(encoding="utf-8-sig")
    assert "unverified" not in text or "verified" in text
    with destination.open(encoding="utf-8-sig", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["email_verification"] in {"published_in_source", "unverified", "not_found"}
    assert row["email_verification"] != "verified"
    with db.connect() as conn:
        conn.execute("DELETE FROM contacts WHERE email_verification = 'published_in_source'")
        conn.commit()
    export_csv(db, destination)
    with destination.open(encoding="utf-8-sig", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["email"] == "guess@example.test"
    assert row["email_verification"] == "unverified"


def test_json_export_keeps_source_and_limitations(tmp_path: Path):
    db = Database(tmp_path / "t.sqlite")
    with db.connect() as conn:
        _store(db, conn, discovery(), config())
        conn.commit()
    path = tmp_path / "out.json"
    assert export_json(db, path, qualified_only=True) == 1
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data[0]["evidence"][0]["source_url"].startswith("https://")
    assert data[0]["compliance_judgment"] == "none"


def test_ai_claim_without_evidence_is_not_confirmed():
    claims = admit_claims([Claim(text="Ustanova krši WCAG.", status="paraphrase", evidence_ids=[])])
    assert claims[0].status == "not_verified"
    assert confirmed_only(claims) == []
    confirmed = confirmed_only([Claim(text="Oglas traži WCAG.", status="quoted", evidence_ids=[4], source_url="https://example.test")])
    assert len(confirmed) == 1


def test_contracts_finder_parser_skips_false_positive():
    payload = {
        "noticeList": [
            {
                "item": {
                    "id": "real-1",
                    "title": "WCAG 2.2 AA accessibility audit",
                    "description": "Accessibility audits for public services. Contact audits@example.test.",
                    "organisationName": "Government Digital Service",
                    "noticeStatus": "Open",
                    "deadlineDate": "2026-12-01T00:00:00Z",
                    "publishedDate": "2026-03-01T00:00:00Z",
                    "valueLow": 50000,
                    "regionText": "London",
                }
            },
            {
                "item": {
                    "id": "taxi",
                    "title": "Passenger assistant taxi",
                    "description": "School transport route.",
                    "organisationName": "East Sussex County Council",
                    "noticeStatus": "Open",
                    "publishedDate": "2026-03-01T00:00:00Z",
                }
            },
        ]
    }

    def transport(method, url, body, headers, timeout):
        return 200, json.dumps(payload).encode(), {}

    items = ContractsFinderSource().search(config(), HttpClient(transport=transport, min_interval=0))
    assert len(items) == 1
    assert items[0].organization_name == "Government Digital Service"
    assert items[0].procurement_signal == "open_procurement"
    assert items[0].level == "A"
    assert "audits@example.test" in items[0].excerpt


def test_usaspending_uses_agency_not_vendor():
    payload = {
        "results": [
            {
                "Award ID": "ABC",
                "generated_internal_id": "CONT_AWD_ABC",
                "Recipient Name": "LEVEL ACCESS INC",
                "Awarding Agency": "Department of Health and Human Services",
                "Description": "SECTION 508 ACCESSIBILITY COMPLIANCE TESTING AND REMEDIATION SERVICES",
                "Award Amount": 304585.67,
                "Start Date": "2024-11-20",
            }
        ]
    }

    def transport(method, url, body, headers, timeout):
        return 200, json.dumps(payload).encode(), {}

    items = UsaSpendingSource().search(config(), HttpClient(transport=transport, min_interval=0))
    assert items[0].organization_name == "Department of Health and Human Services"
    assert items[0].supplier_name == "LEVEL ACCESS INC"
    assert items[0].procurement_signal == "past_award"
    assert "CONT_AWD_ABC" in items[0].source_url


def test_ted_old_notice_is_not_marked_open():
    payload = {
        "notices": [
            {
                "publication-number": "787515-2023",
                "publication-date": "2023-12-26Z",
                "buyer-name": {"eng": ["Het Kadaster"]},
                "buyer-country": {"eng": ["NLD"]},
                "notice-title": {"eng": "Accessibility audits based on the WCAG"},
            }
        ]
    }

    def transport(method, url, body, headers, timeout):
        return 200, json.dumps(payload).encode(), {}

    items = TedSource().search(config(), HttpClient(transport=transport, min_interval=0))
    assert items[0].organization_name == "Het Kadaster"
    assert items[0].country == "NL"
    assert items[0].procurement_signal == "closed"
    assert items[0].source_url.endswith("787515-2023")


def test_sam_without_key_is_unavailable():
    with pytest.raises(SourceUnavailable):
        SamGovSource().search(config(), HttpClient(min_interval=0))


def test_source_failure_does_not_wipe_database(tmp_path: Path):
    db = Database(tmp_path / "t.sqlite")

    class Broken:
        name = "broken"

        def search(self, config, client):
            raise HttpError("mreža", status=503)

    class Good:
        name = "good"

        def search(self, config, client):
            return [discovery()]

    result = run_search(db, config(), sources=[Broken(), Good()], client=HttpClient(min_interval=0))
    assert result["status"] == "completed"
    assert result["stored"] == 1
    states = {row["source_name"]: row["last_status"] for row in db.dashboard()["sources"]}
    assert states["broken"] == "failed"
    assert states["good"] == "ok"


def test_cancel_keeps_committed_rows(tmp_path: Path):
    db = Database(tmp_path / "t.sqlite")
    token = CancelToken()

    class First:
        name = "first"

        def search(self, config, client):
            return [discovery(source_record_id="keep", organization_name="Kept Agency")]

    class Second:
        name = "second"

        def search(self, config, client):
            token.cancel()
            client.cancel = token
            return [discovery(source_record_id="drop", organization_name="Dropped Agency")]

    result = run_search(db, config(), sources=[First(), Second()], cancel=token, client=HttpClient(min_interval=0, cancel=token))
    assert result["status"] == "cancelled"
    names = [row["organization"] for row in db.query_leads()]
    assert names == ["Kept Agency"]


def test_html_pdf_epub_indicators(tmp_path: Path):
    html = analyze_html(
        "<html><head></head><body><img src='a.png'><input><button></button><h1>A</h1><h3>B</h3></body></html>"
    )
    rules = {item.rule_id for item in html.indicators}
    assert {"html-lang", "document-title", "img-alt", "input-name", "button-name", "heading-jump"} <= rules
    decorative = analyze_html("<html lang='en'><head><title>T</title></head><body><img alt=''></body></html>")
    assert decorative.indicators == []
    assert "ne znači" in decorative.notes

    from pypdf import PdfWriter

    pdf_path = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with pdf_path.open("wb") as handle:
        writer.write(handle)
    pdf = analyze_pdf(pdf_path)
    assert "pdf-unmarked" in {item.rule_id for item in pdf.indicators}
    assert pdf.conformance == "not_determined"
    broken = tmp_path / "bad.pdf"
    broken.write_bytes(b"not a pdf")
    assert analyze_pdf(broken).conformance == "not_run"

    epub = tmp_path / "book.epub"
    _write_epub(epub)
    epub_result = analyze_epub(epub)
    epub_rules = {item.rule_id for item in epub_result.indicators}
    assert "epub-language" in epub_rules
    assert "epub-nav" in epub_rules
    assert "epub-img-alt" in epub_rules
    assert all(item.status != "noncompliant" for item in epub_result.indicators)


def test_robots_and_document_links():
    pages = {
        "https://library.test/robots.txt": b"User-agent: *\nDisallow: /private\n",
        "https://blocked.test/robots.txt": b"nope",
    }

    def transport(method, url, body, headers, timeout):
        if url.endswith("/robots.txt") and "library.test" in url:
            return 200, pages[url], {}
        if "blocked.test" in url:
            return 403, b"forbidden", {}
        if url == "https://nodir.test/robots.txt":
            return 404, b"missing", {}
        return 200, b"<html></html>", {}

    client = HttpClient(transport=transport, min_interval=0)
    assert robots_allow("https://library.test/public", client)[0] is True
    assert robots_allow("https://library.test/private", client)[0] is False
    assert robots_allow("https://blocked.test/page", client)[0] is False
    assert robots_allow("https://nodir.test/page", HttpClient(transport=transport, min_interval=0))[0] is True
    links = find_document_links('<a href="/files/book.epub"></a><a href="https://x.test/a.PDF"></a>', "https://library.test/cat/")
    assert links == ["https://library.test/files/book.epub", "https://x.test/a.PDF"]


def test_retry_on_429_and_secret_redaction():
    calls = {"n": 0}

    def transport(method, url, body, headers, timeout):
        calls["n"] += 1
        if calls["n"] == 1:
            return 429, b"wait", {}
        return 200, b'{"ok": true}', {}

    client = HttpClient(transport=transport, min_interval=0, secrets=["super-secret"])
    assert client.get_json("https://api.example.test?api_key=super-secret") == {"ok": True}
    assert calls["n"] == 2
    assert "super-secret" not in redact("key super-secret and api_key=abcdef", ["super-secret"])
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "token super-secret", (), None)
    assert RedactFilter(["super-secret"]).filter(record)
    assert "super-secret" not in record.msg


def test_backup_and_schedule(tmp_path: Path):
    db = Database(tmp_path / "t.sqlite")
    with db.connect() as conn:
        _store(db, conn, discovery(), config())
        conn.commit()
    copy = tmp_path / "backup.sqlite"
    db.backup_to(copy)
    restored = Database(copy)
    assert restored.dashboard()["leads"] == 1
    now = datetime.now(timezone.utc)
    assert should_run_scheduled(now - timedelta(hours=2), 1, now, app_open=True) is True
    assert should_run_scheduled(now, 1, now, app_open=True) is False
    assert should_run_scheduled(None, 1, now, app_open=False) is False


def test_saved_search_roundtrip(tmp_path: Path):
    db = Database(tmp_path / "t.sqlite")
    db.save_search("wcag-us", '{"keywords": ["WCAG"], "max_organizations": 5}')
    rows = db.list_saved_searches()
    assert rows[0]["name"] == "wcag-us"
    with db.connect() as conn:
        raw = conn.execute("SELECT config_json FROM saved_searches").fetchone()["config_json"]
    assert json.loads(raw)["keywords"] == ["WCAG"]


def test_published_email_extractor():
    assert published_emails("Pišite na Office@Agency.gov.uk.") == ["Office@Agency.gov.uk"]


def _write_epub(path: Path) -> None:
    import zipfile

    container = """<?xml version='1.0'?>
    <container xmlns='urn:oasis:names:tc:opendocument:xmlns:container' version='1.0'>
      <rootfiles><rootfile full-path='OEBPS/content.opf' media-type='application/oebps-package+xml'/></rootfiles>
    </container>"""
    opf = """<?xml version='1.0'?>
    <package xmlns='http://www.idpf.org/2007/opf' version='3.0'>
      <metadata xmlns:dc='http://purl.org/dc/elements/1.1/'><dc:title>Book</dc:title></metadata>
      <manifest><item id='c' href='ch.xhtml' media-type='application/xhtml+xml'/></manifest>
    </package>"""
    chapter = "<html><body><img src='a.png'></body></html>"
    with zipfile.ZipFile(path, "w") as package:
        package.writestr("mimetype", "application/epub+zip")
        package.writestr("META-INF/container.xml", container)
        package.writestr("OEBPS/content.opf", opf)
        package.writestr("OEBPS/ch.xhtml", chapter)
