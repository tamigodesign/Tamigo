from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS organizations (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    country TEXT NOT NULL DEFAULT '',
    region TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    category_verification TEXT NOT NULL DEFAULT 'not_verified',
    website TEXT NOT NULL DEFAULT '',
    domain TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(normalized_name, country)
);

CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    status TEXT NOT NULL DEFAULT 'new',
    evidence_level TEXT NOT NULL,
    evidence_strength INTEGER NOT NULL,
    recency_score INTEGER NOT NULL,
    relevance_score INTEGER NOT NULL,
    scale_score INTEGER NOT NULL,
    procurement_score INTEGER NOT NULL,
    activity_score INTEGER NOT NULL,
    contact_score INTEGER NOT NULL,
    geo_score INTEGER NOT NULL,
    total_score INTEGER NOT NULL,
    score_explanation TEXT NOT NULL,
    summary TEXT NOT NULL,
    procurement_signal TEXT NOT NULL,
    formats TEXT NOT NULL,
    verification_status TEXT NOT NULL,
    compliance_judgment TEXT NOT NULL DEFAULT 'none',
    next_action TEXT NOT NULL,
    follow_up_on TEXT,
    user_notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(organization_id)
);

CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    lead_id INTEGER REFERENCES leads(id),
    kind TEXT NOT NULL,
    level TEXT NOT NULL,
    title TEXT NOT NULL,
    excerpt TEXT NOT NULL,
    explanation TEXT NOT NULL,
    limitations TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    published_at TEXT,
    discovered_at TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    procurement_signal TEXT NOT NULL DEFAULT 'none',
    amount REAL,
    formats TEXT NOT NULL DEFAULT '',
    raw_json TEXT NOT NULL,
    UNIQUE(source_name, source_record_id)
);

