"""Validate strict campaign content and print stable actionable findings."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from windsprig.content.loader import (
    ContentError,
    load_asset_manifest,
    load_catalog_bundle,
    load_locales,
)
from windsprig.content.validator import validate_bundle


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--content", type=Path, default=Path("windsprig/content"))
    parser.add_argument("--assets", type=Path, default=Path("assets"))
    parser.add_argument(
        "--all",
        action="store_true",
        dest="validate_all",
        help="run the complete release validation gate",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Load all catalogs and distinguish schema failures from semantic reports."""

    args = _parser().parse_args(argv)
    try:
        bundle = load_catalog_bundle(args.content)
        manifest = load_asset_manifest(args.content / "assets.json")
        locales = load_locales(args.content)
    except ContentError as error:
        print(f"SCHEMA {error}")
        print("FAILED: content schema could not be loaded")
        return 2

    report = validate_bundle(bundle, manifest, locales, asset_root=args.assets)
    for issue in report.errors:
        print(f"ERROR {issue.code} {issue.path}: {issue.message}")
    if report.errors:
        print(f"FAILED: {len(report.errors)} validation errors")
        return 1

    counts = report.counts
    print(
        "OK: "
        f"{counts['worlds']} worlds, {counts['stages']} stages, "
        f"{counts['bosses']} bosses, {counts['motes']} motes, "
        f"{counts['locales']} locales, {counts['music']} music cues, "
        f"{counts['sfx']} sfx cues, "
        f"{counts['duplicate_layouts']} duplicate layouts"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
