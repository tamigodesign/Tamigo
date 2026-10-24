"""Rečnici po pojmu. Podrazumevano se ne dodaju uz korisnikove ključne reči."""

from __future__ import annotations

from tamigo_intel.config import SearchConfig

LANGUAGE_NAMES = {
    "en": "engleski",
    "de": "nemački",
    "fr": "francuski",
    "it": "italijanski",
    "nl": "holandski",
    "da": "danski",
    "fi": "finski",
    "es": "španski",
    "sl": "slovenački",
}

# Fraze koje se stvarno javljaju u oglasima. Nisu doslovan prevod reči accessibility.
CONCEPTS = {
    "pdf_accessibility": {
        "en": "PDF accessibility",
        "de": "barrierefreie PDF",
        "fr": "accessibilité des PDF",
        "it": "accessibilità dei PDF",
        "nl": "toegankelijke PDF",
        "da": "tilgængelig PDF",
        "fi": "saavutettava PDF",
        "es": "accesibilidad de PDF",
        "sl": "dostopnost PDF",
    },
    "epub_accessibility": {
        "en": "EPUB accessibility",
        "de": "barrierefreies EPUB",
        "fr": "accessibilité EPUB",
        "it": "accessibilità EPUB",
        "nl": "toegankelijke EPUB",
        "da": "tilgængelig EPUB",
        "fi": "saavutettava EPUB",
        "es": "accesibilidad EPUB",
        "sl": "dostopnost EPUB",
    },
    "wcag": {
        "en": "WCAG 2.2",
        "de": "WCAG 2.2",
        "fr": "WCAG 2.2",
        "it": "WCAG 2.2",
        "nl": "WCAG 2.2",
        "da": "WCAG 2.2",
        "fi": "WCAG 2.2",
        "es": "WCAG 2.2",
        "sl": "WCAG 2.2",
    },
    "audit": {
        "en": "accessibility audit",
        "de": "Prüfung der Barrierefreiheit",
        "fr": "audit d'accessibilité",
        "it": "audit di accessibilità",
        "nl": "audit digitale toegankelijkheid",
        "da": "tilgængelighedsrevision",
        "fi": "saavutettavuuden auditointi",
        "es": "auditoría de accesibilidad",
        "sl": "revizija dostopnosti",
    },
    "remediation": {
        "en": "accessibility remediation",
        "de": "barrierefreie Aufbereitung",
        "fr": "mise en accessibilité",
        "it": "adeguamento dell'accessibilità",
        "nl": "toegankelijk maken van documenten",
        "da": "udbedring af tilgængelighed",
        "fi": "saavutettavuuden korjaus",
        "es": "adecuación de accesibilidad",
        "sl": "prilagoditev dostopnosti",
    },
    "documents": {
        "en": "accessible documents",
        "de": "barrierefreie Dokumente",
        "fr": "documents accessibles",
        "it": "documenti accessibili",
        "nl": "toegankelijke documenten",
        "da": "tilgængelige dokumenter",
        "fi": "saavutettavat asiakirjat",
        "es": "documentos accesibles",
        "sl": "dostopni dokumenti",
    },
    "digital": {
        "en": "digital accessibility",
        "de": "digitale Barrierefreiheit",
        "fr": "accessibilité numérique",
        "it": "accessibilità digitale",
        "nl": "digitale toegankelijkheid",
        "da": "digital tilgængelighed",
        "fi": "digitaalinen saavutettavuus",
        "es": "accesibilidad digital",
        "sl": "digitalna dostopnost",
    },
    "rgaa": {
        "fr": "RGAA",
    },
    "statement": {
        "en": "accessibility statement",
        "de": "Erklärung zur Barrierefreiheit",
        "fr": "déclaration d'accessibilité",
        "it": "dichiarazione di accessibilità",
        "nl": "toegankelijkheidsverklaring",
        "da": "tilgængelighedserklæring",
        "fi": "saavutettavuusseloste",
        "es": "declaración de accesibilidad",
        "sl": "izjava o dostopnosti",
    },
}

_TERM_LANGUAGE = {
    phrase.casefold(): language
    for phrases in CONCEPTS.values()
    for language, phrase in phrases.items()
}


def dictionary_terms(languages: list[str]) -> list[str]:
    chosen = [code for code in languages if code in LANGUAGE_NAMES]
    terms: list[str] = []
    seen: set[str] = set()
    for phrases in CONCEPTS.values():
        for code in chosen:
            phrase = phrases.get(code) or ""
            key = phrase.casefold()
            if phrase and key not in seen:
                seen.add(key)
                terms.append(phrase)
    return terms


def query_keywords(config: SearchConfig, limit: int = 16) -> list[str]:
    user = [item.strip() for item in config.keywords if item and item.strip()]
    if not config.multilingual:
        return user
    extra = dictionary_terms(config.search_languages)
    merged: list[str] = []
    seen: set[str] = set()
    index_user = 0
    index_extra = 0
    while len(merged) < limit and (index_user < len(user) or index_extra < len(extra)):
        if index_user < len(user):
            _add(merged, seen, user[index_user], limit)
            index_user += 1
        if len(merged) >= limit:
            break
        if index_extra < len(extra):
            _add(merged, seen, extra[index_extra], limit)
            index_extra += 1
    return merged


def language_of_term(term: str) -> str:
    return _TERM_LANGUAGE.get((term or "").casefold(), "")


def first_matching_term(text: str, keywords: list[str]) -> str:
    low = text.casefold()
    for keyword in keywords:
        key = keyword.strip()
        if len(key) >= 4 and key.casefold() in low:
            return key
    return ""


def _add(merged: list[str], seen: set[str], term: str, limit: int) -> None:
    key = term.casefold()
    if key in seen or len(merged) >= limit:
        return
    seen.add(key)
    merged.append(term)