CREATE TABLE IF NOT EXISTS evidence_history (
    id INTEGER PRIMARY KEY,
    evidence_id INTEGER NOT NULL REFERENCES evidence(id),
    recorded_at TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    title TEXT NOT NULL,
    excerpt TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    name TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    department TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    email_verification TEXT NOT NULL DEFAULT 'not_found',
    profile_url TEXT NOT NULL DEFAULT '',
    department_url TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL,
    verified_at TEXT,
    notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    organization_id INTEGER REFERENCES organizations(id),
    url TEXT NOT NULL DEFAULT '',
    format TEXT NOT NULL,
    host_name TEXT NOT NULL DEFAULT '',
    discovered_at TEXT NOT NULL,
    reason TEXT NOT NULL,
    local_path TEXT NOT NULL DEFAULT '',
    analysis_json TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id),
    evidence_id INTEGER REFERENCES evidence(id),
    tool TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    summary TEXT NOT NULL,
    status TEXT NOT NULL,
    wcag_hint TEXT NOT NULL DEFAULT '',
    details TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS procurement_notices (
    id INTEGER PRIMARY KEY,
    evidence_id INTEGER NOT NULL REFERENCES evidence(id),
    notice_status TEXT NOT NULL,
    buyer_name TEXT NOT NULL,
    supplier_name TEXT NOT NULL DEFAULT '',
    amount TEXT NOT NULL DEFAULT '',
    currency TEXT NOT NULL DEFAULT '',
    country TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS search_runs (
    id INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    config_json TEXT NOT NULL,
    log TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS lead_events (
    id INTEGER PRIMARY KEY,
    lead_id INTEGER NOT NULL REFERENCES leads(id),
    at TEXT NOT NULL,
    kind TEXT NOT NULL,
    detail TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS saved_searches (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    config_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_states (
    source_name TEXT PRIMARY KEY,
    last_checked_at TEXT,
    last_status TEXT NOT NULL,
    last_error TEXT NOT NULL DEFAULT '',
    last_result_count INTEGER NOT NULL DEFAULT 0
);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Database:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            self.migrate(conn)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def migrate(self, conn: sqlite3.Connection) -> None:
        conn.executescript(SCHEMA)
        row = conn.execute("SELECT version FROM schema_migrations WHERE version = 1").fetchone()
        if row is None:
            conn.execute("INSERT INTO schema_migrations (version, applied_at) VALUES (1, ?)", (utc_now(),))
        columns = {info[1] for info in conn.execute("PRAGMA table_info(source_states)")}
        if "last_result_count" not in columns:
            conn.execute(
                "ALTER TABLE source_states ADD COLUMN last_result_count INTEGER NOT NULL DEFAULT 0"
            )
        conn.commit()

    def backup_to(self, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as source, sqlite3.connect(destination) as target:
            source.backup(target)

    def upsert_organization(self, conn: sqlite3.Connection, org: dict) -> int:
        now = utc_now()
        existing = conn.execute(
            "SELECT id FROM organizations WHERE normalized_name = ? AND country = ?",
            (org["normalized_name"], org.get("country") or ""),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE organizations
                SET name = ?, region = COALESCE(NULLIF(?, ''), region),
                    category = CASE WHEN ? != '' THEN ? ELSE category END,
                    category_verification = CASE WHEN ? != '' THEN ? ELSE category_verification END,
                    website = CASE WHEN ? != '' THEN ? ELSE website END,
                    domain = CASE WHEN ? != '' THEN ? ELSE domain END,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    org["name"],
                    org.get("region") or "",
                    org.get("category") or "",
                    org.get("category") or "",
                    org.get("category_verification") or "",
                    org.get("category_verification") or "",
                    org.get("website") or "",
                    org.get("website") or "",
                    org.get("domain") or "",
                    org.get("domain") or "",
                    now,
                    existing["id"],
                ),
            )
            return int(existing["id"])
        cursor = conn.execute(
            """
            INSERT INTO organizations (
                name, normalized_name, country, region, category, category_verification,
                website, domain, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                org["name"],
                org["normalized_name"],
                org.get("country") or "",
                org.get("region") or "",
                org.get("category") or "",
                org.get("category_verification") or "not_verified",
                org.get("website") or "",
                org.get("domain") or "",
                now,
                now,
            ),
        )
        return int(cursor.lastrowid)

    def add_or_update_evidence(self, conn: sqlite3.Connection, item: dict) -> tuple[int, bool]:
        now = utc_now()
        current = conn.execute(
            "SELECT * FROM evidence WHERE source_name = ? AND source_record_id = ?",
            (item["source_name"], item["source_record_id"]),
        ).fetchone()
        if current and current["content_hash"] == item["content_hash"]:
            return int(current["id"]), False
        if current:
            conn.execute(
                """
                INSERT INTO evidence_history (evidence_id, recorded_at, content_hash, title, excerpt)
                VALUES (?, ?, ?, ?, ?)
                """,
                (current["id"], now, current["content_hash"], current["title"], current["excerpt"]),
            )
            conn.execute(
                """
                UPDATE evidence
                SET title = ?, excerpt = ?, explanation = ?, limitations = ?, source_url = ?,
                    published_at = ?, discovered_at = ?, content_hash = ?, procurement_signal = ?,
                    amount = ?, formats = ?, raw_json = ?, level = ?, kind = ?
                WHERE id = ?
                """,
                (
                    item["title"],
                    item["excerpt"],
                    item["explanation"],
                    item["limitations"],
                    item["source_url"],
                    item.get("published_at"),
                    now,
                    item["content_hash"],
                    item.get("procurement_signal") or "none",
                    item.get("amount"),
                    ",".join(item.get("formats") or []),
                    item.get("raw_json") or "{}",
                    item["level"],
                    item["kind"],
                    current["id"],
                ),
            )
            return int(current["id"]), True
        cursor = conn.execute(
            """
            INSERT INTO evidence (
                organization_id, lead_id, kind, level, title, excerpt, explanation, limitations,
                source_name, source_record_id, source_url, published_at, discovered_at,
                content_hash, procurement_signal, amount, formats, raw_json
            ) VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["organization_id"],
                item["kind"],
                item["level"],
                item["title"],
                item["excerpt"],
                item["explanation"],
                item["limitations"],
                item["source_name"],
                item["source_record_id"],
                item["source_url"],
                item.get("published_at"),
                now,
                item["content_hash"],
                item.get("procurement_signal") or "none",
                item.get("amount"),
                ",".join(item.get("formats") or []),
                item.get("raw_json") or "{}",
            ),
        )
        return int(cursor.lastrowid), True

    def ensure_lead(self, conn: sqlite3.Connection, organization_id: int) -> int:
        row = conn.execute("SELECT id FROM leads WHERE organization_id = ?", (organization_id,)).fetchone()
        if row:
            return int(row["id"])
        now = utc_now()
        cursor = conn.execute(
            """
            INSERT INTO leads (
                organization_id, status, evidence_level, evidence_strength, recency_score,
                relevance_score, scale_score, procurement_score, activity_score, contact_score,
                geo_score, total_score, score_explanation, summary, procurement_signal, formats,
                verification_status, compliance_judgment, next_action, user_notes, created_at, updated_at
            ) VALUES (?, 'new', 'D', 0, 0, 0, 0, 0, 0, 0, 0, 0, '', '', 'none', '', 'unverified_prospect', 'none', '', '', ?, ?)
            """,
            (organization_id, now, now),
        )
        return int(cursor.lastrowid)

    def save_score(self, conn: sqlite3.Connection, lead_id: int, score: dict) -> None:
        previous = conn.execute("SELECT total_score, evidence_level FROM leads WHERE id = ?", (lead_id,)).fetchone()
        now = utc_now()
        conn.execute(
            """
            UPDATE leads SET
                evidence_level = ?, evidence_strength = ?, recency_score = ?, relevance_score = ?,
                scale_score = ?, procurement_score = ?, activity_score = ?, contact_score = ?,
                geo_score = ?, total_score = ?, score_explanation = ?, summary = ?,
                procurement_signal = ?, formats = ?,
                compliance_judgment = ?, next_action = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                score["evidence_level"],
                score["evidence_strength"],
                score["recency_score"],
                score["relevance_score"],
                score["scale_score"],
                score["procurement_score"],
                score["activity_score"],
                score["contact_score"],
                score["geo_score"],
                score["total_score"],
                score["explanation"],
                score["summary"],
                score["procurement_signal"],
                ",".join(score["formats"]),
                score["compliance_judgment"],
                score["next_action"],
                now,
                lead_id,
            ),
        )
        conn.execute("UPDATE evidence SET lead_id = ? WHERE organization_id = (SELECT organization_id FROM leads WHERE id = ?)", (lead_id, lead_id))
        if previous and (previous["total_score"] != score["total_score"] or previous["evidence_level"] != score["evidence_level"]):
            self.add_event(
                conn,
                lead_id,
                "score_changed",
                f"prethodno {previous['evidence_level']}/{previous['total_score']} -> {score['evidence_level']}/{score['total_score']}",
            )

    def add_contact(self, conn: sqlite3.Connection, contact: dict) -> int:
        existing = conn.execute(
            """
            SELECT id FROM contacts
            WHERE organization_id = ? AND email = ? AND source_url = ? AND name = ?
            """,
            (contact["organization_id"], contact.get("email") or "", contact["source_url"], contact.get("name") or ""),
        ).fetchone()
        if existing:
            return int(existing["id"])
        if contact.get("email_verification") == "verified" and not contact.get("email"):
            raise ValueError("Prazan imejl ne može biti verified.")
        cursor = conn.execute(
            """
            INSERT INTO contacts (
                organization_id, name, title, department, email, email_verification,
                profile_url, department_url, source_url, verified_at, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                contact["organization_id"],
                contact.get("name") or "",
                contact.get("title") or "",
                contact.get("department") or "",
                contact.get("email") or "",
                contact.get("email_verification") or "not_found",
                contact.get("profile_url") or "",
                contact.get("department_url") or "",
                contact["source_url"],
                contact.get("verified_at"),
                contact.get("notes") or "",
            ),
        )
        return int(cursor.lastrowid)

    def add_document(self, conn: sqlite3.Connection, document: dict) -> int:
        cursor = conn.execute(
            """
            INSERT INTO documents (
                organization_id, url, format, host_name, discovered_at, reason, local_path, analysis_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document.get("organization_id"),
                document.get("url") or "",
                document["format"],
                document.get("host_name") or "",
                utc_now(),
                document.get("reason") or "",
                document.get("local_path") or "",
                document.get("analysis_json") or "",
            ),
        )
        return int(cursor.lastrowid)

    def add_finding(self, conn: sqlite3.Connection, finding: dict) -> int:
        cursor = conn.execute(
            """
            INSERT INTO findings (document_id, evidence_id, tool, rule_id, summary, status, wcag_hint, details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                finding.get("document_id"),
                finding.get("evidence_id"),
                finding["tool"],
                finding["rule_id"],
                finding["summary"],
                finding["status"],
                finding.get("wcag_hint") or "",
                finding.get("details") or "",
            ),
        )
        return int(cursor.lastrowid)

    def add_procurement(self, conn: sqlite3.Connection, notice: dict) -> None:
        exists = conn.execute("SELECT id FROM procurement_notices WHERE evidence_id = ?", (notice["evidence_id"],)).fetchone()
        if exists:
            conn.execute(
                """
                UPDATE procurement_notices
                SET notice_status = ?, buyer_name = ?, supplier_name = ?, amount = ?, currency = ?, country = ?
                WHERE evidence_id = ?
                """,
                (
                    notice.get("notice_status") or "",
                    notice.get("buyer_name") or "",
                    notice.get("supplier_name") or "",
                    notice.get("amount") or "",
                    notice.get("currency") or "",
                    notice.get("country") or "",
                    notice["evidence_id"],
                ),
            )
            return
        conn.execute(
            """
            INSERT INTO procurement_notices (evidence_id, notice_status, buyer_name, supplier_name, amount, currency, country)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                notice["evidence_id"],
                notice.get("notice_status") or "",
                notice.get("buyer_name") or "",
                notice.get("supplier_name") or "",
                notice.get("amount") or "",
                notice.get("currency") or "",
                notice.get("country") or "",
            ),
        )

    def add_event(self, conn: sqlite3.Connection, lead_id: int, kind: str, detail: str) -> None:
        conn.execute(
            "INSERT INTO lead_events (lead_id, at, kind, detail) VALUES (?, ?, ?, ?)",
            (lead_id, utc_now(), kind, detail),
        )

    def start_run(self, config_json: str) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO search_runs (started_at, status, config_json) VALUES (?, 'running', ?)",
                (utc_now(), config_json),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def finish_run(self, run_id: int, status: str, log: str, error: str = "") -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE search_runs SET finished_at = ?, status = ?, log = ?, error = ? WHERE id = ?",
                (utc_now(), status, log, error, run_id),
            )
            conn.commit()

    def set_source_state(self, name: str, status: str, error: str = "", result_count: int = 0) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO source_states (source_name, last_checked_at, last_status, last_error, last_result_count)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source_name) DO UPDATE SET
                    last_checked_at = excluded.last_checked_at,
                    last_status = excluded.last_status,
                    last_error = excluded.last_error,
                    last_result_count = excluded.last_result_count
                """,
                (name, utc_now(), status, error[:1000], int(result_count)),
            )
            conn.commit()

    def latest_run(self) -> dict | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM search_runs ORDER BY id DESC LIMIT 1").fetchone()
            return dict(row) if row else None

    def latest_successful_run(self) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM search_runs
                WHERE status IN ('completed_with_results', 'completed_empty', 'partial', 'completed')
                ORDER BY id DESC LIMIT 1
                """
            ).fetchone()
            return dict(row) if row else None

    def delete_leads(self, lead_ids: list[int]) -> int:
        removed = 0
        with self.connect() as conn:
            for lead_id in lead_ids:
                org = conn.execute("SELECT organization_id FROM leads WHERE id = ?", (lead_id,)).fetchone()
                if org is None:
                    continue
                self._delete_organization(conn, int(org["organization_id"]), int(lead_id))
                removed += 1
            conn.commit()
        return removed

    def delete_all_research(self) -> None:
        with self.connect() as conn:
            for table in (
                "findings",
                "procurement_notices",
                "evidence_history",
                "lead_events",
                "contacts",
                "documents",
                "evidence",
                "leads",
                "organizations",
                "search_runs",
            ):
                conn.execute(f"DELETE FROM {table}")
            conn.commit()

    def _delete_organization(self, conn: sqlite3.Connection, organization_id: int, lead_id: int) -> None:
        evidence_ids = [
            int(row["id"])
            for row in conn.execute("SELECT id FROM evidence WHERE organization_id = ?", (organization_id,))
        ]
        for evidence_id in evidence_ids:
            conn.execute("DELETE FROM evidence_history WHERE evidence_id = ?", (evidence_id,))
            conn.execute("DELETE FROM procurement_notices WHERE evidence_id = ?", (evidence_id,))
            conn.execute("DELETE FROM findings WHERE evidence_id = ?", (evidence_id,))
        for row in conn.execute("SELECT id FROM documents WHERE organization_id = ?", (organization_id,)):
            conn.execute("DELETE FROM findings WHERE document_id = ?", (int(row["id"]),))
        conn.execute("DELETE FROM documents WHERE organization_id = ?", (organization_id,))
        conn.execute("DELETE FROM contacts WHERE organization_id = ?", (organization_id,))
        conn.execute("DELETE FROM lead_events WHERE lead_id = ?", (lead_id,))
        conn.execute("DELETE FROM evidence WHERE organization_id = ?", (organization_id,))
        conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
        conn.execute("DELETE FROM organizations WHERE id = ?", (organization_id,))

    def dashboard(self) -> dict:
        with self.connect() as conn:
            def count(sql: str, params: tuple = ()) -> int:
                return int(conn.execute(sql, params).fetchone()[0])

            by_country = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT o.country AS country, COUNT(*) AS count
                    FROM leads l JOIN organizations o ON o.id = l.organization_id
                    GROUP BY o.country ORDER BY count DESC
                    """
                )
            ]
            by_category = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT CASE WHEN o.category = '' THEN 'nije utvrđeno' ELSE o.category END AS category,
                           COUNT(*) AS count
                    FROM leads l JOIN organizations o ON o.id = l.organization_id
                    GROUP BY o.category ORDER BY count DESC
                    """
                )
            ]
            recent = [
                dict(row)
                for row in conn.execute(
                    "SELECT id, started_at, finished_at, status, error FROM search_runs ORDER BY id DESC LIMIT 8"
                )
            ]
            sources = [dict(row) for row in conn.execute("SELECT * FROM source_states ORDER BY source_name")]
            return {
                "organizations": count("SELECT COUNT(*) FROM organizations"),
                "leads": count("SELECT COUNT(*) FROM leads"),
                "strong": count("SELECT COUNT(*) FROM leads WHERE evidence_level IN ('A', 'B')"),
                "procurement": count("SELECT COUNT(*) FROM leads WHERE procurement_signal = 'open_procurement'"),
                "awaiting": count("SELECT COUNT(*) FROM leads WHERE verification_status = 'unverified_prospect'"),
                "by_country": by_country,
                "by_category": by_category,
                "recent_runs": recent,
                "sources": sources,
            }

    def query_leads(self, filters: dict | None = None) -> list[dict]:
        filters = filters or {}
        clauses = ["1 = 1"]
        params: list = []
        if filters.get("level"):
            clauses.append("l.evidence_level = ?")
            params.append(filters["level"])
        if filters.get("min_level"):
            rank = {"D": 1, "C": 2, "B": 3, "A": 4}[filters["min_level"]]
            clauses.append(
                "CASE l.evidence_level WHEN 'A' THEN 4 WHEN 'B' THEN 3 WHEN 'C' THEN 2 ELSE 1 END >= ?"
            )
            params.append(rank)
        if filters.get("country"):
            clauses.append("o.country = ?")
            params.append(filters["country"])
        if filters.get("status"):
            clauses.append("l.status = ?")
            params.append(filters["status"])
        if filters.get("format"):
            clauses.append("l.formats LIKE ?")
            params.append(f"%{filters['format']}%")
        if filters.get("procurement"):
            clauses.append("l.procurement_signal = ?")
            params.append(filters["procurement"])
        if filters.get("qualified_only"):
            clauses.append("l.evidence_level IN ('A', 'B') AND l.status != 'rejected'")
        sql = f"""
            SELECT l.*, o.name AS organization, o.country, o.website, o.category, o.category_verification
            FROM leads l JOIN organizations o ON o.id = l.organization_id
            WHERE {' AND '.join(clauses)}
            ORDER BY l.total_score DESC, l.id DESC
        """
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(sql, params)]

    def lead_bundle(self, lead_id: int) -> dict | None:
        with self.connect() as conn:
            lead = conn.execute(
                """
                SELECT l.*, o.name AS organization, o.country, o.region, o.website, o.category,
                       o.category_verification, o.domain
                FROM leads l JOIN organizations o ON o.id = l.organization_id
                WHERE l.id = ?
                """,
                (lead_id,),
            ).fetchone()
            if lead is None:
                return None
            evidence = [dict(row) for row in conn.execute("SELECT * FROM evidence WHERE lead_id = ? ORDER BY id", (lead_id,))]
            contacts = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM contacts WHERE organization_id = ? ORDER BY id",
                    (lead["organization_id"],),
                )
            ]
            events = [dict(row) for row in conn.execute("SELECT * FROM lead_events WHERE lead_id = ? ORDER BY id", (lead_id,))]
            documents = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM documents WHERE organization_id = ? ORDER BY id",
                    (lead["organization_id"],),
                )
            ]
            findings = []
            if documents or evidence:
                findings = [
                    dict(row)
                    for row in conn.execute(
                        """
                        SELECT f.* FROM findings f
                        LEFT JOIN documents d ON d.id = f.document_id
                        WHERE d.organization_id = ? OR f.evidence_id IN (SELECT id FROM evidence WHERE lead_id = ?)
                        ORDER BY f.id
                        """,
                        (lead["organization_id"], lead_id),
                    )
                ]
            return {
                "lead": dict(lead),
                "evidence": evidence,
                "contacts": contacts,
                "events": events,
                "documents": documents,
                "findings": findings,
            }

    def update_lead_operator(self, lead_id: int, status: str, notes: str, follow_up_on: str, verification_status: str) -> None:
        allowed_status = {"new", "reviewing", "qualified", "rejected", "contacted", "archived"}
        allowed_verification = {"unverified_prospect", "manually_verified", "rejected"}
        if status not in allowed_status:
            raise ValueError("Nepoznat status.")
        if verification_status not in allowed_verification:
            raise ValueError("Nepoznat status provere.")
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE leads SET status = ?, user_notes = ?, follow_up_on = ?, verification_status = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, notes, follow_up_on or None, verification_status, utc_now(), lead_id),
            )
            self.add_event(conn, lead_id, "operator_update", f"{status}; provera={verification_status}")
            conn.commit()

    def save_search(self, name: str, config_json: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO saved_searches (name, config_json, created_at) VALUES (?, ?, ?)",
                (name, config_json, utc_now()),
            )
            conn.commit()

    def list_saved_searches(self) -> list[dict]:
        with self.connect() as conn:
            return [dict(row) for row in conn.execute("SELECT id, name, created_at FROM saved_searches ORDER BY id DESC")]

    def evidence_for_org(self, conn: sqlite3.Connection, organization_id: int) -> list[dict]:
        rows = []
        for row in conn.execute("SELECT * FROM evidence WHERE organization_id = ?", (organization_id,)):
            item = dict(row)
            item["formats"] = [part for part in (item.get("formats") or "").split(",") if part]
            rows.append(item)
        return rows

    def export_rows(self, qualified_only: bool = False) -> list[dict]:
        leads = self.query_leads({"qualified_only": True} if qualified_only else {})
        exported = []
        for lead in leads:
            bundle = self.lead_bundle(lead["id"])
            assert bundle is not None
            exported.append(bundle)
        return exported


def dumps(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)
