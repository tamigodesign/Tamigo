"""TLS za spakovani program. Provera sertifikata ostaje uključena."""

from __future__ import annotations

import os
import ssl

import certifi


def ca_bundle() -> str:
    path = certifi.where()
    if not os.path.isfile(path):
        raise RuntimeError(f"Nedostaje paket sertifikata: {path}")
    return path


def install_ca_bundle() -> str:
    """Usmerava podrazumevani kontekst na Mozilla CA iz certifi. Ne isključuje proveru."""
    path = ca_bundle()
    os.environ["SSL_CERT_FILE"] = path
    os.environ["REQUESTS_CA_BUNDLE"] = path
    context = verified_context()
    if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
        raise RuntimeError("TLS provera sertifikata nije uključena.")
    return path


def verified_context() -> ssl.SSLContext:
    context = ssl.create_default_context(cafile=ca_bundle())
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context
