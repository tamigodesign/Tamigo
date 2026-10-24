"""Kredencijali. Na macOS idu u Keychain. U config.json se ne upisuju."""

from __future__ import annotations

import sys

SECRET_FIELDS = ("sam_api_key", "github_token", "openai_api_key")
SERVICE = "Tamigo Accessibility Intelligence"


class MemoryVault:
    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def get(self, name: str) -> str:
        return self._data.get(name, "")

    def set(self, name: str, value: str) -> None:
        if value:
            self._data[name] = value
        else:
            self._data.pop(name, None)

    def configured(self, name: str) -> bool:
        return bool(self._data.get(name))


class KeychainVault:
    def get(self, name: str) -> str:
        import keyring

        value = keyring.get_password(SERVICE, name)
        return value or ""

    def set(self, name: str, value: str) -> None:
        import keyring

        if not value:
            try:
                keyring.delete_password(SERVICE, name)
            except keyring.errors.PasswordDeleteError:
                return
            return
        keyring.set_password(SERVICE, name, value)

    def configured(self, name: str) -> bool:
        return bool(self.get(name))


_MEMORY = MemoryVault()


def default_vault():
    if sys.platform == "darwin":
        return KeychainVault()
    return _MEMORY
