"""BOAMP, zvanični Open Data DILA. Pretraga ide po predmetu oglasa, ne po celom tekstu.

API: https://boamp-datadila.opendatasoft.com/api/explore/v2.1
Dokumentacija: https://www.data.gouv.fr/dataservices/api-bulletin-officiel-des-annonces-des-marches-publics-boamp
Ključ nije potreban. Polje donnees se ne preuzima.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from tamigo_intel.config import SearchConfig
from tamigo_intel.http_client import HttpClient
from tamigo_intel.sources.base import Discovered
from tamigo_intel.terms import clean_text, parse_date, procurement_level, relevant

ENDPOINT = "https://boamp-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/boamp/records"
SELECT = "idweb,objet,nomacheteur,dateparution,nature,nature_libelle,etat,url_avis,datelimitereponse,descripteur_libelle,titulaire"
MAX_TERMS = 4
PAGE_LIMIT = 20


class BoampSource:
    name = "boamp"
    countries = ("FR",)

    def search(self, config: SearchConfig, client: HttpClient, now: datetime | None = None) -> list[Discovered]:
        moment = now or datetime.now(timezone.utc)
        start = (moment - timedelta(days=max(1, config.recency_days))).date().isoformat()
        found: list[Discovered] = []
        seen: set[str] = set()
        for term in query_terms(config.keywords):
            where = f'search(objet, "{term}") AND dateparution >= "{start}"'
            params = urlencode(
                {
                    "where": where,
                    "limit": str(PAGE_LIMIT),
                    "order_by": "dateparution desc",
                    "select": SELECT,
                }
            )
            data = client.get_json(f"{ENDPOINT}?{params}")
            rows = data.get("results")
            if rows is None:
                rows = []
            if not isinstance(rows, list):
                raise ValueError("BOAMP odgovor nema listu results.")
            for row in rows:
                if not isinstance(row, dict):
                    continue
                item = record_to_item(row, config.keywords, moment)
                if item is None or item.source_record_id in seen:
                    continue
                seen.add(item.source_record_id)
                found.append(item)
                if len(found) >= config.max_per_source:
                    return found
        return found


def query_terms(keywords: list[str]) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for keyword in keywords:
        term = _clean_term(keyword)
        key = term.casefold()
        if len(term) < 4 or key in seen:
            continue
        seen.add(key)
        found.append(term)
        if len(found) >= MAX_TERMS:
            break
    return found


def record_to_item(row: dict, keywords: list[str], now: datetime | None = None) -> Discovered | None:
    moment = now or datetime.now(timezone.utc)
    title = clean_text(str(row.get("objet") or ""), 400)
    descriptors = row.get("descripteur_libelle") or []
    if isinstance(descriptors, list):
        extra = " ".join(str(item) for item in descriptors)
    else:
        extra = str(descriptors)
    excerpt = clean_text(f"{title} {extra}".strip(), 700)
    if not title or not relevant(excerpt, keywords):
        return None
    buyer = clean_text(str(row.get("nomacheteur") or ""), 300)
    if not buyer:
        return None
    record_id = str(row.get("idweb") or "").strip()
    if not record_id:
        return None
    url = str(row.get("url_avis") or "")
    if not url.startswith("https://www.boamp.fr/"):
        url = f"https://www.boamp.fr/pages/avis/?q=idweb:{record_id}"
    signal = _signal(row, moment)
    supplier = _supplier(row.get("titulaire"))
    level = procurement_level(title, excerpt)
    return Discovered(
        source_name="boamp",
        source_record_id=record_id,
        source_url=url,
        organization_name=buyer,
        country="FR",
        title=title,
        excerpt=excerpt,
        explanation=(
            "BOAMP Open Data. Sačuvani su predmet oglasa, naručilac i zvanična adresa. "
            "Ceo tekst oglasa nije preuzet."
        ),
        limitations=(
            "Ovo nije cela francuska nabavka. BOAMP ne objavljuje svaki oglas ispod zakonskog praga. "
            "Pretraga gleda predmet oglasa, najviše četiri reči i dvadeset zapisa po reči. "
            "Reč accessibilité sama obuhvata i građevinsku pristupačnost, pa se čuva samo zapis "
            "koji ima digitalni termin. Dodela je istorijska. Rok koji je prošao nije otvoren poziv. "
            "Iznos nije u ovom izvodu i nije upisan."
        ),
        level=level,
        kind="award" if signal == "past_award" else "procurement_notice",
        published_at=str(row.get("dateparution") or "") or None,
        procurement_signal=signal,
        supplier_name=supplier,
        notice_status=signal,
        raw={
            "idweb": record_id,
            "nature": row.get("nature") or "",
            "etat": row.get("etat") or "",
            "dateparution": row.get("dateparution") or "",
        },
    )


def _signal(row: dict, now: datetime) -> str:
    nature = str(row.get("nature") or "").upper()
    etat = str(row.get("etat") or "").upper()
    if nature.startswith("ATTRIB"):
        return "past_award"
    if nature in {"ANNULATION"} or etat in {"ANNULE", "ANNULATION"}:
        return "closed"
    deadline = parse_date(str(row.get("datelimitereponse") or ""))
    if deadline is not None and deadline < now:
        return "closed"
    if nature == "APPEL_OFFRE":
        return "open_procurement"
    return "closed"


def _supplier(value) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return clean_text(", ".join(str(item) for item in value if item), 300)
    return clean_text(str(value), 300)


def _clean_term(value: str) -> str:
    text = re.sub(r"[^\w\s.'-]", " ", value or "", flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()[:80]
