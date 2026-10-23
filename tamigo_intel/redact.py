from __future__ import annotations

import logging
import re

_QUERY_SECRET = re.compile(r"((?:api_key|access_token|token)=)[^&\s]+", re.IGNORECASE)


def redact(text: str, secrets: list[str] | None = None) -> str:
    cleaned = _QUERY_SECRET.sub(r"\1***", text)
    for secret in secrets or []:
        if secret and len(secret) >= 4:
            cleaned = cleaned.replace(secret, "***")
    return cleaned


class RedactFilter(logging.Filter):
    def __init__(self, secrets: list[str] | None = None) -> None:
        super().__init__()
        self.secrets = list(secrets or [])

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg, self.secrets)
        if record.args:
            record.args = tuple(
                redact(arg, self.secrets) if isinstance(arg, str) else arg
                for arg in record.args
            )
        return True
