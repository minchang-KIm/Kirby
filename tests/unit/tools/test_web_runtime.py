"""Deterministic integrity contracts for the self-hosted browser runtime."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tools import web_runtime
from tools.web_runtime import (
    RuntimeAsset,
    RuntimeIntegrityError,
    RuntimeManifest,
    cache_runtime_asset,
    fetch_https,
    load_runtime_manifest,
    stage_runtime_assets,
    verify_same_origin_runtime_index,
)

_ROOT = Path(__file__).resolve().parents[3]

_PINNED_GRAPH = (
    (
        "runtime/browserfs/2.0.0/browserfs.min.js",
        "https://cdnjs.cloudflare.com/ajax/libs/BrowserFS/2.0.0/browserfs.min.js",
        247_362,
        "f6f7e897d91b43d284a92865fb67a3729b044a5f2e4002362bcd6f9b5115911a",
    ),
    (
        "runtime/0.9.3/pythons.js",
        "https://pygame-web.github.io/cdn/0.9.3/pythons.js",
        69_205,
        "6da43e3e62c3db933421b99681e8ef99ed9b0ce1589ed8a0c69b88443278e019",
    ),
    (
        "runtime/0.9.3/cpythonrc.py",
        "https://pygame-web.github.io/cdn/0.9.3/cpythonrc.py",
        50_426,
        "b8a0b8168b58ef7c38c17d4705c9cbe1751fa667a0a6d26ed26f0537134735de",
    ),
    (
        "runtime/0.9.3/empty.ogg",
        "https://pygame-web.github.io/cdn/0.9.3/empty.ogg",
        4_035,
        "884c20d864222b845aa78fb078ec370f4ddaa203cd92ace28440ed7733403b40",
    ),
    (
        "runtime/0.9.3/cpython312/main.js",
        "https://pygame-web.github.io/cdn/0.9.3/cpython312/main.js",
        849_985,
        "01c4e4dc7145a482ad259d8272ce73d97b58ec2a141bfb57e620347730d159c7",
    ),
    (
        "runtime/0.9.3/cpython312/main.data",
        "https://pygame-web.github.io/cdn/0.9.3/cpython312/main.data",
        6_668_609,
        "b068df4d59b06b113cfc3c4d6419bdf699d2c2eeb547c9119e2044c98cdc4a59",
    ),
    (
        "runtime/0.9.3/cpython312/main.wasm",
        "https://pygame-web.github.io/cdn/0.9.3/cpython312/main.wasm",
        13_447_111,
        "3cfb882de90feeb367325f0c58731932880c8f424fb5a670b98d035ae862b280",
    ),
    (
        "runtime/vt.js",
        "https://pygame-web.github.io/cdn/vt.js",
        14_656,
        "ef5d853b3dd27ebcb62b5d88f92b51606a0a6f11c75f9af10426b8e93781c2c3",
    ),
)


def _asset(payload: bytes = b"runtime") -> RuntimeAsset:
    return RuntimeAsset(
        artifact_path="runtime/test/runtime.bin",
        source_url="https://runtime.example.invalid/runtime.bin",
        size_bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def test_checked_in_manifest_pins_the_exact_closed_vt_dependency_graph() -> None:
    manifest = load_runtime_manifest(_ROOT / "web" / "runtime-manifest.json")

    assert manifest.schema_version == 1
    assert manifest.runtime_id == "pygbag-0.9.3-cpython312-vt"
    assert (
        tuple((asset.artifact_path, asset.source_url, asset.size_bytes, asset.sha256) for asset in manifest.assets)
        == _PINNED_GRAPH
    )


def test_manifest_rejects_a_missing_required_runtime_asset(tmp_path: Path) -> None:
    source = json.loads((_ROOT / "web" / "runtime-manifest.json").read_text(encoding="utf-8"))
    source["assets"] = source["assets"][:-1]
    path = tmp_path / "runtime-manifest.json"
    path.write_text(json.dumps(source), encoding="utf-8")

    with pytest.raises(RuntimeIntegrityError, match="runtime_manifest_asset_set"):
        load_runtime_manifest(path)


@pytest.mark.parametrize(
    ("field", "value", "error_code"),
    [
        ("size_bytes", 0, "runtime_manifest_size"),
        ("sha256", "not-a-sha", "runtime_manifest_sha256"),
        ("source_url", "http://example.invalid/runtime.js", "runtime_manifest_https"),
    ],
)
def test_manifest_rejects_invalid_integrity_pins(
    tmp_path: Path,
    field: str,
    value: object,
    error_code: str,
) -> None:
    source = json.loads((_ROOT / "web" / "runtime-manifest.json").read_text(encoding="utf-8"))
    source["assets"][0][field] = value
    path = tmp_path / "runtime-manifest.json"
    path.write_text(json.dumps(source), encoding="utf-8")

    with pytest.raises(RuntimeIntegrityError, match=error_code):
        load_runtime_manifest(path)


def test_cache_reuses_a_verified_payload_without_fetching_again(tmp_path: Path) -> None:
    payload = b"runtime"
    asset = _asset(payload)
    calls: list[str] = []

    first = cache_runtime_asset(
        asset,
        tmp_path,
        lambda url: calls.append(url) or payload,
    )
    second = cache_runtime_asset(
        asset,
        tmp_path,
        lambda _url: (_ for _ in ()).throw(AssertionError("verified cache must be reused")),
    )

    assert first == second
    assert first.read_bytes() == payload
    assert calls == [asset.source_url]


def test_cache_rejects_corruption_without_refetching_or_overwriting(tmp_path: Path) -> None:
    asset = _asset()
    cache_path = tmp_path / asset.sha256
    tmp_path.mkdir(exist_ok=True)
    cache_path.write_bytes(b"bad")

    with pytest.raises(RuntimeIntegrityError, match="runtime_cache_size_mismatch"):
        cache_runtime_asset(
            asset,
            tmp_path,
            lambda _url: (_ for _ in ()).throw(AssertionError("corruption must be explicit")),
        )

    assert cache_path.read_bytes() == b"bad"


def test_cache_rejects_remote_drift_without_publishing_a_partial(tmp_path: Path) -> None:
    asset = _asset()

    with pytest.raises(RuntimeIntegrityError, match="runtime_fetch_size_mismatch"):
        cache_runtime_asset(asset, tmp_path, lambda _url: b"drift")

    assert list(tmp_path.iterdir()) == []


def test_cache_rejects_same_size_remote_hash_drift(tmp_path: Path) -> None:
    asset = _asset(b"runtime")

    with pytest.raises(RuntimeIntegrityError, match="runtime_fetch_sha256_mismatch"):
        cache_runtime_asset(asset, tmp_path, lambda _url: b"runtimf")

    assert list(tmp_path.iterdir()) == []


def test_cache_atomically_replaces_only_a_verified_temporary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = b"runtime"
    asset = _asset(payload)
    real_replace = web_runtime.os.replace
    replacements: list[tuple[Path, Path]] = []

    def verified_replace(source: str | Path, destination: str | Path) -> None:
        source_path = Path(source)
        destination_path = Path(destination)
        assert source_path.read_bytes() == payload
        assert not destination_path.exists()
        replacements.append((source_path, destination_path))
        real_replace(source_path, destination_path)

    monkeypatch.setattr(web_runtime.os, "replace", verified_replace)

    cached = cache_runtime_asset(asset, tmp_path, lambda _url: payload)

    assert cached == tmp_path / asset.sha256
    assert len(replacements) == 1
    assert not replacements[0][0].exists()


def test_default_fetcher_rejects_a_redirect_from_the_exact_manifest_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RedirectedResponse:
        def __enter__(self) -> RedirectedResponse:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def geturl(self) -> str:
            return "https://mirror.example.invalid/runtime.js"

        def read(self) -> bytes:
            return b"runtime"

    monkeypatch.setattr(web_runtime, "urlopen", lambda _url, timeout: RedirectedResponse())

    with pytest.raises(RuntimeIntegrityError, match="runtime_fetch_redirect"):
        fetch_https("https://origin.example.invalid/runtime.js")


def test_stage_runtime_assets_copies_verified_cache_and_manifest_before_measurement(
    tmp_path: Path,
) -> None:
    payload = b"runtime"
    asset = _asset(payload)
    manifest = RuntimeManifest(
        schema_version=1,
        runtime_id="test-runtime",
        assets=(asset,),
        sha256="a" * 64,
    )
    output = tmp_path / "artifact"

    total = stage_runtime_assets(
        manifest,
        tmp_path / "cache",
        output,
        lambda _url: payload,
    )

    assert total == len(payload)
    assert (output / asset.artifact_path).read_bytes() == payload
    staged_manifest = json.loads((output / "runtime" / "runtime-manifest.json").read_text(encoding="utf-8"))
    assert staged_manifest["runtime_id"] == "test-runtime"


def test_generated_index_rejects_external_or_vtx_runtime_references(tmp_path: Path) -> None:
    index = tmp_path / "index.html"
    index.write_text(
        '<script src="https://pygame-web.github.io/cdn/0.9.3/pythons.js" data-os="vtx,snd,gui"></script>',
        encoding="utf-8",
    )

    with pytest.raises(RuntimeIntegrityError, match="runtime_index_external_url"):
        verify_same_origin_runtime_index(index)


def test_generated_index_accepts_only_the_relative_vt_runtime_graph(tmp_path: Path) -> None:
    index = tmp_path / "index.html"
    index.write_text(
        '<script src="runtime/browserfs/2.0.0/browserfs.min.js"></script>'
        '<script src="runtime/0.9.3/pythons.js" data-os="vt,snd,gui"></script>'
        '<script>config = {cdn: "runtime/0.9.3/"};</script>',
        encoding="utf-8",
    )

    verify_same_origin_runtime_index(index)
