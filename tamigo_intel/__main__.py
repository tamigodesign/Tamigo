from __future__ import annotations

import argparse
import json
import platform
import sys

from tamigo_intel import __version__
from tamigo_intel.config import load_config
from tamigo_intel.db import Database
from tamigo_intel.paths import data_dir, db_path, is_frozen
from tamigo_intel.redact import redact
from tamigo_intel.vault import SECRET_FIELDS


def _emit(message: str) -> None:
    """Windowed .app na macOS nema konzolu. Upis u fajl je izvor istine, ispis je sporedan."""
    if sys.stdout is None:
        return
    try:
        print(message, flush=True)
    except (OSError, ValueError):
        return


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Tamigo Accessibility Intelligence")
    parser.add_argument("--search", action="store_true", help="Pokreni pretragu bez prozora")
    parser.add_argument("--export", choices=["csv", "json"])
    parser.add_argument("--qualified-only", action="store_true")
    parser.add_argument("--output")
    parser.add_argument("--max-organizations", type=int)
    parser.add_argument("--self-check", action="store_true", help="Upiši da li je paket pokrenut i gde je baza")
    parser.add_argument("--stats", action="store_true", help="Ispiši brojeve iz postojeće baze")
    args = parser.parse_args(argv)
    if args.self_check:
        payload = {
            "version": __version__,
            "frozen": is_frozen(),
            "platform": sys.platform,
            "machine": platform.machine(),
            "data_dir": str(data_dir()),
            "db_path": str(db_path()),
        }
        (data_dir() / "self-check.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _emit(json.dumps(payload, ensure_ascii=False))
        return
    if args.stats and not args.search and not args.export:
        database = Database(db_path())
        text = json.dumps(database.dashboard(), ensure_ascii=False, default=str)
        (data_dir() / "stats.json").write_text(text, encoding="utf-8")
        _emit(text)
        return
    if args.search or args.export:
        from tamigo_intel.exporting import export_csv, export_json
        from tamigo_intel.pipeline import run_search

        config = load_config()
        if args.max_organizations:
            config.max_organizations = args.max_organizations
        database = Database(db_path())
        if args.search:
            try:
                result = run_search(database, config, on_progress=_emit)
            except Exception as exc:
                secret_values = [str(getattr(config, name) or "") for name in SECRET_FIELDS]
                (data_dir() / "search-result.json").write_text(
                    json.dumps(
                        {"status": "error", "error": redact(str(exc), secret_values)},
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                raise
            payload = {"status": result["status"], "stored": result["stored"], "log": result["log"]}
            (data_dir() / "search-result.json").write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )
            _emit(json.dumps({"status": result["status"], "stored": result["stored"]}, ensure_ascii=False))
        if args.export:
            if not args.output:
                raise SystemExit("Za izvoz navedite --output.")
            from pathlib import Path

            if args.export == "csv":
                count = export_csv(database, Path(args.output), qualified_only=args.qualified_only)
            else:
                count = export_json(database, Path(args.output), qualified_only=args.qualified_only)
            _emit(str(count))
        return
    from tamigo_intel.ui.app import main as gui_main

    gui_main()


if __name__ == "__main__":
    main(sys.argv[1:])
