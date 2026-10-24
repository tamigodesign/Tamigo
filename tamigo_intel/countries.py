"""Zemlje za izbor. Pokrivenost opisuje stvarne izvore, ne ceo portal zemlje."""

from __future__ import annotations

ISO3_TO_ISO2 = {
    "usa": "US",
    "can": "CA",
    "gbr": "GB",
    "deu": "DE",
    "nld": "NL",
    "fra": "FR",
    "ita": "IT",
    "aut": "AT",
    "dnk": "DK",
    "bel": "BE",
    "fin": "FI",
    "che": "CH",
    "esp": "ES",
    "svn": "SI",
    "irl": "IE",
    "aus": "AU",
    "nzl": "NZ",
    "swe": "SE",
    "pol": "PL",
    "prt": "PT",
    "lux": "LU",
    "cze": "CZ",
    "svk": "SK",
    "hun": "HU",
    "rou": "RO",
    "bgr": "BG",
    "est": "EE",
    "lva": "LV",
    "ltu": "LT",
    "grc": "GR",
    "cyp": "CY",
    "mlt": "MT",
    "hrv": "HR",
    "nor": "NO",
}

# TED pokriva naslov oglasa. Nacionalni portali navedeni u napomeni nisu povezani.
_TED = "TED: samo naslov oglasa. Nacionalni portal nije povezan. Nije potpuna pokrivenost."

COUNTRIES = [
    {"code": "US", "name": "Sjedinjene Države", "groups": ["north_america", "english"], "coverage": "USAspending (istorijske dodele) i SAM.gov (traži ključ). Nije potpuna pokrivenost."},
    {"code": "CA", "name": "Kanada", "groups": ["north_america", "english"], "coverage": "CanadaBuys: otvoreni CSV i najviše dve fiskalne godine dodela. Pokrajinski portali nisu povezani."},
    {"code": "GB", "name": "Ujedinjeno Kraljevstvo", "groups": ["europe", "english"], "coverage": "Contracts Finder. Find a Tender je poseban izvor i podrazumevano je isključen. Nije potpuna pokrivenost."},
    {"code": "DE", "name": "Nemačka", "groups": ["eu", "europe"], "coverage": _TED + " bund.de nije povezan."},
    {"code": "NL", "name": "Holandija", "groups": ["eu", "europe"], "coverage": _TED + " TenderNed nije povezan."},
    {"code": "FR", "name": "Francuska", "groups": ["eu", "europe"], "coverage": _TED + " BOAMP nije povezan."},
    {"code": "IT", "name": "Italija", "groups": ["eu", "europe"], "coverage": _TED + " ANAC nije povezan."},
    {"code": "AT", "name": "Austrija", "groups": ["eu", "europe"], "coverage": _TED + " ANKÖ nije povezan."},
    {"code": "DK", "name": "Danska", "groups": ["eu", "europe"], "coverage": _TED + " udbud.dk nije povezan."},
    {"code": "BE", "name": "Belgija", "groups": ["eu", "europe"], "coverage": _TED + " e-Procurement nije povezan."},
    {"code": "FI", "name": "Finska", "groups": ["eu", "europe"], "coverage": _TED + " HILMA nije povezana."},
    {"code": "ES", "name": "Španija", "groups": ["eu", "europe"], "coverage": _TED + " Plataforma de Contratación nije povezana."},
    {"code": "SI", "name": "Slovenija", "groups": ["eu", "europe"], "coverage": _TED + " e-JN nije povezan."},
    {"code": "IE", "name": "Irska", "groups": ["eu", "europe", "english"], "coverage": _TED + " eTenders nije povezan."},
    {"code": "SE", "name": "Švedska", "groups": ["eu", "europe"], "coverage": _TED},
    {"code": "PL", "name": "Poljska", "groups": ["eu", "europe"], "coverage": _TED},
    {"code": "PT", "name": "Portugalija", "groups": ["eu", "europe"], "coverage": _TED},
    {"code": "LU", "name": "Luksemburg", "groups": ["eu", "europe"], "coverage": _TED},
    {"code": "CZ", "name": "Češka", "groups": ["eu", "europe"], "coverage": _TED},
    {"code": "SK", "name": "Slovačka", "groups": ["eu", "europe"], "coverage": _TED},
    {"code": "HU", "name": "Mađarska", "groups": ["eu", "europe"], "coverage": _TED},
    {"code": "RO", "name": "Rumunija", "groups": ["eu", "europe"], "coverage": _TED},
    {"code": "BG", "name": "Bugarska", "groups": ["eu", "europe"], "coverage": _TED},
    {"code": "HR", "name": "Hrvatska", "groups": ["eu", "europe"], "coverage": _TED},
    {"code": "EE", "name": "Estonija", "groups": ["eu", "europe"], "coverage": _TED},
    {"code": "LV", "name": "Letonija", "groups": ["eu", "europe"], "coverage": _TED},
    {"code": "LT", "name": "Litvanija", "groups": ["eu", "europe"], "coverage": _TED},
    {"code": "GR", "name": "Grčka", "groups": ["eu", "europe"], "coverage": _TED},
    {"code": "CY", "name": "Kipar", "groups": ["eu", "europe"], "coverage": _TED},
    {"code": "MT", "name": "Malta", "groups": ["eu", "europe"], "coverage": _TED},
    {"code": "CH", "name": "Švajcarska", "groups": ["europe"], "coverage": "Nije povezana. simap.ch nije ugrađen."},
    {"code": "NO", "name": "Norveška", "groups": ["europe"], "coverage": "Nije povezana."},
    {"code": "AU", "name": "Australija", "groups": ["english"], "coverage": "Nije povezana. AusTender je vraćao HTTP 403 i nije ugrađen."},
    {"code": "NZ", "name": "Novi Zeland", "groups": ["english"], "coverage": "Nije povezan."},
]

PRESETS = {
    "north_america": "Severna Amerika",
    "eu": "EU",
    "europe": "Evropa",
    "english": "Englesko govorno područje",
    "all": "Sve podešene zemlje",
    "none": "Ništa",
}

_BY_CODE = {item["code"]: item for item in COUNTRIES}


def country_by_code(code: str) -> dict | None:
    return _BY_CODE.get((code or "").upper())


def preset_codes(name: str) -> list[str]:
    if name == "all":
        return [item["code"] for item in COUNTRIES]
    if name == "none":
        return []
    return [item["code"] for item in COUNTRIES if name in item["groups"]]


def country_allowed(country: str, selected: list[str], restrict: bool) -> bool:
    """Bez filtera ostaje dosadašnje ponašanje: zemlja se ne odbacuje."""
    if not restrict:
        return True
    chosen = {(code or "").upper() for code in selected if code}
    if not chosen:
        return True
    code = (country or "").upper()
    return bool(code) and code in chosen
