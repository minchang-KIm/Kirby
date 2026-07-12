"""Wrap the canonical Windsprig favicon in a deterministic Windows ICO file."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_ICO_HEADER_SIZE = 22


def build_icon_bytes(png: bytes) -> bytes:
    """Return a one-image ICO that embeds the supplied PNG without re-encoding it."""

    if not isinstance(png, bytes):
        raise TypeError("png must be bytes")
    if len(png) < 24 or not png.startswith(_PNG_SIGNATURE) or png[12:16] != b"IHDR":
        raise ValueError("source must be a canonical PNG with an IHDR first chunk")
    width, height = struct.unpack_from(">II", png, 16)
    if not 1 <= width <= 256 or not 1 <= height <= 256:
        raise ValueError("Windows icon dimensions must be between 1 and 256 pixels")
    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack(
        "<BBBBHHII",
        0 if width == 256 else width,
        0 if height == 256 else height,
        0,
        0,
        1,
        32,
        len(png),
        _ICO_HEADER_SIZE,
    )
    return header + entry + png


def generate_icon(source: Path, destination: Path, *, check: bool = False) -> Path:
    """Write or verify the deterministic icon derived from ``source``."""

    if not isinstance(source, Path) or not isinstance(destination, Path):
        raise TypeError("source and destination must be pathlib.Path values")
    expected = build_icon_bytes(source.read_bytes())
    if check:
        if not destination.is_file() or destination.read_bytes() != expected:
            raise ValueError(f"Windows icon is missing or stale: {destination}")
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(expected)
    return destination


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify the tracked icon without modifying it")
    parser.add_argument("--source", type=Path, default=root / "assets/generated/ui/favicon.png")
    parser.add_argument("--output", type=Path, default=root / "assets/branding/windsprig.ico")
    args = parser.parse_args()
    generate_icon(args.source.resolve(), args.output.resolve(), check=args.check)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
