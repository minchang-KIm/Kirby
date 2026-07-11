# Windsprig: Echoes of the Gale

Windsprig is an original local action-platform game about Sprig, a seed spirit restoring motion to six sky islands. The same deterministic Python/pygame-ce runtime targets Windows and desktop Chromium.

## Requirements

- Python 3.12 or 3.13
- A physical keyboard or standards-compatible gamepad
- A viewport of at least 1024×576 for browser play

## Install and run with uv

```powershell
uv sync --all-extras --locked
uv run python -m windsprig
uv run pytest -q
```

## Standard-venv fallback

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev,web]"
.\.venv\Scripts\python -m windsprig
.\.venv\Scripts\python -m pytest -q
```

The game contains original code and release assets. See `assets/LICENSES.md` for provenance and third-party license notices.

## Campaign

Guide Sprig across six sky islands with five stages each. Draw nearby echoes, capture their resonance, and harmonize with it to use an echo ability. Each stage also holds Wind Motes that reward careful exploration.

## Controls

- World map: use `Left`/`Right` or `A`/`D` to select a stage, `Enter` to begin, and `Esc` to exit.
- Stage: use `Esc` to return to the world map and `R` to restart.
- Player 1: `A`/`D` move, `W` jump or hover, hold and release `S` to draw, `F` uses an echo ability, `G` guards, `H` dodges, and `T` drops the current echo ability.
- Player 2: arrow keys move, jump or hover, and draw; `.` uses an echo ability, `/` guards, `Right Shift` dodges, and `,` drops the current echo ability.
- Players 3 and 4: standards-compatible gamepads.

## Project layout

- `windsprig/core/`: deterministic ECS, event bus, fixed-step timing, and random-number services
- `windsprig/input/`: device-independent commands, bindings, and input collection
- `windsprig/gameplay/`: components, systems, echo abilities, entity factory, and stage runtime
- `windsprig/content/`: campaign and echo-ability data
- `windsprig/meta/`: world-map progression, saves, and completion tracking
- `docs/kr/`: Korean architecture and pattern documentation
- `tests/`: unit and integration tests
