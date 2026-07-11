# Windsprig Code Conventions

Windsprig is a production game and a code-study project. The source should make contracts and design decisions discoverable without burying readers in commentary.

## Design priorities

1. Preserve deterministic gameplay. Rendering cadence, platform APIs, and presentation effects do not change simulation results.
2. Keep boundaries explicit. Platform services, input routing, persistence, gameplay, presentation, and release tooling depend on narrow public contracts.
3. Make invalid states difficult to construct. Prefer frozen dataclasses, validated configuration, stable IDs, and typed result objects.
4. Keep one source of truth. Do not retain compatibility runtimes, duplicate progression rules, or parallel asset catalogs.

## Naming and structure

- Use domain language from the product: `draw`, `capture`, `harmonize`, `Wind Mote`, `ActiveRoster`, and `StageRuntime`.
- Name booleans as predicates (`is_ready`, `has_focus`, `can_retry`) and collections by their contents (`active_players`, `pending_edges`).
- Keep functions cohesive. Extract a helper when it gives a rule a meaningful name or isolates a side effect; do not split linear code merely to reduce line count.
- Inject clocks, storage, display, audio, browser bridges, and random seeds at boundaries. Gameplay code must not reach into operating-system or JavaScript globals.

## Types and data

- Type every production function and method. Public protocols describe platform and subsystem boundaries.
- Prefer immutable value objects for commands, events, snapshots, configuration, and save models.
- Narrow `object` values at the producer/consumer boundary with validation or a precise cast after the invariant is established. Do not spread `Any` to silence analysis.
- Use stable content IDs in saves, replays, and seeds. Display names may be localized; identifiers may not.

## Docstrings and comments

- Add a concise docstring to public modules, protocols, classes, and non-obvious public functions. State the contract, ownership, timing, side effects, or failure behavior—not a paraphrase of the name.
- Add a short comment when a reader needs the reason for an ordering constraint, compatibility seam, safety check, or deliberately unusual implementation.
- Prefer this:

  ```python
  # Edges survive render frames that produce no fixed simulation step.
  self._pending_edges.extend(edges)
  ```

  Avoid this:

  ```python
  # Add edges to the pending edge list.
  self._pending_edges.extend(edges)
  ```

- Keep comments accurate when behavior changes. Delete obsolete commentary in the same change that invalidates it.
- Use issue links or design-document links only when they add durable context; source code must remain understandable if an external link disappears.

## Errors and observability

- Raise precise exceptions for programmer/configuration errors. Convert expected runtime failures into typed results or visible notices at the boundary that can recover.
- Never hide save, content, build, or release-integrity failures. Audio unavailability may degrade to muted play because the product explicitly supports it.
- Diagnostic messages include a stable operation or error code and enough local context to act, without secrets or personal data.
- Persistence assumes one active session. Save fingerprints are best-effort guards, not an atomic cross-tab compare-and-swap; after `recovery_required`, reload and adopt authoritative data before retrying.

## Tests

- Use red-green-refactor for behavior changes. Record a failing regression before fixing a defect.
- Test public behavior and invariants rather than private implementation shape.
- Name tests as executable specifications, including the triggering condition and expected outcome.
- Deterministic tests lock seeds, hashes, event ordering, and stable IDs. Browser and Windows smoke tests exercise the packaged artifacts, not only source imports.
- A coverage percentage never substitutes for a missing release-critical flow.

## Review checklist

- Does the change preserve deterministic and platform boundaries?
- Are public contracts typed and documented at the right level?
- Do comments explain reasons rather than syntax?
- Are names drawn from the product domain and free of legacy identity?
- Is there a focused regression for each changed behavior or fixed bug?
- Do Ruff, mypy, focused tests, and the appropriate end-to-end gate pass without suppressing real errors?
