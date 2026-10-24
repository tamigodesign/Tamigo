"""Ulaz za PyInstaller. Finder pokreće ovaj fajl unutar .app paketa."""

from __future__ import annotations

import multiprocessing
import sys


def main() -> None:
    multiprocessing.freeze_support()
    from tamigo_intel.tls import install_ca_bundle

    install_ca_bundle()
    from tamigo_intel.__main__ import main as run

    run(sys.argv[1:])


if __name__ == "__main__":
    main()
