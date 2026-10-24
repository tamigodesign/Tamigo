"""Opis izvora i proba veze. Poruke ne sadrže tajne."""

from __future__ import annotations

from tamigo_intel.config import SearchConfig
from tamigo_intel.failures import failure_kind, failure_label
from tamigo_intel.http_client import HttpClient, HttpError
from tamigo_intel.redact import redact

SOURCE_GROUPS = (
    ("procurement", "1. Javne nabavke i oglasi"),
    ("publishers", "2. Izdavači i udruženja"),
    ("universities", "3. Univerziteti i istraživanje"),
    ("libraries", "4. Biblioteke i repozitorijumi"),
    ("government", "5. Državne ustanove i izveštaji o pristupačnosti"),
    ("professional", "6. Zdravstvo, struka i nauka"),
    ("documents", "7. Javni dokumenti i dokazi"),
)


SOURCE_CATALOG = [
    {
        "name": "sam_gov",
        "title": "SAM.gov",
        "group": "procurement",
        "availability": "needs_key",
        "auth": "required",
        "credential": "sam_api_key",
        "credential_label": "API ključ",
        "signup_url": "https://api.data.gov/signup/",
        "docs_url": "https://open.gsa.gov/api/get-opportunities-public-api/",
        "instructions": "Napravite besplatan ključ na api.data.gov. U SAM.gov se ne unosi lozinka naloga.",
        "limits": "Javni ključ ima dnevni limit. Osnovni pristup nema pretplatu. Bez ključa ovaj izvor se ne poziva.",
    },
    {
        "name": "github_issues",
        "title": "GitHub issues",
        "group": "procurement",
        "availability": "available",
        "auth": "optional",
        "credential": "github_token",
        "credential_label": "token",
        "signup_url": "https://github.com/settings/tokens",
        "docs_url": "https://docs.github.com/en/rest/search/search#search-issues-and-pull-requests",
        "instructions": "Token je opcion. Dovoljan je klasičan token bez dodatnih ovlašćenja za javne podatke. Lozinka naloga se ne traži.",
        "limits": "Bez tokena je granica oko 60 zahteva na sat po IP adresi. Token podiže tu granicu. Nema posebne naknade za ovu pretragu.",
    },
    {
        "name": "contracts_finder",
        "title": "Contracts Finder (UK)",
        "group": "procurement",
        "availability": "available",
        "auth": "none",
        "credential": "",
        "credential_label": "",
        "signup_url": "https://www.contractsfinder.service.gov.uk/",
        "docs_url": "https://www.contractsfinder.service.gov.uk/apidocumentation",
        "instructions": "Javni API. Ključ nije potreban.",
        "limits": "Besplatno. Program pravi pauzu između zahteva.",
    },
    {
        "name": "usaspending",
        "title": "USAspending",
        "group": "procurement",
        "availability": "partial",
        "auth": "none",
        "credential": "",
        "credential_label": "",
        "signup_url": "https://www.usaspending.gov/",
        "docs_url": "https://api.usaspending.gov/",
        "instructions": "Javni API. Ključ nije potreban. Lid je naručilac, ne dobavljač.",
        "limits": "Besplatno. Istorijske dodele nisu otvoren poziv.",
    },
    {
        "name": "canada_buys",
        "title": "CanadaBuys",
        "group": "procurement",
        "availability": "partial",
        "auth": "none",
        "credential": "",
        "credential_label": "",
        "signup_url": "https://canadabuys.canada.ca/en/procurement-and-contracting-data",
        "docs_url": "https://open.canada.ca/data/en/dataset/6abd20d4-7a1c-4b38-baa2-9525d0bb2fd2",
        "instructions": "Zvanični CSV. Ključ nije potreban.",
        "limits": "Besplatno. Preuzimaju se otvoreni oglasi i najviše dve poslednje fiskalne godine dodela.",
    },
    {
        "name": "find_tender",
        "title": "Find a Tender (UK)",
        "group": "procurement",
        "availability": "partial",
        "auth": "none",
        "credential": "",
        "credential_label": "",
        "signup_url": "https://www.find-tender.service.gov.uk/",
        "docs_url": "https://www.find-tender.service.gov.uk/apidocumentation",
        "instructions": "Javni OCDS API. Ključ nije potreban. Izvor je podrazumevano isključen.",
        "limits": "Besplatno. Čitaju se najnovija izdanja, najviše četiri stranice, pa lokalni filter. Nije cela arhiva. HTML oglasa može vratiti HTTP 403.",
    },
    {
        "name": "ted",
        "title": "TED",
        "group": "procurement",
        "availability": "partial",
        "auth": "none",
        "credential": "",
        "credential_label": "",
        "signup_url": "https://ted.europa.eu/",
        "docs_url": "https://docs.ted.europa.eu/api/latest/search.html",
        "instructions": "Javni API. Ključ nije potreban.",
        "limits": "Besplatno. Čuva se naslov oglasa, ne ceo tekst.",
    },
    {
        "name": "boamp",
        "title": "BOAMP (Francuska)",
        "group": "procurement",
        "availability": "partial",
        "auth": "none",
        "credential": "",
        "credential_label": "",
        "signup_url": "https://www.boamp.fr/",
        "docs_url": "https://www.data.gouv.fr/dataservices/api-bulletin-officiel-des-annonces-des-marches-publics-boamp",
        "instructions": "Javni Open Data DILA. Ključ nije potreban. Izvor je podrazumevano isključen.",
        "limits": "Besplatno. Pretraga je po predmetu oglasa, najviše četiri reči i dvadeset zapisa po reči. Ceo tekst oglasa se ne preuzima. Nije cela francuska nabavka.",
    },
]


