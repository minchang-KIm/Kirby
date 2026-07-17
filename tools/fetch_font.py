"""Fetch and verify the pinned Noto Sans KR font and retained OFL."""

from __future__ import annotations

import argparse
import hashlib
import os
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final, cast
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, build_opener

COMMIT: Final = "ec0464b978de222073645d6d3366f3fdf03376d8"
TIMEOUT_SECONDS: Final = 30.0
FILES: Mapping[str, tuple[str, str]] = {
    "NotoSansKR[wght].ttf": (
        f"https://raw.githubusercontent.com/google/fonts/{COMMIT}/ofl/notosanskr/NotoSansKR%5Bwght%5D.ttf",
        "194018e6b2b293a7964f037b25c0249ce1418bc9ab3c971060a03aa57861e252",
    ),
    "OFL-NotoSansKR.txt": (
        f"https://raw.githubusercontent.com/google/fonts/{COMMIT}/ofl/notosanskr/OFL.txt",
        "1c05c68c34f9708415aada51f17e1b0092d2cea709bf4a94cd38114f9e73d7d9",
    ),
}

type FontFetcher = Callable[[str], bytes]


class _NoRedirectHandler(HTTPRedirectHandler):
    """Stop urllib before it can issue a request to a redirect target."""

    def redirect_request(
        self,
        req: Any,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        _ = req, fp, code, msg, headers, newurl
        return None


def digest(data: bytes) -> str:
    """Return the lowercase SHA-256 digest for one complete payload."""

    return hashlib.sha256(data).hexdigest()


def fetch_https(url: str) -> bytes:
    """Fetch one exact HTTPS URL without accepting redirects or non-bytes."""

    if not url.startswith("https://"):
        raise ValueError(f"font source must use HTTPS: {url}")
    opener = build_opener(_NoRedirectHandler())
    try:
        with opener.open(url, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 - exact pinned HTTPS source
            final_url = cast(str, response.geturl())
            if final_url != url:
                raise RuntimeError(f"font source redirect rejected: expected {url}, received {final_url}")
            payload = response.read()
    except HTTPError as error:
        if error.code in {301, 302, 303, 307, 308}:
            location = error.headers.get("Location", "<missing>")
            raise RuntimeError(f"font source redirect rejected: expected {url}, received {location}") from error
        raise
    if type(payload) is not bytes:
        raise TypeError(f"font fetch expected bytes for {url}")
    return payload


def invalid_files(root: Path = Path(".")) -> tuple[Path, ...]:
    """Return missing or hash-invalid pinned files without writing or fetching."""

    invalid: list[Path] = []
    for name, (_, expected) in FILES.items():
        relative = Path("assets/fonts") / name
        path = root / relative
        if not path.is_file() or digest(path.read_bytes()) != expected:
            invalid.append(relative)
    return tuple(invalid)


def _temporary_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return temporary


def _replace(source: str | Path, destination: str | Path) -> None:
    os.replace(source, destination)


def _restore(path: Path, previous: bytes | None) -> None:
    if previous is None:
        path.unlink(missing_ok=True)
        return
    temporary = _temporary_file(path, previous)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _publish(root: Path, payloads: Mapping[str, bytes]) -> None:
    destinations = {name: root / "assets/fonts" / name for name in payloads}
    previous = {
        name: destination.read_bytes() if destination.exists() else None for name, destination in destinations.items()
    }
    temporary: dict[str, Path] = {}
    try:
        for name, payload in payloads.items():
            temporary[name] = _temporary_file(destinations[name], payload)
        published: list[str] = []
        try:
            for name in payloads:
                _replace(temporary[name], destinations[name])
                published.append(name)
        except BaseException:
            for name in reversed(published):
                _restore(destinations[name], previous[name])
            raise
    finally:
        for path in temporary.values():
            path.unlink(missing_ok=True)


def download_files(root: Path = Path("."), fetcher: FontFetcher = fetch_https) -> None:
    """Validate every remote payload before transactionally publishing any file."""

    payloads: dict[str, bytes] = {}
    for name, (url, expected) in FILES.items():
        payload = fetcher(url)
        if type(payload) is not bytes:
            raise TypeError(f"font fetch expected bytes for {name}")
        if digest(payload) != expected:
            raise RuntimeError(f"hash mismatch for {name}")
        payloads[name] = payload
    _publish(root, payloads)


def main(
    argv: Sequence[str] | None = None,
    *,
    root: Path = Path("."),
    fetcher: FontFetcher = fetch_https,
) -> int:
    """Fetch pinned font files or verify committed bytes offline."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        invalid = invalid_files(root)
        if invalid:
            print("INVALID: " + ", ".join(path.as_posix() for path in invalid))
            return 1
    else:
        download_files(root, fetcher)
    print("font: Noto Sans KR at pinned Google Fonts commit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
