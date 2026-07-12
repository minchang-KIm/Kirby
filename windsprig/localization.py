"""Strict immutable English/Korean localization and formatting."""

from __future__ import annotations

import string
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from windsprig.content.loader import ContentError, load_locales
from windsprig.content.models import LocaleCatalog

type Language = Literal["en", "ko"]
type FormatValue = str | int | float

SUPPORTED_LANGUAGES: Final = frozenset({"en", "ko"})
_ENGLISH_DIAGNOSTIC_FALLBACKS: Final = frozenset({"debug.english_only"})
_FORMATTER = string.Formatter()


def _formatter_fields(source: str, path: str) -> frozenset[str]:
    try:
        parsed = tuple(_FORMATTER.parse(source))
    except ValueError as error:
        raise ContentError(path, f"invalid format string: {error}") from error
    fields: set[str] = set()
    for _, field_name, format_spec, conversion in parsed:
        if field_name is None:
            continue
        if not field_name.isidentifier():
            raise ContentError(path, f"unsafe formatter field: {field_name}")
        if conversion is not None and conversion not in {"s", "r", "a"}:
            raise ContentError(path, f"invalid formatter conversion: {conversion}")
        fields.add(field_name)
        if format_spec:
            raise ContentError(path, f"unsupported formatter specifier: {format_spec}")
    return frozenset(fields)


def load_locale_catalog(content_dir: Path) -> LocaleCatalog:
    """Load canonical strict locale JSON and enforce release parity/formatting."""

    catalog = load_locales(content_dir)
    en = catalog.strings["en"]
    ko = catalog.strings["ko"]
    en_only = sorted(set(en) - set(ko))
    ko_only = sorted(set(ko) - set(en))
    if en_only or ko_only:
        raise ValueError(
            f"locale key sets differ: en-only={','.join(en_only) or '-'}; ko-only={','.join(ko_only) or '-'}"
        )
    for key in sorted(en):
        en_fields = _formatter_fields(en[key], f"locales.en.{key}")
        ko_fields = _formatter_fields(ko[key], f"locales.ko.{key}")
        if en_fields != ko_fields:
            raise ValueError(
                f"locale placeholders differ for {key}: "
                f"en={','.join(sorted(en_fields)) or '-'}; "
                f"ko={','.join(sorted(ko_fields)) or '-'}"
            )
    return catalog


@dataclass(frozen=True, slots=True)
class Localizer:
    """Format one supported locale without retaining caller-owned arguments."""

    catalog: LocaleCatalog
    language: Language

    def __post_init__(self) -> None:
        if self.language not in SUPPORTED_LANGUAGES:
            raise ValueError(f"unsupported locale language: {self.language}")

    @classmethod
    def load(cls, content_dir: Path, language: Language) -> Localizer:
        """Load a validated catalog for ``language``."""

        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(f"unsupported locale language: {language}")
        return cls(load_locale_catalog(content_dir), language)

    def text(self, key: str, **values: FormatValue) -> str:
        """Return one formatted message or a path-rich lookup/format error."""

        for name, value in values.items():
            if type(value) not in {str, int, float}:
                raise TypeError(f"locale format value {name} for key {key} must be str, int, or float")
        source = self.catalog.strings[self.language].get(key)
        if source is None and key in _ENGLISH_DIAGNOSTIC_FALLBACKS:
            source = self.catalog.strings["en"].get(key)
        if source is None:
            raise KeyError(f"missing locale key: {key} (language={self.language})")
        try:
            return source.format_map(values)
        except KeyError as error:
            missing = error.args[0]
            raise KeyError(f"missing locale format value: {missing} for key: {key}") from None
        except (AttributeError, IndexError, ValueError) as error:
            raise ValueError(f"could not format locale key {key}: {error}") from error


__all__ = ["Language", "LocaleCatalog", "Localizer", "load_locale_catalog"]
