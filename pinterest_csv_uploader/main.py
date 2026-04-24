"""CLI entry point for Pinterest CSV upload automation."""
from __future__ import annotations

import argparse
import sys

from config import load_config
from logger import setup_logger
from uploader import PinterestCSVUploader


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pinterest-csv-upload",
        description="Automate Pinterest login and bulk CSV upload.",
    )
    p.add_argument(
        "--csv",
        help="Path to the CSV file to upload (overrides PINTEREST_CSV_PATH).",
    )
    p.add_argument(
        "--env-file",
        help="Path to a .env file (defaults to ./.env if present).",
    )
    p.add_argument(
        "--headless",
        action="store_true",
        help="Force headless browser (overrides env). PRD default is visible.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        cfg = load_config(csv_override=args.csv, env_file=args.env_file)
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    if args.headless:
        cfg.headless = True

    log = setup_logger(cfg.artifacts_dir)
    log.info("Starting Pinterest CSV upload — csv=%s", cfg.csv_path)

    result = PinterestCSVUploader(cfg, log).run()

    if result.success:
        log.info("DONE: %s", result.message)
        return 0
    log.error("FAILED: %s", result.message)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
