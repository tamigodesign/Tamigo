"""Razvrstavanje greške izvora. HTTP 403 nije isto što i TLS."""

from __future__ import annotations

import json

FAILURE_LABELS = {
    "tls": "TLS provera sertifikata nije prošla.",
    "auth": "HTTP 401: prijava ili ključ nije prihvaćen.",
    "forbidden": "HTTP 403: pristup je odbijen. Ovo nije greška sertifikata.",
    "not_found": "HTTP 404: adresa izvora nije nađena.",
    "rate_limit": "HTTP 429: izvor traži pauzu.",
    "server": "HTTP 5xx: izvor je prijavio grešku servera.",
    "timeout": "Isteklo je vreme čekanja.",
    "malformed": "Odgovor nije moguće pročitati.",
    "configuration": "Izvor čeka podešavanje.",
    "other": "Greška izvora.",
}


def failure_label(kind: str) -> str:
    return FAILURE_LABELS.get(kind, FAILURE_LABELS["other"])


def failure_kind(exc: BaseException) -> str:
    text = str(exc).lower()
    if "certificate" in text or "certificate verify failed" in text or "tls" in text or "ssl:" in text:
        return "tls"
    status = getattr(exc, "status", None)
    if status == 401:
        return "auth"
    if status == 403:
        return "forbidden"
    if status == 404:
        return "not_found"
    if status == 429:
        return "rate_limit"
    if isinstance(status, int) and status >= 500:
        return "server"
    if isinstance(exc, TimeoutError) or "timed out" in text or "timeout" in text:
        return "timeout"
    if isinstance(exc, json.JSONDecodeError) or (isinstance(exc, ValueError) and "json" in text):
        return "malformed"
    return "other"
