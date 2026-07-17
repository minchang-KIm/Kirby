"""Release localization, formatting, and Korean font supply-chain contract."""

from __future__ import annotations

import hashlib
import json
import string
from pathlib import Path
from typing import Any
from urllib.error import HTTPError

import pygame
import pytest

from tools import fetch_font, generate_locales
from windsprig.content.loader import (
    PUBLIC_ABILITY_IDS,
    ContentError,
    load_campaign_catalog,
    load_reward_catalog,
)
from windsprig.content.models import LocaleCatalog
from windsprig.localization import Localizer, load_locale_catalog

CONTENT_DIR = Path("windsprig/content")
FONT_PATH = Path("assets/fonts/NotoSansKR[wght].ttf")
LICENSE_PATH = Path("assets/fonts/OFL-NotoSansKR.txt")
PINNED_COMMIT = "ec0464b978de222073645d6d3366f3fdf03376d8"


def _fields(value: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(value) if name is not None}


def test_locales_have_identical_keys_placeholders_and_release_coverage() -> None:
    catalog = load_locale_catalog(CONTENT_DIR)

    assert set(catalog.strings) == {"en", "ko"}
    assert set(catalog.strings["en"]) == set(catalog.strings["ko"])
    assert len(catalog.strings["en"]) >= 180
    for key in catalog.strings["en"]:
        assert _fields(catalog.strings["en"][key]) == _fields(catalog.strings["ko"][key])

    campaign = load_campaign_catalog(CONTENT_DIR)
    rewards = load_reward_catalog(CONTENT_DIR)
    referenced = {
        key
        for world in campaign.world_specs.values()
        for key in (world.name_key, world.identity_key, *world.mechanic_keys)
    }
    referenced.update(key for stage in campaign.stages.values() for key in (stage.name_key, stage.intro_key))
    referenced.update(
        f"boss.{boss_id}.name"
        for boss_id in (
            "rootjaw",
            "crucible_crab",
            "luma_eel",
            "volt_roc",
            "prism_warden",
            "the_stillness",
        )
    )
    referenced.update(reward.name_key for reward in rewards.mote_thresholds)
    enemy_ids = {spawn.kind for stage in campaign.stages.values() for spawn in stage.enemy_spawns}
    assert len(campaign.world_specs) == 6
    assert len(campaign.stages) == 30
    assert len(enemy_ids) == 18
    assert len(rewards.mote_thresholds) == 18
    referenced.update(f"enemy.{enemy_id}.name" for enemy_id in enemy_ids)
    referenced.update(f"ability.{ability_id}.name" for ability_id in PUBLIC_ABILITY_IDS)
    assert referenced <= set(catalog.strings["en"])
    assert catalog.strings == load_locale_catalog(CONTENT_DIR).strings
    assert catalog.strings["en"] == generate_locales.build()["en"]
    assert catalog.strings["ko"] == generate_locales.build()["ko"]


def test_localizer_formats_korean_and_has_explicit_english_diagnostic() -> None:
    ko = Localizer.load(CONTENT_DIR, "ko")

    assert ko.text("results.time", time="01:23.456") == "기록 01:23.456"
    assert ko.text("debug.english_only") == "English diagnostic"
    with pytest.raises(KeyError, match="missing locale key: unknown.release.key"):
        ko.text("unknown.release.key")


def test_localizer_rejects_unsupported_language_and_freezes_all_maps() -> None:
    catalog = load_locale_catalog(CONTENT_DIR)

    with pytest.raises(ValueError, match=r"^unsupported locale language: fr$"):
        Localizer.load(CONTENT_DIR, "fr")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        catalog.strings["fr"] = {}  # type: ignore[index]
    with pytest.raises(TypeError):
        catalog.strings["en"]["game.title"] = "Changed"  # type: ignore[index]


def test_english_fallback_is_restricted_to_the_explicit_diagnostic_seam() -> None:
    catalog = LocaleCatalog(
        {
            "en": {
                "debug.english_only": "English diagnostic",
                "release.only": "Release copy",
            },
            "ko": {},
        }
    )
    localizer = Localizer(catalog, "ko")

    assert localizer.text("debug.english_only") == "English diagnostic"
    with pytest.raises(KeyError, match="missing locale key: release.only"):
        localizer.text("release.only")


