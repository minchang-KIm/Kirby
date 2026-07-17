"""Validate strict campaign content and print stable actionable findings."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
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
from windsprig.content.models import ValidationIssue, ValidationReport
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
    parser.add_argument("--report", type=Path, help="write one canonical JSON evidence report")
    return parser


def _issue_payload(issue: ValidationIssue) -> dict[str, str]:
    return {"code": issue.code, "message": issue.message, "path": issue.path}


def _write_report(path: Path, status: str, report: ValidationReport | None, schema_error: str | None = None) -> None:
    if report is None:
        errors = [] if schema_error is None else [{"code": "schema", "message": schema_error, "path": "catalog"}]
        counts: dict[str, int] = {}
        warnings: list[dict[str, str]] = []
    else:
        errors = [_issue_payload(issue) for issue in report.errors]
        counts = dict(report.counts)
        warnings = [_issue_payload(issue) for issue in report.warnings]
    payload: dict[str, object] = {
        "counts": counts,
        "errors": errors,
        "status": status,
        "warnings": warnings,
    }
    encoded = (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    destination = path.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: Sequence[str] | None = None) -> int:
    """Load all catalogs and distinguish schema failures from semantic reports."""

    parser = _parser()
    args = parser.parse_args(argv)
    if args.report is not None and not args.validate_all:
        parser.error("--report requires --all")
    try:
        bundle = load_catalog_bundle(args.content)
        manifest = load_asset_manifest(args.content / "assets.json")
        locales = load_locales(args.content)
    except ContentError as error:
        if args.report is not None:
            _write_report(args.report, "schema_error", None, str(error))
        print(f"SCHEMA {error}")
        print("FAILED: content schema could not be loaded")
        return 2

    report = validate_bundle(bundle, manifest, locales, asset_root=args.assets)
    if args.report is not None:
        _write_report(args.report, "passed" if report.ok else "failed", report)
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
