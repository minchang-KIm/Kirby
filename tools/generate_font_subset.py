"""Generate the deterministic Korean-capable font shipped by the runtimes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import tempfile
from collections.abc import Mapping, Sequence
from io import BytesIO
from pathlib import Path
from typing import Final, cast

import fontTools  # type: ignore[import-untyped]
from fontTools.subset import Options, Subsetter  # type: ignore[import-untyped]
from fontTools.ttLib import TTFont  # type: ignore[import-untyped]
from fontTools.varLib.instancer import instantiateVariableFont  # type: ignore[import-untyped]

# Direct script execution places ``tools/`` on sys.path instead of its parent.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.fetch_font import FILES

FONTTOOLS_VERSION: Final = "4.63.0"
SOURCE_FONT: Final = Path("assets/fonts/NotoSansKR[wght].ttf")
RUNTIME_FONT: Final = Path("assets/fonts/WindsprigSansKR.ttf")
RUNTIME_FONT_SHA256: Final = "12a7caf5a82170940ea1dd73112e70ea353edf0a0230621268593fb30ef98a53"
INSTANCE_WEIGHT: Final = 500
ASCII_CODEPOINTS: Final = frozenset(range(0x20, 0x7F))
LOCALE_PATHS: Final = (
    Path("windsprig/content/strings.en.json"),
    Path("windsprig/content/strings.ko.json"),
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _is_link_or_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    isjunction = getattr(os.path, "isjunction", None)
    if callable(isjunction) and isjunction(path):
        return True
    try:
        details = path.lstat()
    except FileNotFoundError:
        return False
    attributes = getattr(details, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)


def _regular_file(root: Path, relative: Path) -> Path:
    if _is_link_or_reparse(root) or not root.is_dir():
        raise ValueError(f"font subset source root must be a regular directory: {root}")
    current = root
    for part in relative.parts:
        current = current / part
        if _is_link_or_reparse(current):
            raise ValueError(f"font subset path is unsafe: {current}")
    if not current.is_file():
        raise FileNotFoundError(f"font subset source is missing: {current}")
    return current


def _load_locale(path: Path) -> Mapping[str, str]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or any(
        type(key) is not str or type(value) is not str for key, value in document.items()
    ):
        raise ValueError(f"locale must be a string mapping: {path}")
    return cast(dict[str, str], document)


def required_codepoints(root: Path) -> set[int]:
    """Return the stable glyph set for shipped bilingual copy and ASCII names."""

    if not isinstance(root, Path):
        raise TypeError("root must be a pathlib.Path")
    lexical_root = Path(os.path.abspath(root))
    codepoints = set(ASCII_CODEPOINTS)
    for relative in LOCALE_PATHS:
        catalog = _load_locale(_regular_file(lexical_root, relative))
        codepoints.update(ord(character) for value in catalog.values() for character in value)
    return codepoints


def subset_bytes(source_root: Path) -> bytes:
    """Build one static, timestamp-free subset from the pinned variable source."""

    if fontTools.__version__ != FONTTOOLS_VERSION:
        raise RuntimeError(
            f"fontTools {FONTTOOLS_VERSION} is required for byte-stable output; found {fontTools.__version__}"
        )
    lexical_root = Path(os.path.abspath(source_root))
    source = _regular_file(lexical_root, SOURCE_FONT)
    payload = source.read_bytes()
    expected_source_hash = FILES[SOURCE_FONT.name][1]
    if _sha256(payload) != expected_source_hash:
        raise RuntimeError("pinned Noto Sans KR source hash mismatch")

    required = required_codepoints(lexical_root)
    font = TTFont(BytesIO(payload), recalcTimestamp=False, lazy=False)
    try:
        source_cmap = font.getBestCmap()
        if source_cmap is None:
            raise RuntimeError("pinned Noto Sans KR source has no Unicode cmap")
        missing = sorted(required - set(source_cmap))
        if missing:
            preview = ", ".join(f"U+{value:04X}" for value in missing[:8])
            raise RuntimeError(f"pinned font is missing required glyphs: {preview}")

        instantiateVariableFont(
            font,
            {"wght": INSTANCE_WEIGHT},
            inplace=True,
            optimize=True,
        )
        options = Options()
        options.recalc_timestamp = False
        options.layout_features = ["*"]
        options.name_IDs = ["*"]
        options.name_languages = ["*"]
        options.notdef_glyph = True
        options.notdef_outline = True
        options.recommended_glyphs = True
        subsetter = Subsetter(options=options)
        subsetter.populate(unicodes=required)
        subsetter.subset(font)

        output = BytesIO()
        font.recalcTimestamp = False
        font.save(output, reorderTables=True)
        generated = output.getvalue()
    finally:
        font.close()

    if not generated:
        raise RuntimeError("font subset generation produced an empty payload")
    if _sha256(generated) != RUNTIME_FONT_SHA256:
        raise RuntimeError("runtime font subset hash drifted from the reviewed artifact")
    return generated


def _output_directory(root: Path) -> Path:
    if not isinstance(root, Path):
        raise TypeError("root must be a pathlib.Path")
    lexical_root = Path(os.path.abspath(root))
    if not lexical_root.exists():
        lexical_root.mkdir(parents=True)
    if _is_link_or_reparse(lexical_root) or not lexical_root.is_dir():
        raise ValueError(f"font subset root must be a regular directory: {lexical_root}")
    current = lexical_root
    for part in RUNTIME_FONT.parent.parts:
        current = current / part
        if current.exists() or _is_link_or_reparse(current):
            if _is_link_or_reparse(current) or not current.is_dir():
                raise ValueError(f"font subset output directory is unsafe: {current}")
        else:
            current.mkdir()
    return current


def _publish(path: Path, payload: bytes) -> None:
    if path.exists() or _is_link_or_reparse(path):
        if _is_link_or_reparse(path) or not path.is_file():
            raise ValueError(f"font subset output is unsafe: {path}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def generate(root: Path = Path("."), *, source_root: Path | None = None) -> Path:
    """Atomically publish the runtime subset under ``root``."""

    source = root if source_root is None else source_root
    payload = subset_bytes(source)
    directory = _output_directory(root)
    output = directory / RUNTIME_FONT.name
    _publish(output, payload)
    return output


def check(root: Path = Path("."), *, source_root: Path | None = None) -> tuple[str, ...]:
    """Return deterministic drift findings without modifying ``root``."""

    source = root if source_root is None else source_root
    expected = subset_bytes(source)
    lexical_root = Path(os.path.abspath(root))
    if _is_link_or_reparse(lexical_root) or not lexical_root.is_dir():
        raise ValueError(f"font subset root must be a regular directory: {lexical_root}")
    output = lexical_root
    for part in RUNTIME_FONT.parts:
        output = output / part
        if _is_link_or_reparse(output):
            raise ValueError(f"font subset output is unsafe: {output}")
    if _is_link_or_reparse(output) or not output.is_file():
        return (f"STALE {RUNTIME_FONT.as_posix()}",)
    if output.read_bytes() != expected:
        return (f"STALE {RUNTIME_FONT.as_posix()}",)
    return ()


def main(argv: Sequence[str] | None = None, *, root: Path = Path(".")) -> int:
    """Generate or verify the committed runtime font subset."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args(argv)
    if arguments.check:
        findings = check(root)
        if findings:
            print("\n".join(findings))
            return 1
    else:
        generate(root)
    size = (Path(os.path.abspath(root)) / RUNTIME_FONT).stat().st_size
    print(f"font subset: {len(required_codepoints(root))} codepoints, {size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