def test_localizer_reports_missing_format_values_without_retaining_arguments() -> None:
    localizer = Localizer.load(CONTENT_DIR, "en")
    values = {"current": 3, "maximum": 5}

    assert localizer.text("hud.hp", **values) == "HP 3/5"
    assert values == {"current": 3, "maximum": 5}
    with pytest.raises(
        KeyError,
        match=r"missing locale format value: maximum for key: hud\.hp",
    ):
        localizer.text("hud.hp", current=3)
    with pytest.raises(
        TypeError,
        match=r"locale format value current for key hud\.hp must be str, int, or float",
    ):
        localizer.text("hud.hp", current=object(), maximum=5)  # type: ignore[arg-type]


def test_locale_loader_rejects_placeholder_drift(tmp_path: Path) -> None:
    (tmp_path / "strings.en.json").write_text(
        '{"results.time":"Time {time}"}\n',
        encoding="utf-8",
    )
    (tmp_path / "strings.ko.json").write_text(
        '{"results.time":"기록 {seconds}"}\n',
        encoding="utf-8",
    )

    with pytest.raises((ContentError, ValueError), match="placeholder"):
        load_locale_catalog(tmp_path)


@pytest.mark.parametrize(
    ("document", "language", "message"),
    [
        ('{"title":"One","title":"Two"}', "en", r"locales\.en\.title: duplicate field"),
        ('{"title":""}', "en", r"locales\.en\.title: must be a non-empty string"),
        ('{"title":true}', "en", r"locales\.en\.title: must be a non-empty string"),
        ('["title"]', "en", r"locales\.en: must be an object"),
        ('{"title":"둘","title":"셋"}', "ko", r"locales\.ko\.title: duplicate field"),
    ],
)
def test_locale_adapter_preserves_canonical_loader_errors(
    tmp_path: Path,
    document: str,
    language: str,
    message: str,
) -> None:
    valid = '{"title":"Title"}'
    (tmp_path / "strings.en.json").write_text(document if language == "en" else valid, encoding="utf-8")
    (tmp_path / "strings.ko.json").write_text(document if language == "ko" else valid, encoding="utf-8")

    with pytest.raises(ContentError, match=rf"^{message}$"):
        load_locale_catalog(tmp_path)


