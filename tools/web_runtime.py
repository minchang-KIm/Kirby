"""Verify, cache, and stage the pinned same-origin browser runtime."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, cast
from urllib.parse import urlsplit
from urllib.request import urlopen

from tools.release_common import _DirectoryHandle, _protected_directory_chain, _verify_directory

RUNTIME_MANIFEST_NAME: Final = "runtime-manifest.json"
RUNTIME_CDN_PATH: Final = "runtime/0.9.3/"
_RUNTIME_ID: Final = "pygbag-0.9.3-cpython312-vt"
_REQUIRED_RUNTIME_PATHS: Final = frozenset(
    {
        "runtime/browserfs/2.0.0/browserfs.min.js",
        "runtime/0.9.3/pythons.js",
        "runtime/0.9.3/cpythonrc.py",
        "runtime/0.9.3/empty.ogg",
        "runtime/0.9.3/cpython312/main.js",
        "runtime/0.9.3/cpython312/main.data",
        "runtime/0.9.3/cpython312/main.wasm",
        "runtime/vt.js",
    }
)
_SHA256_PATTERN: Final = re.compile(r"[0-9a-f]{64}")
_EXTERNAL_URL_PATTERN: Final = re.compile(r"https?://", re.IGNORECASE)

type RuntimeFetcher = Callable[[str], bytes]


class RuntimeIntegrityError(ValueError):
    """Report a stable browser-runtime integrity or graph violation."""


@dataclass(frozen=True, slots=True)
class RuntimeAsset:
    """Describe one immutable remote payload and its artifact destination."""

    artifact_path: str
    source_url: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class RuntimeManifest:
    """Own the complete audited browser-runtime dependency graph."""

    schema_version: int
    runtime_id: str
    assets: tuple[RuntimeAsset, ...]
    sha256: str


def _fail(code: str, detail: str) -> RuntimeIntegrityError:
    return RuntimeIntegrityError(f"{code}: {detail}")


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _fail("runtime_manifest_duplicate_key", key)
        result[key] = value
    return result


def _require_fields(
    value: Mapping[str, object],
    expected: frozenset[str],
    context: str,
) -> None:
    actual = frozenset(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        raise _fail(
            "runtime_manifest_fields",
            f"{context} missing={missing!r} unknown={unknown!r}",
        )


def _parse_asset(value: object, index: int) -> RuntimeAsset:
    if not isinstance(value, dict):
        raise _fail("runtime_manifest_asset_type", f"assets[{index}] must be an object")
    asset_object = cast(dict[str, object], value)
    _require_fields(
        asset_object,
        frozenset({"artifact_path", "source_url", "size_bytes", "sha256"}),
        f"assets[{index}]",
    )
    artifact_path = asset_object["artifact_path"]
    source_url = asset_object["source_url"]
    size_bytes = asset_object["size_bytes"]
    sha256 = asset_object["sha256"]
    if type(artifact_path) is not str:
        raise _fail("runtime_manifest_path", f"assets[{index}].artifact_path")
    pure_path = PurePosixPath(artifact_path)
    if (
        pure_path.is_absolute()
        or ".." in pure_path.parts
        or not artifact_path.startswith("runtime/")
        or "\\" in artifact_path
    ):
        raise _fail("runtime_manifest_path", artifact_path)
    if type(source_url) is not str:
        raise _fail("runtime_manifest_https", f"assets[{index}].source_url")
    parsed_url = urlsplit(source_url)
    if (
        parsed_url.scheme != "https"
        or not parsed_url.netloc
        or parsed_url.username is not None
        or parsed_url.password is not None
        or parsed_url.query
        or parsed_url.fragment
    ):
        raise _fail("runtime_manifest_https", source_url)
    if type(size_bytes) is not int or size_bytes <= 0:
        raise _fail("runtime_manifest_size", f"{artifact_path}: {size_bytes!r}")
    if type(sha256) is not str or _SHA256_PATTERN.fullmatch(sha256) is None:
        raise _fail("runtime_manifest_sha256", f"{artifact_path}: {sha256!r}")
    return RuntimeAsset(
        artifact_path=artifact_path,
        source_url=source_url,
        size_bytes=size_bytes,
        sha256=sha256,
    )


def load_runtime_manifest(path: Path) -> RuntimeManifest:
    """Load the checked-in manifest and reject any incomplete dependency graph."""
    raw = path.read_bytes()
    try:
        value = json.loads(raw, object_pairs_hook=_strict_object)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise _fail("runtime_manifest_json", str(error)) from error
    if not isinstance(value, dict):
        raise _fail("runtime_manifest_root", "root must be an object")
    root = cast(dict[str, object], value)
    _require_fields(
        root,
        frozenset({"schema_version", "runtime_id", "assets"}),
        "root",
    )
    if root["schema_version"] != 1:
        raise _fail("runtime_manifest_schema", repr(root["schema_version"]))
    if root["runtime_id"] != _RUNTIME_ID:
        raise _fail("runtime_manifest_id", repr(root["runtime_id"]))
    asset_values = root["assets"]
    if not isinstance(asset_values, list):
        raise _fail("runtime_manifest_assets", "assets must be an array")
    assets = tuple(_parse_asset(item, index) for index, item in enumerate(asset_values))
    paths = [asset.artifact_path for asset in assets]
    if len(paths) != len(set(paths)):
        raise _fail("runtime_manifest_asset_set", "duplicate artifact path")
    if frozenset(paths) != _REQUIRED_RUNTIME_PATHS:
        missing = sorted(_REQUIRED_RUNTIME_PATHS - frozenset(paths))
        unknown = sorted(frozenset(paths) - _REQUIRED_RUNTIME_PATHS)
        raise _fail(
            "runtime_manifest_asset_set",
            f"missing={missing!r} unknown={unknown!r}",
        )
    return RuntimeManifest(
        schema_version=1,
        runtime_id=_RUNTIME_ID,
        assets=assets,
        sha256=hashlib.sha256(raw).hexdigest(),
    )


def fetch_https(url: str) -> bytes:
    """Fetch one manifest-authorized HTTPS payload without implicit fallback."""
    with urlopen(url, timeout=120) as response:  # noqa: S310 - validated manifest HTTPS
        final_url = cast(str, response.geturl())
        if final_url != url:
            raise _fail("runtime_fetch_redirect", f"expected {url}, received {final_url}")
        return cast(bytes, response.read())


def _verify_payload(payload: bytes, asset: RuntimeAsset, context: str) -> None:
    if len(payload) != asset.size_bytes:
        raise _fail(
            f"{context}_size_mismatch",
            f"{asset.artifact_path}: expected {asset.size_bytes}, received {len(payload)}",
        )
    digest = hashlib.sha256(payload).hexdigest()
    if digest != asset.sha256:
        raise _fail(
            f"{context}_sha256_mismatch",
            f"{asset.artifact_path}: expected {asset.sha256}, received {digest}",
        )


def _verify_file(path: Path, asset: RuntimeAsset, context: str) -> None:
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise _fail(f"{context}_read_failed", f"{asset.artifact_path}: {error}") from error
    _verify_payload(payload, asset, context)


@contextmanager
def _protected_runtime_directory(path: Path, context: str) -> Iterator[_DirectoryHandle]:
    try:
        with _protected_directory_chain(path, create=True) as directory:
            yield directory
    except RuntimeIntegrityError:
        raise
    except (OSError, ValueError) as error:
        raise _fail(f"{context}_path", f"{path}: {error}") from error


def cache_runtime_asset(
    asset: RuntimeAsset,
    cache_dir: Path,
    fetcher: RuntimeFetcher = fetch_https,
) -> Path:
    """Return one verified cache entry, publishing a fetch with atomic replacement."""
    with _protected_runtime_directory(cache_dir, "runtime_cache") as cache_directory:
        target = cache_dir / asset.sha256
        _verify_directory(cache_directory)
        if target.exists():
            _verify_file(target, asset, "runtime_cache")
            return target

        try:
            payload = fetcher(asset.source_url)
        except Exception as error:
            raise _fail("runtime_fetch_failed", f"{asset.source_url}: {error}") from error
        if type(payload) is not bytes:
            raise _fail("runtime_fetch_type", f"{asset.artifact_path}: expected bytes")
        _verify_payload(payload, asset, "runtime_fetch")
        _verify_directory(cache_directory)

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=cache_dir,
                prefix=f".{asset.sha256}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary.write(payload)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            _verify_file(temporary_path, asset, "runtime_fetch")
            _verify_directory(cache_directory)
            os.replace(temporary_path, target)
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        _verify_file(target, asset, "runtime_cache")
        return target


def _manifest_payload(manifest: RuntimeManifest) -> Mapping[str, object]:
    return {
        "schema_version": manifest.schema_version,
        "runtime_id": manifest.runtime_id,
        "assets": [
            {
                "artifact_path": asset.artifact_path,
                "source_url": asset.source_url,
                "size_bytes": asset.size_bytes,
                "sha256": asset.sha256,
            }
            for asset in manifest.assets
        ],
    }


def stage_runtime_assets(
    manifest: RuntimeManifest,
    cache_dir: Path,
    output: Path,
    fetcher: RuntimeFetcher = fetch_https,
) -> int:
    """Stage every verified cache entry and an auditable manifest into the artifact."""
    total = 0
    for asset in manifest.assets:
        destination = output / Path(*PurePosixPath(asset.artifact_path).parts)
        with _protected_runtime_directory(destination.parent, "runtime_stage"):
            cached = cache_runtime_asset(asset, cache_dir, fetcher)
            shutil.copyfile(cached, destination)
            _verify_file(destination, asset, "runtime_stage")
        total += asset.size_bytes
    staged_manifest = output / "runtime" / RUNTIME_MANIFEST_NAME
    with _protected_runtime_directory(staged_manifest.parent, "runtime_stage"):
        staged_manifest.write_text(
            json.dumps(_manifest_payload(manifest), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return total


def verify_same_origin_runtime_index(path: Path) -> None:
    """Reject generated launch pages that retain any external runtime edge."""
    html = path.read_text(encoding="utf-8")
    if _EXTERNAL_URL_PATTERN.search(html) is not None:
        raise _fail("runtime_index_external_url", str(path))
    required = (
        'src="runtime/browserfs/2.0.0/browserfs.min.js"',
        'src="runtime/0.9.3/pythons.js"',
        'data-os="vt,snd,gui"',
        'cdn: "runtime/0.9.3/"',
    )
    for snippet in required:
        if snippet not in html:
            raise _fail("runtime_index_graph", f"missing {snippet!r}")
    if 'data-os="vtx' in html or "xtermjsixel" in html or "../vtx.js" in html:
        raise _fail("runtime_index_terminal", "vtx/xterm runtime is forbidden")