PLANNED_SOURCES = [
    {
        "name": "oeffentlichevergabe",
        "title": "Bekanntmachungsservice (Nemačka)",
        "group": "procurement",
        "note": "Zvanični Open Data je dnevni izvoz, bez pretrage po ključnoj reči u ovom programu. Nije ugrađen.",
    },
    {
        "name": "tenderned",
        "title": "TenderNed (Holandija)",
        "group": "procurement",
        "note": "Nije ugrađen. Javni API pogodan za ovu pretragu nije povezan.",
    },
    {
        "name": "anac",
        "title": "ANAC (Italija)",
        "group": "procurement",
        "note": "Nije ugrađen.",
    },
    {
        "name": "ankoe",
        "title": "ANKÖ (Austrija)",
        "group": "procurement",
        "note": "Nije ugrađen.",
    },
    {
        "name": "udbud",
        "title": "udbud.dk (Danska)",
        "group": "procurement",
        "note": "Nije ugrađen.",
    },
    {
        "name": "be_procurement",
        "title": "e-Procurement (Belgija)",
        "group": "procurement",
        "note": "Nije ugrađen.",
    },
    {
        "name": "hilma",
        "title": "HILMA (Finska)",
        "group": "procurement",
        "note": "Nije ugrađen.",
    },
    {
        "name": "simap",
        "title": "simap.ch (Švajcarska)",
        "group": "procurement",
        "note": "Nije ugrađen.",
    },
    {
        "name": "placsp",
        "title": "Plataforma de Contratación (Španija)",
        "group": "procurement",
        "note": "Nije ugrađen.",
    },
    {
        "name": "ejn",
        "title": "e-JN (Slovenija)",
        "group": "procurement",
        "note": "Nije ugrađen.",
    },
    {
        "name": "etenders",
        "title": "eTenders (Irska)",
        "group": "procurement",
        "note": "Nije ugrađen.",
    },
    {
        "name": "austender",
        "title": "AusTender (Australija)",
        "group": "procurement",
        "note": "Proba adrese vraćala je HTTP 403 MissingAuthenticationToken. Nije ugrađen. 403 ovde nije greška sertifikata.",
    },
    {
        "name": "nz_procurement",
        "title": "Novi Zeland, javna nabavka",
        "group": "procurement",
        "note": "Nije ugrađen.",
    },
    {
        "name": "publisher_directories",
        "title": "Imenici izdavača",
        "group": "publishers",
        "note": "Nijedan imenik nije proveren kao dozvoljen izvor za upis. Nije ugrađen. Izdavač nije sam po sebi dokaz potrebe.",
    },
    {
        "name": "universities",
        "title": "Univerziteti i istraživački instituti",
        "group": "universities",
        "note": "Nije ugrađen. Pripadnost sektoru ne pravi lid.",
    },
    {
        "name": "libraries",
        "title": "Biblioteke i digitalni repozitorijumi",
        "group": "libraries",
        "note": "Nije ugrađen.",
    },
    {
        "name": "accessibility_reports",
        "title": "Zvanični izveštaji i izjave o pristupačnosti",
        "group": "government",
        "note": "Nije ugrađen. Nabavke i dalje dolaze iz povezanih portala.",
    },
    {
        "name": "professional_orgs",
        "title": "Zdravstvo, struka i naučna društva",
        "group": "professional",
        "note": "Nije ugrađen. Sektor sam ne znači da ustanova traži uslugu.",
    },
    {
        "name": "public_documents",
        "title": "Otkrivanje javnih PDF i EPUB fajlova",
        "group": "documents",
        "note": "Nije ugrađeno kao pretraga. Ručna provera jednog fajla i dalje stoji na izabranom lidu i nije ocena WCAG.",
    },
]


