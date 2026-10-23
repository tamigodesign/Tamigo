"""CanadaBuys otvoreni podaci. Bez ključa.

Preuzimaju se zvanični CSV fajlovi Vlade Kanade. Lid je naručilac ili krajnji
korisnik iz tog fajla, nikad dobavljač. Dodela ostaje istorijska.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from tamigo_intel.config import SearchConfig
from tamigo_intel.http_client import HttpClient, HttpError
from tamigo_intel.sources.base import Discovered
from tamigo_intel.terms import age_days, clean_text, parse_date, procurement_level, relevant

OPEN_CSV = "https://canadabuys.canada.ca/opendata/pub/openTenderNotice-ouvertAvisAppelOffres.csv"
AWARD_CSV = "https://canadabuys.canada.ca/opendata/pub/{start}-{end}-awardNotice-avisAttribution.csv"
FILE_CAP = 45_000_000
MAX_AWARD_FILES = 2

TITLE = "title-titre-eng"
TITLE_FR = "title-titre-fra"
REFERENCE = "referenceNumber-numeroReference"
AMENDMENT = "amendmentNumber-numeroModification"
PUBLISHED = "publicationDate-datePublication"
TENDER_CLOSE = "tenderClosingDate-appelOffresDateCloture"
TENDER_STATUS = "tenderStatus-appelOffresStatut-eng"
TENDER_DESC = "tenderDescription-descriptionAppelOffres-eng"
TENDER_DESC_FR = "tenderDescription-descriptionAppelOffres-fra"
ENTITY = "contractingEntityName-nomEntitContractante-eng"
ENTITY_FR = "contractingEntityName-nomEntitContractante-fra"
PROVINCE = "contractingEntityAddressProvince-entiteContractanteAdresseProvince-eng"
END_USER = "endUserEntitiesName-nomEntitesUtilisateurFinal-eng"
CONTACT_NAME = "contactInfoName-informationsContactNom"
CONTACT_EMAIL = "contactInfoEmail-informationsContactCourriel"
EXTERNAL_URL = "noticeURL-URLavis-eng"
AWARD_DESC = "awardDescription-descriptionAttribution-eng"
AWARD_DESC_FR = "awardDescription-descriptionAttribution-fra"
AWARD_STATUS = "awardStatus-attributionStatut-eng"
AWARD_DATE = "contractAwardDate-dateAttributionContrat"
SUPPLIER = "supplierLegalName-nomLegalFournisseur-eng"
TOTAL_VALUE = "totalContractValue-valeurTotaleContrat"
CONTRACT_AMOUNT = "contractAmount-montantContrat"
CURRENCY = "contractCurrency-contratMonnaie"


def fiscal_start_year(moment: datetime) -> int:
    return moment.year if moment.month >= 4 else moment.year - 1


def award_csv_urls(now: datetime, recency_days: int, limit: int = MAX_AWARD_FILES) -> list[str]:
    """Najnovije fiskalne godine koje seku zadati prozor. Starije se ne vuku u istom prolazu."""
    window = max(0, recency_days)
    start = now - timedelta(days=window)
    year = fiscal_start_year(now)
    oldest = fiscal_start_year(start)
    urls: list[str] = []
    while year >= oldest and len(urls) < limit:
        urls.append(AWARD_CSV.format(start=year, end=year + 1))
        year -= 1
    return urls


def notice_url(reference: str, kind: str) -> str:
    segment = "award-notice" if kind == "award" else "tender-notice"
    token = quote(reference.strip(), safe="-._")
    return f"https://canadabuys.canada.ca/en/tender-opportunities/{segment}/{token}"


def _money(value: str | None) -> float | None:
    if not value:
        return None
    try:
        number = float(value.replace(",", "").replace(" ", ""))
    except ValueError:
        return None
    if number <= 0:
        return None
    return number


def _cell(row: dict, *keys: str, limit: int = 1500) -> str:
    for key in keys:
        text = clean_text(row.get(key) or "", limit)
        if text:
            return text
    return ""


def _buyer(row: dict) -> tuple[str, str]:
    entity = _cell(row, ENTITY, ENTITY_FR, limit=300)
    end_user = _cell(row, END_USER, limit=300)
    if end_user and "*" not in end_user and ";" not in end_user and len(end_user) <= 200:
        return end_user, entity
    return entity, entity


def parse_canada_csv(text: str, kind: str, config: SearchConfig, file_url: str, now: datetime | None = None) -> list[Discovered]:
    moment = now or datetime.now(timezone.utc)
    found: list[Discovered] = []
    seen: set[str] = set()
    for row in csv.DictReader(io.StringIO(text)):
        reference = (row.get(REFERENCE) or "").strip()
        if not reference:
            continue
        amendment = (row.get(AMENDMENT) or "").strip()
        record_id = f"{reference}:{amendment or '0'}"
        if record_id in seen:
            continue
        title = _cell(row, TITLE, TITLE_FR, limit=300)
        if kind == "award":
            description = _cell(row, AWARD_DESC, AWARD_DESC_FR)
            published = (row.get(PUBLISHED) or row.get(AWARD_DATE) or "").strip()
        else:
            description = _cell(row, TENDER_DESC, TENDER_DESC_FR)
            published = (row.get(PUBLISHED) or "").strip()
        if not title or not relevant(f"{title} {description}", config.keywords):
            continue
        buyer, contracting = _buyer(row)
        if not buyer:
            continue
        level = procurement_level(title, description)
        if level == "D":
            continue
        published_age = age_days(published, moment)
        if kind == "award":
            if not published or published_age is None or published_age > config.recency_days:
                continue
            status = (row.get(AWARD_STATUS) or "").strip()
            signal = "closed" if status.lower() == "cancelled" else "past_award"
            amount = _money(row.get(TOTAL_VALUE)) or _money(row.get(CONTRACT_AMOUNT))
            currency = (row.get(CURRENCY) or "").strip() or "CAD"
        else:
            status = (row.get(TENDER_STATUS) or "").strip()
            deadline = parse_date(row.get(TENDER_CLOSE))
            still_open = status.lower() == "open" and (deadline is None or deadline >= moment)
            if not still_open and (published_age is None or published_age > config.recency_days):
                continue
            signal = "open_procurement" if still_open else "closed"
            amount = None
            currency = ""
        seen.add(record_id)
        supplier = _cell(row, SUPPLIER, limit=300)
        external = (row.get(EXTERNAL_URL) or "").strip()
        led_by = ""
        if contracting and contracting != buyer:
            led_by = f" Ugovor administrira {contracting}."
        amount_note = ""
        if kind == "award" and amount is None:
            amount_note = " Iznos u fajlu nije objavljen ili je nula; to nije budžet."
        found.append(
            Discovered(
                source_name="canada_buys",
                source_record_id=record_id,
                source_url=notice_url(reference, kind),
                organization_name=buyer,
                country="CA",
                region=_cell(row, PROVINCE, limit=120),
                title=title,
                excerpt=description or title,
                explanation=(
                    "Javni zapis CanadaBuys. Ustanova je naručilac ili navedeni krajnji korisnik, ne dobavljač. "
                    "Tekst pokazuje nabavku ili dodelu, ne stanje njihovih PDF, EPUB ili veb fajlova."
                    + led_by
                ),
                limitations=(
                    "Izvor je zvanični CSV. Dodele nisu otvoren poziv. "
                    "U jednoj pretrazi stižu otvoreni oglasi i najviše dve poslednje fiskalne godine dodela. "
                    "Rokovi u fajlu su istočno vreme, upisani bez zone."
                    + amount_note
                ),
                kind="award" if kind == "award" else "procurement_notice",
                level=level,
                published_at=published or None,
                procurement_signal=signal,
                amount=amount,
                supplier_name=supplier,
                notice_status=status,
                currency=currency,
                contact_name=_cell(row, CONTACT_NAME, limit=200),
                contact_email=_cell(row, CONTACT_EMAIL, limit=200),
                raw={
                    "reference": reference,
                    "file_url": file_url,
                    "external_notice_url": external,
                    "supplier": supplier,
                    "contracting_entity": contracting,
                },
            )
        )
    rank = {"A": 0, "B": 1, "C": 2, "D": 3}
    found.sort(key=lambda item: rank.get(item.level, 9))
    return found[: config.max_per_source]


class CanadaBuysSource:
    name = "canada_buys"

    def search(self, config: SearchConfig, client: HttpClient, now: datetime | None = None) -> list[Discovered]:
        moment = now or datetime.now(timezone.utc)
        files = [("tender", OPEN_CSV)]
        files.extend(("award", url) for url in award_csv_urls(moment, config.recency_days))
        found: list[Discovered] = []
        errors: list[str] = []
        for kind, url in files:
            if len(found) >= config.max_per_source:
                break
            try:
                data = client.get_bytes(url, max_bytes=FILE_CAP, timeout=90)
            except (HttpError, OSError, ValueError) as exc:
                errors.append(str(exc))
                continue
            if len(data) >= FILE_CAP:
                errors.append(f"Fajl je na granici od {FILE_CAP} bajtova i nije čitan: {url}")
                continue
            narrowed = SearchConfig(**{**config.__dict__, "max_per_source": config.max_per_source - len(found)})
            found.extend(parse_canada_csv(data.decode("utf-8-sig", errors="replace"), kind, narrowed, url, moment))
        if errors and not found:
            raise HttpError("CanadaBuys nije pročitan. " + " ".join(errors))
        if errors:
            note = " Deo fajlova nije preuzet: " + " ".join(errors)
            for item in found:
                item.limitations += note
        return found
