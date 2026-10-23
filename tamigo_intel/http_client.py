from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Callable

from tamigo_intel.cancel import CancelToken
from tamigo_intel.redact import redact

USER_AGENT = "TamigoAccessibilityIntelligence/0.1 (local research; public-source prospecting)"
Transport = Callable[..., tuple[int, bytes, dict]]


class HttpError(Exception):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def _default_transport(method: str, url: str, body: bytes | None, headers: dict, timeout: float) -> tuple[int, bytes, dict]:
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read(), dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        return exc.code, payload, dict(exc.headers.items()) if exc.headers else {}


class HttpClient:
    def __init__(
        self,
        transport: Transport | None = None,
        min_interval: float = 1.0,
        timeout: float = 30.0,
        cancel: CancelToken | None = None,
        secrets: list[str] | None = None,
        sleeper: Callable[[float], None] | None = None,
        max_bytes: int = 20_000_000,
    ) -> None:
        self.transport = transport or _default_transport
        self.min_interval = min_interval
        self.timeout = timeout
        self.cancel = cancel
        self.secrets = secrets or []
        self.sleeper = sleeper or time.sleep
        self.max_bytes = max_bytes
        self._last_request = 0.0

    def _pace(self) -> None:
        if self.cancel:
            self.cancel.raise_if_cancelled()
        if self.min_interval <= 0:
            return
        wait = self.min_interval - (time.monotonic() - self._last_request)
        if wait > 0:
            self.sleeper(wait)
        if self.cancel:
            self.cancel.raise_if_cancelled()

    def request(self, method: str, url: str, payload: dict | None = None, headers: dict | None = None) -> tuple[int, bytes]:
        self._pace()
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        sent = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
        if body is not None:
            sent["Content-Type"] = "application/json"
        if headers:
            sent.update(headers)
        safe_url = redact(url, self.secrets)
        last_error: Exception | None = None
        for attempt in range(2):
            status, data, _response_headers = self.transport(method, url, body, sent, self.timeout)
            self._last_request = time.monotonic()
            if len(data) > self.max_bytes:
                data = data[: self.max_bytes]
            if status == 429 and attempt == 0:
                self.sleeper(0 if self.min_interval == 0 else min(self.min_interval, 2))
                continue
            if status >= 400:
                last_error = HttpError(f"HTTP {status} za {safe_url}", status=status)
                if status >= 500 and attempt == 0:
                    continue
                raise last_error
            return status, data
        if last_error:
            raise last_error
        raise HttpError(f"Neuspešan zahtev {safe_url}")

    def get_json(self, url: str, headers: dict | None = None) -> dict:
        _status, data = self.request("GET", url, headers=headers)
        return json.loads(data.decode("utf-8"))

    def post_json(self, url: str, payload: dict, headers: dict | None = None) -> dict:
        _status, data = self.request("POST", url, payload=payload, headers=headers)
        return json.loads(data.decode("utf-8"))

    def get_bytes(self, url: str, headers: dict | None = None, max_bytes: int | None = None) -> bytes:
        previous = self.max_bytes
        if max_bytes is not None:
            self.max_bytes = max_bytes
        try:
            _status, data = self.request("GET", url, headers=headers)
            return data
        finally:
            self.max_bytes = previous
