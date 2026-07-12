# ADR 001: Fixed-point completion percentage

- Status: Accepted
- Date: 2026-07-12
- Applies from: Windsprig 1.0.0

## Context

The first campaign plan described `completion_percent()` as returning
`decimal.Decimal`. The pinned CPython/WebAssembly runtime exposes only a
placeholder `decimal.Decimal` constructor and omits `ROUND_HALF_UP`; importing
the planned implementation prevented the game from starting in a browser.

Completion is a bounded presentation value with one decimal place. It does not
need arbitrary-precision arithmetic at its public boundary, but it must remain
exact and must round the combined 50/30/10/10 weighting only once.

## Decision

`completion_percent()` and `CompletionBreakdown.percent` return the immutable
domain value `CompletionPercent`. Its canonical representation is integer
tenths of one percent in `[0, 1000]`, where `500` renders as `"50.0"` and
`1000` renders as `"100.0"`.

The calculation combines exact integer ratios, clamps the rational result, and
performs one half-up rounding operation. Callers use `.tenths` for numeric
comparisons and `str(value)` for localized presentation. Implicit Decimal or
float arithmetic is deliberately unsupported, so rounding cannot leak into
progression or persistence.

This is an approved pre-release API correction, not a compatibility shim. The
campaign plan is amended to name `CompletionPercent`; tests lock its type,
bounds, formatting, ordering, and exact formula.

## Consequences

- Native and browser builds expose the same value type and semantics.
- The application no longer imports the unavailable browser `decimal` module.
- Consumers written against an unreleased `Decimal` prototype must migrate to
  `.tenths` or `str(value)` before Windsprig 1.0.0.
- Future precision changes require a new ADR and save/presentation audit.
