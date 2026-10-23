from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LegalHint:
    jurisdiction: str
    title: str
    source_url: str
    note: str
    applicability: str = "requires_verification"


HINTS: tuple[LegalHint, ...] = (
    LegalHint(
        "US",
        "ADA i smernice Ministarstva pravde za veb sadržaj javnih tela",
        "https://www.ada.gov/resources/2024-03-08-web-rule/",
        "Pravilo iz 2024. odnosi se na određena javna tela, ne na svaku ustanovu u SAD. Rokovi i obuhvat se proveravaju na zvaničnom tekstu.",
    ),
    LegalHint(
        "US",
        "Section 508",
        "https://www.section508.gov/",
        "Odnosi se na savezne agencije i određene nabavke, ne na svaku privatnu firmu.",
    ),
    LegalHint(
        "EU",
        "European Accessibility Act",
        "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32019L0882",
        "Direktiva se prenosi nacionalnim propisima. Ne primenjuje se automatski na svaku organizaciju u Evropi.",
    ),
    LegalHint(
        "GB",
        "Obaveza pristupačnosti javnog sektora u UK",
        "https://www.gov.uk/guidance/accessibility-requirements-for-public-sector-websites-and-apps",
        "Važi za tela javnog sektora u obimu koji propis navodi. Samo sedište u UK nije dokaz obaveze ni kvara.",
    ),
    LegalHint(
        "AU",
        "Australian Government Digital Service Standard i DDA kontekst",
        "https://www.dta.gov.au/help-and-advice/digital-service-standard",
        "Standardi i Zakon o diskriminaciji imaju različit obuhvat. Primenljivost se proverava posebno.",
    ),
    LegalHint(
        "INT",
        "WCAG 2.2",
        "https://www.w3.org/TR/WCAG22/",
        "Tehnički standard. Nije sam po sebi zakon i automatski test ne utvrđuje punu usklađenost.",
    ),
    LegalHint(
        "INT",
        "PDF/UA",
        "https://www.iso.org/standard/64599.html",
        "Standard za pristupačan PDF. Nije dokaz da konkretan dokument ne ispunjava zahtev.",
    ),
    LegalHint(
        "INT",
        "EPUB Accessibility 1.1",
        "https://www.w3.org/TR/epub-a11y-11/",
        "Specifikacija za EPUB. Odsustvo metapodatka nije samo po sebi dokaz nepristupačnog sadržaja.",
    ),
)


def hints_for(country: str) -> list[LegalHint]:
    code = (country or "").upper()
    selected = []
    for hint in HINTS:
        if hint.jurisdiction in {code, "INT"} or (code in {"UK"} and hint.jurisdiction == "GB"):
            selected.append(hint)
        elif hint.jurisdiction == "EU" and code in {"DE", "FR", "NL", "IE", "AT", "BE", "ES", "IT", "SE", "PL"}:
            selected.append(hint)
    return selected