def catalog_by_name() -> dict[str, dict]:
    return {item["name"]: item for item in SOURCE_CATALOG}


def auth_label(kind: str) -> str:
    return {"required": "ključ je obavezan", "optional": "ključ je opcion", "none": "ključ nije potreban"}.get(kind, kind)


def availability_label(kind: str) -> str:
    return {
        "available": "dostupan",
        "needs_key": "traži API ključ",
        "partial": "delimično povezan",
        "not_implemented": "nije još ugrađeno",
    }.get(kind, kind)


def test_connection(name: str, config: SearchConfig, client: HttpClient) -> tuple[str, str]:
    """Vraća (status, poruka). Status je ok, missing ili failed. Poruka je bez tajni."""
    info = catalog_by_name().get(name)
    if info is None:
        return "failed", "Nepoznat izvor."
    secret = getattr(config, info["credential"], "") if info["credential"] else ""
    secrets = [value for value in (config.sam_api_key, config.github_token, config.openai_api_key) if value]
    if info["auth"] == "required" and not secret:
        return "missing", "Ključ nije sačuvan. Izvor se ne poziva dok se ne unese."
    try:
        if name == "sam_gov":
            _probe_sam(config, client)
        elif name == "github_issues":
            _probe_github(config, client)
        elif name == "contracts_finder":
            client.post_json(
                "https://www.contractsfinder.service.gov.uk/api/rest/2/search_notices/json",
                {"searchCriteria": {"keyword": "WCAG", "types": ["Contract"]}, "size": 1},
            )
        elif name == "usaspending":
            client.post_json(
                "https://api.usaspending.gov/api/v2/search/spending_by_award/",
                {"filters": {"keywords": ["WCAG"]}, "fields": ["Award ID"], "limit": 1, "page": 1},
            )
        elif name == "ted":
            client.post_json(
                "https://api.ted.europa.eu/v3/notices/search",
                {"query": "notice-title ~ WCAG", "fields": ["publication-number"], "limit": 1, "page": 1},
            )
        elif name == "find_tender":
            client.get_json("https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages?limit=1")
        elif name == "canada_buys":
            client.get_bytes(
                "https://canadabuys.canada.ca/opendata/pub/openTenderNotice-ouvertAvisAppelOffres.csv",
                max_bytes=2048,
                timeout=20,
            )
        elif name == "boamp":
            client.get_json(
                "https://boamp-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/boamp/records?limit=1&select=idweb"
            )
        else:
            return "failed", "Proba veze nije ugrađena za ovaj izvor."
    except (HttpError, OSError, ValueError) as exc:
        return "failed", _safe_error(exc, secrets)
    if info["auth"] == "optional" and not secret:
        return "ok", "Veza radi bez ključa. Token i dalje može da podigne limit."
    return "ok", "Veza radi. Sertifikat je proveren."


def _probe_sam(config: SearchConfig, client: HttpClient) -> None:
    from datetime import datetime, timedelta, timezone
    from urllib.parse import urlencode

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=7)
    params = urlencode(
        {
            "api_key": config.sam_api_key,
            "keywords": "WCAG",
            "limit": "1",
            "postedFrom": start.strftime("%m/%d/%Y"),
            "postedTo": end.strftime("%m/%d/%Y"),
        }
    )
    client.get_json("https://api.sam.gov/opportunities/v2/search?" + params)


def _probe_github(config: SearchConfig, client: HttpClient) -> None:
    headers = {"Accept": "application/vnd.github+json"}
    if config.github_token:
        headers["Authorization"] = f"Bearer {config.github_token}"
    client.get_json("https://api.github.com/rate_limit", headers=headers)


def _safe_error(exc: Exception, secrets: list[str]) -> str:
    return f"{failure_label(failure_kind(exc))} {redact(str(exc), secrets)}"
