from __future__ import annotations

import argparse
import json
import sys

from tamigo_intel.config import load_config
from tamigo_intel.db import Database
from tamigo_intel.paths import db_path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Tamigo Accessibility Intelligence")
    parser.add_argument("--search", action="store_true", help="Pokreni pretragu bez prozora")
    parser.add_argument("--export", choices=["csv", "json"])
    parser.add_argument("--qualified-only", action="store_true")
    parser.add_argument("--output")
    parser.add_argument("--max-organizations", type=int)
    args = parser.parse_args(argv)
    if args.search or args.export:
        from tamigo_intel.exporting import export_csv, export_json
        from tamigo_intel.pipeline import run_search

        config = load_config()
        if args.max_organizations:
            config.max_organizations = args.max_organizations
        database = Database(db_path())
        if args.search:
            result = run_search(database, config, on_progress=print)
            print(json.dumps({"status": result["status"], "stored": result["stored"]}, ensure_ascii=False))
        if args.export:
            if not args.output:
                raise SystemExit("Za izvoz navedite --output.")
            from pathlib import Path

            if args.export == "csv":
                count = export_csv(database, Path(args.output), qualified_only=args.qualified_only)
            else:
                count = export_json(database, Path(args.output), qualified_only=args.qualified_only)
            print(count)
        return
    from tamigo_intel.ui.app import main as gui_main

    gui_main()


if __name__ == "__main__":
    main(sys.argv[1:])