def test_locale_loader_rejects_key_drift_malformed_and_unsafe_fields(tmp_path: Path) -> None:
    en_path = tmp_path / "strings.en.json"
    ko_path = tmp_path / "strings.ko.json"
    en_path.write_text('{"title":"Title"}\n', encoding="utf-8")
    ko_path.write_text('{"other":"제목"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match=r"^locale key sets differ: en-only=title; ko-only=other$"):
        load_locale_catalog(tmp_path)

    en_path.write_text('{"title":"Title {value"}\n', encoding="utf-8")
    ko_path.write_text('{"title":"제목 {value"}\n', encoding="utf-8")
    with pytest.raises(ContentError, match=r"^locales\.en\.title: invalid format string"):
        load_locale_catalog(tmp_path)

    en_path.write_text('{"title":"Title {value.__class__}"}\n', encoding="utf-8")
    ko_path.write_text('{"title":"제목 {value.__class__}"}\n', encoding="utf-8")
    with pytest.raises(ContentError, match=r"^locales\.en\.title: unsafe formatter field: value\.__class__$"):
        load_locale_catalog(tmp_path)

    en_path.write_text('{"title":"Title {value!z}"}\n', encoding="utf-8")
    ko_path.write_text('{"title":"제목 {value!z}"}\n', encoding="utf-8")
    with pytest.raises(ContentError, match=r"^locales\.en\.title: invalid formatter conversion: z$"):
        load_locale_catalog(tmp_path)

    en_path.write_text('{"title":"Title {value:z}"}\n', encoding="utf-8")
    ko_path.write_text('{"title":"제목 {value:z}"}\n', encoding="utf-8")
    with pytest.raises(ContentError, match=r"^locales\.en\.title: unsupported formatter specifier: z$"):
        load_locale_catalog(tmp_path)


def test_locale_generator_is_canonical_repeatable_and_lf_pinned() -> None:
    first = generate_locales.canonical_outputs()
    second = generate_locales.canonical_outputs()

    assert first == second
    assert tuple(first) == (
        Path("windsprig/content/strings.en.json"),
        Path("windsprig/content/strings.ko.json"),
    )
    assert len(generate_locales.build()["en"]) >= 180
    for relative_path, canonical in first.items():
        assert relative_path.read_bytes() == canonical.encode("utf-8")
        assert canonical.endswith("\n") and "\r" not in canonical
        assert json.loads(canonical)
    attributes = set(Path(".gitattributes").read_text(encoding="utf-8").splitlines())
    assert "windsprig/content/strings.en.json text eol=lf" in attributes
    assert "windsprig/content/strings.ko.json text eol=lf" in attributes


def test_locale_generator_check_is_no_write_and_reports_every_stale_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    content = tmp_path / "windsprig/content"
    content.mkdir(parents=True)
    en_path = content / "strings.en.json"
    ko_path = content / "strings.ko.json"
    en_path.write_bytes(b"en sentinel\n")
    ko_path.write_bytes(b"ko sentinel\n")
    before = {path: path.read_bytes() for path in (en_path, ko_path)}

    assert generate_locales.main(["--check"], root=tmp_path) == 1
    assert capsys.readouterr().out == ("STALE: windsprig/content/strings.en.json, windsprig/content/strings.ko.json\n")
    assert {path: path.read_bytes() for path in before} == before
    assert not tuple(tmp_path.rglob("*.tmp"))


def test_locale_generator_writes_then_checks_clean(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert generate_locales.main([], root=tmp_path) == 0
    assert capsys.readouterr().out == "locales: 209 keys in en/ko\n"
    for relative_path, canonical in generate_locales.canonical_outputs().items():
        assert (tmp_path / relative_path).read_bytes() == canonical.encode("utf-8")
    assert not tuple(tmp_path.rglob("*.tmp"))

    assert generate_locales.main(["--check"], root=tmp_path) == 0
    assert capsys.readouterr().out == "locales: 209 keys in en/ko\n"


def test_locale_generator_serializes_completely_before_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = tmp_path / "windsprig/content"
    content.mkdir(parents=True)
    paths = (content / "strings.en.json", content / "strings.ko.json")
    for path in paths:
        path.write_bytes(f"{path.name} sentinel\n".encode())
    before = {path: path.read_bytes() for path in paths}
    original_dumps = generate_locales.json.dumps
    calls = 0

    def fail_second(*args: object, **kwargs: object) -> str:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise TypeError("serialization failed")
        return original_dumps(*args, **kwargs)

    monkeypatch.setattr(generate_locales.json, "dumps", fail_second)
    with pytest.raises(TypeError, match="serialization failed"):
        generate_locales.main([], root=tmp_path)

    assert calls == 2
    assert {path: path.read_bytes() for path in before} == before
    assert not tuple(tmp_path.rglob("*.tmp"))


def test_locale_generator_rolls_back_a_partial_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = tmp_path / "windsprig/content"
    content.mkdir(parents=True)
    paths = (content / "strings.en.json", content / "strings.ko.json")
    for path in paths:
        path.write_bytes(f"{path.name} sentinel\n".encode())
    before = {path: path.read_bytes() for path in paths}
    real_replace = generate_locales.os.replace
    calls = 0

    def fail_once(source: str | Path, destination: str | Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("publication failed")
        real_replace(source, destination)

    monkeypatch.setattr(generate_locales, "_replace", fail_once)
    with pytest.raises(OSError, match="publication failed"):
        generate_locales.main([], root=tmp_path)

    assert {path: path.read_bytes() for path in before} == before
    assert not tuple(tmp_path.rglob("*.tmp"))


class _Response:
    def __init__(self, payload: object, final_url: str) -> None:
        self.payload = payload
        self.final_url = final_url

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def geturl(self) -> str:
        return self.final_url

    def read(self) -> Any:
        return self.payload


class _Opener:
    def __init__(self, result: _Response | HTTPError) -> None:
        self.result = result
        self.requests: list[tuple[str, float]] = []

    def open(self, url: str, *, timeout: float) -> _Response:
        self.requests.append((url, timeout))
        if isinstance(self.result, HTTPError):
            raise self.result
        return self.result


def test_font_fetcher_pins_https_commit_hashes_and_rejects_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert fetch_font.COMMIT == PINNED_COMMIT
    assert fetch_font.FILES == {
        "NotoSansKR[wght].ttf": (
            f"https://raw.githubusercontent.com/google/fonts/{PINNED_COMMIT}/ofl/notosanskr/NotoSansKR%5Bwght%5D.ttf",
            "194018e6b2b293a7964f037b25c0249ce1418bc9ab3c971060a03aa57861e252",
        ),
        "OFL-NotoSansKR.txt": (
            f"https://raw.githubusercontent.com/google/fonts/{PINNED_COMMIT}/ofl/notosanskr/OFL.txt",
            "1c05c68c34f9708415aada51f17e1b0092d2cea709bf4a94cd38114f9e73d7d9",
        ),
    }
    url = fetch_font.FILES["OFL-NotoSansKR.txt"][0]
    opener = _Opener(_Response(b"license", url + "?redirected=1"))
    monkeypatch.setattr(fetch_font, "build_opener", lambda *_handlers: opener)
    with pytest.raises(RuntimeError, match="redirect"):
        fetch_font.fetch_https(url)
    assert opener.requests == [(url, fetch_font.TIMEOUT_SECONDS)]
    assert 0 < fetch_font.TIMEOUT_SECONDS <= 30


def test_font_http_handler_rejects_redirect_before_following(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = fetch_font.FILES["OFL-NotoSansKR.txt"][0]
    redirected_url = "http://example.invalid/downgraded-license"
    handler = fetch_font._NoRedirectHandler()
    assert handler.redirect_request(None, None, 302, "Found", {}, redirected_url) is None
    opener = _Opener(HTTPError(url, 302, "Found", {"Location": redirected_url}, None))
    installed_handlers: list[object] = []

    def opener_factory(*handlers: object) -> _Opener:
        installed_handlers.extend(handlers)
        return opener

    monkeypatch.setattr(fetch_font, "build_opener", opener_factory)
    with pytest.raises(RuntimeError, match="redirect rejected"):
        fetch_font.fetch_https(url)

    assert len(installed_handlers) == 1
    assert isinstance(installed_handlers[0], fetch_font._NoRedirectHandler)
    assert opener.requests == [(url, fetch_font.TIMEOUT_SECONDS)]


def test_font_https_fetch_accepts_exact_bytes_and_rejects_scheme_and_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = fetch_font.FILES["OFL-NotoSansKR.txt"][0]

    monkeypatch.setattr(
        fetch_font,
        "build_opener",
        lambda *_handlers: _Opener(_Response(b"license", url)),
    )
    assert fetch_font.fetch_https(url) == b"license"

    with pytest.raises(ValueError, match="must use HTTPS"):
        fetch_font.fetch_https("http://example.invalid/font.ttf")

    monkeypatch.setattr(
        fetch_font,
        "build_opener",
        lambda *_handlers: _Opener(_Response(bytearray(b"license"), url)),
    )
    with pytest.raises(TypeError, match="expected bytes"):
        fetch_font.fetch_https(url)


def test_font_fetcher_rejects_non_bytes_before_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def non_bytes(_url: str) -> bytes:
        return bytearray(b"not bytes")  # type: ignore[return-value]

    with pytest.raises(TypeError, match="expected bytes"):
        fetch_font.download_files(tmp_path, non_bytes)
    assert not (tmp_path / "assets/fonts").exists()


def test_font_fetcher_validates_every_payload_before_atomic_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payloads = {"font.bin": b"font payload", "license.txt": b"license payload"}
    files = {
        name: (f"https://example.invalid/{name}", hashlib.sha256(payload).hexdigest())
        for name, payload in payloads.items()
    }
    monkeypatch.setattr(fetch_font, "FILES", files)
    font_root = tmp_path / "assets/fonts"
    font_root.mkdir(parents=True)
    paths = tuple(font_root / name for name in files)
    for path in paths:
        path.write_bytes(f"{path.name} sentinel".encode())
    before = {path: path.read_bytes() for path in paths}

    def truncated(url: str) -> bytes:
        name = url.rsplit("/", maxsplit=1)[-1]
        return payloads[name] if name == "font.bin" else b"truncated"

    with pytest.raises(RuntimeError, match="hash mismatch for license.txt"):
        fetch_font.download_files(tmp_path, truncated)

    assert {path: path.read_bytes() for path in before} == before
    assert not tuple(tmp_path.rglob("*.tmp"))


def test_font_fetcher_check_is_offline_no_write_and_detects_tampering(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    called = False

    def forbidden(_url: str) -> bytes:
        nonlocal called
        called = True
        raise AssertionError("check mode must remain offline")

    assert fetch_font.main(["--check"], root=tmp_path, fetcher=forbidden) == 1
    assert called is False
    assert not (tmp_path / "assets").exists()
    assert capsys.readouterr().out == ("INVALID: assets/fonts/NotoSansKR[wght].ttf, assets/fonts/OFL-NotoSansKR.txt\n")


def test_font_fetcher_downloads_then_checks_clean_offline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payloads = {"font.bin": b"font payload", "license.txt": b"license payload"}
    files = {
        name: (f"https://example.invalid/{name}", hashlib.sha256(payload).hexdigest())
        for name, payload in payloads.items()
    }
    monkeypatch.setattr(fetch_font, "FILES", files)

    def fetcher(url: str) -> bytes:
        return payloads[url.rsplit("/", maxsplit=1)[-1]]

    assert fetch_font.main([], root=tmp_path, fetcher=fetcher) == 0
    assert capsys.readouterr().out == "font: Noto Sans KR at pinned Google Fonts commit\n"
    assert fetch_font.main(["--check"], root=tmp_path, fetcher=lambda _url: b"forbidden") == 0
    assert capsys.readouterr().out == "font: Noto Sans KR at pinned Google Fonts commit\n"
    assert not tuple(tmp_path.rglob("*.tmp"))


def test_font_fetcher_rolls_back_a_partial_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payloads = {"font.bin": b"font payload", "license.txt": b"license payload"}
    files = {
        name: (f"https://example.invalid/{name}", hashlib.sha256(payload).hexdigest())
        for name, payload in payloads.items()
    }
    monkeypatch.setattr(fetch_font, "FILES", files)
    font_root = tmp_path / "assets/fonts"
    font_root.mkdir(parents=True)
    paths = tuple(font_root / name for name in files)
    for path in paths:
        path.write_bytes(f"{path.name} sentinel".encode())
    before = {path: path.read_bytes() for path in paths}
    real_replace = fetch_font.os.replace
    calls = 0

    def fail_once(source: str | Path, destination: str | Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("publication failed")
        real_replace(source, destination)

    monkeypatch.setattr(fetch_font, "_replace", fail_once)

    def fetcher(url: str) -> bytes:
        return payloads[url.rsplit("/", maxsplit=1)[-1]]

    with pytest.raises(OSError, match="publication failed"):
        fetch_font.download_files(tmp_path, fetcher)
    assert {path: path.read_bytes() for path in before} == before
    assert not tuple(tmp_path.rglob("*.tmp"))


def test_font_license_ledger_records_only_present_task_5_asset_provenance() -> None:
    ledger = Path("assets/LICENSES.md").read_text(encoding="utf-8")
    for expected in (
        "Noto Sans KR",
        "NotoSansKR[wght].ttf",
        "OFL-NotoSansKR.txt",
        PINNED_COMMIT,
        "194018e6b2b293a7964f037b25c0249ce1418bc9ab3c971060a03aa57861e252",
        "1c05c68c34f9708415aada51f17e1b0092d2cea709bf4a94cd38114f9e73d7d9",
        "The pinned Noto Sans KR source is redistributed unmodified.",
        "WindsprigSansKR.ttf",
        "4211e2545aa28f0a9e6c72d61a9996663b3160f7b6ce54d6563e065543743f58",
        "assets/generated/art-provenance.json",
        "assets/generated/audio-provenance.json",
    ):
        assert expected in ledger


def test_bundled_font_and_license_match_pinned_release_files() -> None:
    attributes = set(Path(".gitattributes").read_text(encoding="utf-8").splitlines())
    assert "assets/fonts/NotoSansKR[[]wght].ttf binary" in attributes
    assert "assets/fonts/WindsprigSansKR.ttf binary" in attributes
    assert "assets/fonts/OFL-NotoSansKR.txt binary" in attributes
    assert hashlib.sha256(FONT_PATH.read_bytes()).hexdigest() == (
        "194018e6b2b293a7964f037b25c0249ce1418bc9ab3c971060a03aa57861e252"
    )
    assert hashlib.sha256(LICENSE_PATH.read_bytes()).hexdigest() == (
        "1c05c68c34f9708415aada51f17e1b0092d2cea709bf4a94cd38114f9e73d7d9"
    )
    pygame.font.init()
    font = pygame.font.Font(str(FONT_PATH), 28)
    sample = "바람싹 메아리 수집 완료 설정 접근성"
    assert all(metric is not None for metric in font.metrics(sample))
    assert font.render(sample, True, "white").get_bounding_rect().width > 200
