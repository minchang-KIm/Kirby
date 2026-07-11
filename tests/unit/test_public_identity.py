from __future__ import annotations

from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[2]
PUBLIC_PATHS = (
    ROOT / "windsprig",
    ROOT / "README.md",
    ROOT / "assets" / "LICENSES.md",
    ROOT / "build.spec",
    ROOT / "docs" / "kr",
)
FORBIDDEN = ("kirby", "kirby_clone", "return to dream land", "kirby-rtd")


def test_public_package_metadata_is_windsprig() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["name"] == "windsprig"
    assert data["project"]["version"] == "1.0.0"
    assert data["project"]["scripts"]["windsprig"] == "windsprig.__main__:main"


def test_active_public_files_contain_no_legacy_identity() -> None:
    hits: list[str] = []
    for path in PUBLIC_PATHS:
        files = path.rglob("*") if path.is_dir() else (path,)
        for file in files:
            if not file.is_file() or file.suffix.lower() not in {".py", ".md", ".toml", ".spec", ".json"}:
                continue
            text = file.read_text(encoding="utf-8").casefold()
            for token in FORBIDDEN:
                if token in text:
                    hits.append(f"{file.relative_to(ROOT)}: {token}")
    assert hits == []
