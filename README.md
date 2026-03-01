# Kirby-Style Pygame Practice Clone

A learning-focused 2D platformer inspired by Kirby feel, implemented with deterministic fixed-step simulation, replay hashing, and test coverage for core gameplay logic.

## Features

- Snappy platformer movement with:
  - coyote time (`100ms`)
  - jump buffering (`120ms`)
  - variable jump height
- Combat loop:
  - player attack startup/active/recovery windows
  - enemy contact damage
  - invulnerability windows and knockback
- One complete level with:
  - hazards
  - checkpoints
  - collectibles
  - regular and tougher enemy variants
  - goal tile win condition
- Deterministic simulation core usable by runtime and tests
- Replay frame hashing support (`tools/replay_runner.py`)
- PyInstaller build spec for Windows packaging

## Stack

- Python 3.12+
- pygame
- pytest + pytest-cov + hypothesis
- pyinstaller

## Setup

This project expects `uv` as the workflow tool.

If `uv` is not on your `PATH` in PowerShell, use `python -m uv` in place of `uv` for the same commands.

1. Install `uv` (Windows PowerShell):
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

2. Create venv and install:
```powershell
python -m uv venv
python -m uv pip install -r requirements-dev.txt
```

3. Run game:
```powershell
python -m uv run python -m kirby_clone
```

4. Run tests with coverage:
```powershell
python -m uv run pytest --cov=kirby_clone --cov-report=term-missing
```

5. Build executable:
```powershell
python -m uv run pyinstaller build.spec
```

## Controls

- `Left/Right` or `A/D`: Move
- `Space`: Jump
- `J`: Attack
- `Esc`: Pause toggle
- `R`: Restart from checkpoint after death

## Project Layout

- `kirby_clone/`: engine + gameplay modules
- `levels/`: JSON level files
- `assets/`: license log and optional external assets
- `tests/`: unit + integration suites
- `tools/replay_runner.py`: deterministic replay checker
- `build.spec`: PyInstaller config

## Legal / Asset Policy

- No proprietary Kirby assets are included.
- Runtime visuals/audio use generated placeholders.
- Third-party assets must be permissively licensed (preferably CC0) and documented in [assets/LICENSES.md](assets/LICENSES.md).
