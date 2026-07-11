# Windsprig Release Foundation and Browser Feasibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the original `windsprig` package, deterministic async runtime boundary, native/web platform services, joined-player input and robust v2 saves, then prove the same pygame-ce runtime can boot, accept input, initialize audio, complete a stage, and reload a save in desktop Chromium.

**Architecture:** Move the tested ECS into one public `windsprig` package and keep deterministic fixed steps below an async frame coordinator. All operating-system and browser behavior is injected through narrow platform protocols; input edges are buffered separately from held state, the active roster is the only source of player entities, and the save service owns validation, migration, backup, quarantine, and recovery. A pinned Pygbag probe exercises these production boundaries in Chromium before presentation work begins.

**Tech Stack:** Python 3.12–3.13, pygame-ce 2.5.7, standard-library dataclasses/JSON validation, Pygbag 0.9.3, uv lockfile, pytest/pytest-asyncio/pytest-cov, Ruff, mypy, Playwright 1.61.0 Chromium, GitHub Actions.

## Global Constraints

- One original, production-quality game shipped as a playable browser build and a Windows desktop build from the same Python/pygame-ce codebase.
- This is a full-product program, not a vertical-slice reduction.
- The six-world, five-stage campaign remains the v1.0 scope.
- Content may be regenerated or replaced where the current data repeats layouts, but no world or stage is removed merely to make the release easier.
- The public game, package, executable, window title, repository display name, documentation, screenshots, and website must not use Nintendo, Kirby, Return to Dream Land, or any Nintendo character, logo, visual asset, audio, level, or copy.
- The website is responsive, but v1.0 gameplay requires a physical keyboard or standards-compatible gamepad and a viewport at least 1024×576.
- Online multiplayer, accounts, cloud saves, monetization, and touch controls are not v1.0 features.
- Render to a 1280×720 logical canvas and scale with letterboxing to common desktop aspect ratios and DPI settings.
- English is the source locale; Korean remains fully supported.
- The public Python package becomes `windsprig`.
- Legacy modules are migrated into the production package or deleted after their tested behavior is absorbed; the shipped executable must not contain two competing game runtimes.
- `GameApp.run()` becomes an async application loop that yields once per rendered frame.
- Desktop uses `asyncio.run`, while the Pygbag entry point invokes the same loop without calling `sys.exit` or `pygame.quit` after browser startup.
- Fixed simulation steps remain deterministic and are separated from rendering cadence.
- Discrete input events are queued until at least one fixed step consumes them, preventing button presses from disappearing on zero-step render frames.
- Continuous input is sampled per render frame and copied into subsequent fixed steps as held state only.
- Native saves use `%LOCALAPPDATA%/Windsprig/save_data.json` by default, with temp-file write, flush, atomic replace, and one known-good backup.
- Browser saves use local browser storage through the Pygbag JavaScript bridge, encode the same schema, and expose storage failure to the UI.
- No code path writes relative to the launch directory in a release build.
- Replace process-randomized `hash(stage_id)` with a stable digest-derived integer seed.
- Save read/write failure never crashes the render loop; it preserves the in-memory session, displays a retryable notice, and avoids reporting success.
- If fixed-step catch-up exceeds a bounded budget, the application drops excess accumulated render time, records a performance diagnostic, and avoids a spiral of death.
- Production modules target at least 85% branch coverage overall.
- Simulation remains stable at a 16 ms fixed step.
- Target: 60 rendered FPS at 1280×720 on a typical modern Windows laptop and desktop Chromium; minimum sustained gameplay floor is 30 FPS on the documented baseline.
- Browser time from cached loader start to interactive title is at most 5 seconds on the test connection; cold start is at most 12 seconds with visible progress and no blank canvas.
- Compressed browser transfer target is at most 30 MB for v1.0.
- Use pygame-ce for both targets and pin a verified Pygbag toolchain version.
- The first camera-ready public release is `v1.0.0`.
- All artifacts embed the same semantic version and commit SHA.
- TypeScript/Phaser is allowed only if the feasibility gate produces evidence that pygame-ce/Pygbag cannot meet the release criteria; the feature and campaign scope must remain unchanged.

---

## Foundation Boundary and File Map

The foundation owns these interfaces. Later gameplay, campaign/presentation, and distribution plans consume them without creating alternate app, input, storage, or platform layers.

- Move `kirby_clone/` to `windsprig/`; move `windsprig/settings.py` to `windsprig/config.py`; move `windsprig/gameplay/systems/inhale_system.py` to `windsprig/gameplay/systems/draw_system.py`. Do not retain a `kirby_clone` compatibility package.
- `windsprig/config.py`: `GameConfig`, release metadata, fixed-step/catch-up limits, and logical resolution.
- `windsprig/core/rng.py`: `derive_stage_seed(base_seed: int, stage_id: str) -> int` plus existing `DeterministicRng`.
- `windsprig/core/time.py`: `FixedStepClock.push(elapsed_ms: float, max_steps: int) -> StepBatch`.
- `windsprig/platform/services.py`: storage, audio, display, time, lifecycle, browser, capabilities, and aggregate service protocols.
- `windsprig/platform/native.py`: `%LOCALAPPDATA%` storage and pygame native implementations; `create_native_services(config: GameConfig) -> PlatformServices`.
- `windsprig/platform/web.py`: Pygbag bridge, local-storage/audio/fullscreen implementations; `create_web_services(config: GameConfig) -> PlatformServices`.
- `windsprig/input/roster.py`: `DeviceRef`, `ActivePlayer`, and `ActiveRoster`.
- `windsprig/input/commands.py`: device-agnostic gameplay/menu commands and `InputFrame`.
- `windsprig/input/router.py`: `RoutedInput` and roster-aware `InputRouter`.
- `windsprig/input/queue.py`: `InputQueue` with one-shot edges and latest held values.
- `windsprig/meta/save_models.py`: immutable, validated save v2 models.
- `windsprig/meta/save_migrations.py`: deterministic prototype-v1-to-v2 conversion.
- `windsprig/meta/save_manager.py`: `SaveService`, result/notice types, backup, quarantine, and recovery.
- `windsprig/screens/base.py`: `ScreenId`, `ScreenTransition`, and the fixed-update/render screen protocol.
- `windsprig/app.py`: the only async frame coordinator.
- `windsprig/__main__.py` and `web/main.py`: native and Pygbag entry points for the same `GameApp`.
- `tools/build_web.py`: deterministic Pygbag build and size report.
- `tools/evaluate_web_feasibility.py`: binary pass/fallback-required evaluator.
- `.github/workflows/ci.yml`: identity, lint/type, coverage, and Chromium feasibility jobs.

The production gameplay constructor after this plan is:

```python
StageRuntime(
    config: GameConfig,
    stage: StageSpec,
    ability_registry: AbilityRegistry,
    active_players: Sequence[ActivePlayer],
    seed: int,
)
```

`StageRuntime` must spawn only `active_players`. `World.step(dt_ms: int, input_frame: object) -> FrameSnapshot`, `GameEvent(topic: str, payload: dict[str, object])`, and `EventBus.subscribe/publish/drain/peek` retain their current contracts.

## Feasibility Decision Before Downstream Work

Pygbag passes only when the pinned build satisfies every assertion below in desktop Chromium twice: once from an empty browser profile and once after reload. A missing signal, an uncaught console error, or an exceeded hard budget is a failure, not a partial pass.

| Required evidence | Pass threshold |
|---|---|
| Boot | `windsprig:probe:boot=ready`; cold interactive time ≤12,000 ms; cached interactive time ≤5,000 ms; no blank canvas |
| Input | Enter joins P1 and a later key edge is consumed by a fixed step exactly once |
| Audio | After a canvas pointer gesture, mixer initialization reports `ready`; unavailable audio reports visible `muted`, never a crash |
| Save | The v2 JSON is written to browser local storage and the same profile/mote data is restored after reload |
| Stage completion | A real `StageRuntime` and `StageGoalSystem` publish completion, then `SaveService.save` succeeds |
| Runtime health | No uncaught page/console errors; measured gameplay floor ≥30 FPS at 1280×720 |
| Artifact | Gzip-compressed transfer sum ≤30 MiB |

If an assertion fails because a repository defect is reproduced by a unit/integration test, fix that defect in the owning task and rerun the complete gate. If the same required assertion still fails in the isolated production-boundary probe on Pygbag 0.9.3/pygame-ce 2.5.7, record `fallback_required`; do not waive the assertion, announce a reduced release, or mark this subproject complete. The fallback keeps the six worlds, 30 stages, 90 stable motes, six bosses, all supported actions, local four-player play, browser release, Windows release, accessibility, localization, performance budgets, and release evidence. It replaces only the implementation route with TypeScript/Phaser plus a Windows desktop wrapper and requires new detailed plans for all remaining subprojects before feature work resumes.

### Task 1: Establish the Public Package, Reproducible Metadata, and Original Documentation

**Files:**
- Create: `tests/unit/test_public_identity.py`
- Move: `kirby_clone/` -> `windsprig/`
- Move: `windsprig/settings.py` -> `windsprig/config.py`
- Move: `windsprig/gameplay/systems/inhale_system.py` -> `windsprig/gameplay/systems/draw_system.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `README.md`
- Modify: `assets/LICENSES.md`
- Modify: `build.spec`
- Modify: `tools/replay_runner.py`
- Modify imports in: `tests/unit/test_combat.py`, `tests/unit/test_determinism.py`, `tests/unit/test_enemy.py`, `tests/unit/test_input_commands_new.py`, `tests/unit/test_meta_progression_new.py`, `tests/unit/test_physics.py`, `tests/unit/test_player.py`, `tests/unit/test_state_machine_new.py`, `tests/integration/test_game_flow.py`, `tests/integration/test_inhale_copy_new.py`, `tests/integration/test_replay_runner.py`, `tests/integration/test_stage_runtime_new.py`
- Modify terminology in: `docs/kr/README.md`, `docs/kr/diagrams.md`, `docs/kr/patterns/command.md`, `docs/kr/patterns/state.md`
- Delete: `requirements.txt`
- Delete: `requirements-dev.txt`

**Interfaces:**
- Produces: installable distribution `windsprig==1.0.0`, console command `windsprig`, module command `python -m windsprig`, extras `.[dev]` and `.[web]`.
- Produces: active package/import prefix `windsprig`; public title `Windsprig: Echoes of the Gale`.
- Consumes: existing tested source and content without retaining a second importable runtime.

- [ ] **Step 1: Record the pre-change baseline without editing it**

Run:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m pytest -q
```

Expected: the existing 25-test baseline passes. If discovery reports a different collected count, record the exact count in the task notes and require zero failures before continuing.

- [ ] **Step 2: Add the failing public-identity test**

```python
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
```

- [ ] **Step 3: Run the focused test and verify the red state**

Run: `.\.venv\Scripts\python -m pytest tests/unit/test_public_identity.py -v`

Expected: FAIL because `pyproject.toml` still names `kirby-rtd-study-clone` and the `windsprig` package does not exist.

- [ ] **Step 4: Move the package and mechanically rename the public action vocabulary**

Run exactly from the repository root:

```powershell
git mv kirby_clone windsprig
git mv windsprig/settings.py windsprig/config.py
git mv windsprig/gameplay/systems/inhale_system.py windsprig/gameplay/systems/draw_system.py

$files = @(rg -l 'kirby_clone|InhaleStartCommand|InhaleReleaseCommand|InhaleSystem|InhaleState|inhale_system|inhale_pressed|inhale_released|FloatCommand' windsprig tests tools docs/kr)
$map = [ordered]@{
  'kirby_clone' = 'windsprig'
  'InhaleStartCommand' = 'DrawStartCommand'
  'InhaleReleaseCommand' = 'DrawReleaseCommand'
  'InhaleSystem' = 'DrawSystem'
  'InhaleState' = 'DrawState'
  'inhale_system' = 'draw_system'
  'inhale_pressed' = 'draw_pressed'
  'inhale_released' = 'draw_released'
  'FloatCommand' = 'HoverCommand'
}
foreach ($file in $files) {
  $text = [IO.File]::ReadAllText((Resolve-Path $file))
  foreach ($pair in $map.GetEnumerator()) { $text = $text.Replace($pair.Key, $pair.Value) }
  [IO.File]::WriteAllText((Resolve-Path $file), $text, [Text.UTF8Encoding]::new($false))
}
```

Then rename the remaining identifiers explicitly in `windsprig/input/bindings.py`, `windsprig/input/devices.py`, `windsprig/gameplay/components/core.py`, and `windsprig/gameplay/systems/draw_system.py`: `inhale` -> `draw`, `swallowed_tag` -> `captured_echo`, `_on_inhale_release` -> `_on_draw_release`, and local `inhale` variables -> `draw_state`. Rename `tests/integration/test_inhale_copy_new.py` to `tests/integration/test_draw_harmonize_new.py` with `git mv` and rename its test to `test_draw_harmonize_grants_echo_ability`.

- [ ] **Step 5: Replace `pyproject.toml` with the single dependency source**

```toml
[build-system]
requires = ["setuptools>=80,<81"]
build-backend = "setuptools.build_meta"

[project]
name = "windsprig"
version = "1.0.0"
description = "Windsprig: Echoes of the Gale"
readme = "README.md"
license = { file = "LICENSE" }
requires-python = ">=3.12,<3.14"
dependencies = [
  "pygame-ce==2.5.7",
]

[project.optional-dependencies]
dev = [
  "hypothesis>=6.146,<7",
  "mypy>=1.17,<2",
  "pyinstaller>=6.17,<7",
  "pytest>=8.4,<9",
  "pytest-asyncio>=1.1,<2",
  "pytest-cov>=6.3,<7",
  "ruff>=0.12,<1",
]
web = [
  "playwright==1.61.0",
  "pygbag==0.9.3",
]

[project.scripts]
windsprig = "windsprig.__main__:main"

[tool.setuptools.package-data]
windsprig = ["content/*.json"]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
addopts = "-q"
asyncio_mode = "auto"

[tool.coverage.run]
branch = true
source = ["windsprig"]
omit = ["windsprig/__main__.py"]

[tool.ruff]
line-length = 120
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.mypy]
python_version = "3.12"
strict = true
packages = ["windsprig.platform", "windsprig.input", "windsprig.meta"]
```

Run:

```powershell
Remove-Item requirements.txt, requirements-dev.txt
uv lock --python 3.12
uv sync --all-extras --locked
```

Expected: `uv.lock` names the root package `windsprig` at `1.0.0`, resolves `pygame-ce==2.5.7` and `pygbag==0.9.3`, and `uv sync` exits 0 without reading either deleted requirements file.

- [ ] **Step 6: Rewrite the public launch documentation and package metadata**

Use this exact README opening and command section; retain useful control/campaign documentation only after translating it to the approved wind-and-echo vocabulary:

```markdown
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
```

Set `windsprig/__init__.py` to `"""Windsprig: Echoes of the Gale."""`, set the pygame caption to `Windsprig: Echoes of the Gale`, update every import to `windsprig`, and change `build.spec` analysis/collection names to `windsprig` and `Windsprig`. Rewrite `assets/LICENSES.md` as an original-asset provenance ledger with columns `Asset`, `Source`, `License`, and `Use`; it may contain no fan-asset instructions. Rewrite the four listed Korean docs to use Windsprig, draw/capture, harmonize, echo ability, and Wind Mote terminology.

- [ ] **Step 7: Verify identity, imports, lock consistency, and the baseline**

Run:

```powershell
uv run pytest tests/unit/test_public_identity.py -v
uv run python -c "import windsprig; from windsprig.config import GameConfig; print(GameConfig().resolution)"
uv lock --check
uv run pytest -q
rg -n -i "kirby|kirby_clone|return to dream land|kirby-rtd" windsprig README.md assets build.spec docs/kr
```

Expected: tests PASS; import prints `(1280, 720)`; lock check exits 0; the full baseline passes; `rg` exits 1 with no matches.

- [ ] **Step 8: Commit the public identity boundary**

```powershell
git add -A
git commit -m "refactor: establish Windsprig package identity"
```

Expected: one commit containing the package move, metadata/lock, documentation, import changes, and identity test; no generated build directory is staged.

### Task 2: Validate Configuration and Derive Stable Stage Seeds

**Files:**
- Modify: `windsprig/config.py`
- Modify: `windsprig/core/rng.py`
- Modify: `windsprig/app.py`
- Modify: `windsprig/gameplay/runtime.py`
- Create: `tests/unit/test_config_and_seed.py`
- Modify: `tests/integration/test_stage_runtime_new.py`

**Interfaces:**
- Produces: `GameConfig(resolution=(1280, 720), target_fps=60, fixed_dt_ms=16, max_catch_up_steps=5, max_frame_elapsed_ms=250, replay_seed=1337, max_local_players=4)`.
- Produces: `derive_stage_seed(base_seed: int, stage_id: str) -> int` using BLAKE2s with an 8-byte digest.
- Consumes: stage IDs as stable content identifiers; never Python's process-randomized `hash()`.

- [ ] **Step 1: Add failing stable-seed and config tests**

```python
from __future__ import annotations

import os
import subprocess
import sys

from windsprig.config import GameConfig
from windsprig.core.rng import derive_stage_seed


def test_release_runtime_defaults_are_bounded() -> None:
    config = GameConfig()
    assert config.resolution == (1280, 720)
    assert config.fixed_dt_ms == 16
    assert config.max_catch_up_steps == 5
    assert config.max_frame_elapsed_ms == 250
    assert config.fixed_dt_seconds == 0.016


def test_stage_seed_has_a_locked_digest_value() -> None:
    assert derive_stage_seed(1337, "world_1_stage_1") == 17674047013880078487
    assert derive_stage_seed(1337, "world_1_stage_2") == 16524485793878410478


def test_stage_seed_is_independent_of_python_hash_seed() -> None:
    code = (
        "from windsprig.core.rng import derive_stage_seed; "
        "print(derive_stage_seed(77, 'foundation_probe'))"
    )
    values: list[str] = []
    for hash_seed in ("1", "999"):
        env = os.environ.copy()
        env["PYTHONHASHSEED"] = hash_seed
        values.append(subprocess.check_output([sys.executable, "-c", code], env=env, text=True).strip())
    assert values == ["17908035134853811437", "17908035134853811437"]
```

- [ ] **Step 2: Run the tests and verify the red state**

Run: `uv run pytest tests/unit/test_config_and_seed.py -v`

Expected: FAIL because `GameConfig` lacks the catch-up limits and `derive_stage_seed` is undefined.

- [ ] **Step 3: Implement the validated configuration and digest seed**

Replace `windsprig/config.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class GameConfig:
    resolution: tuple[int, int] = (1280, 720)
    fullscreen: bool = False
    target_fps: int = 60
    fixed_dt_ms: int = 16
    max_catch_up_steps: int = 5
    max_frame_elapsed_ms: int = 250
    gravity: float = 2500.0
    move_speed: float = 260.0
    jump_velocity: float = 760.0
    coyote_time_ms: int = 100
    jump_buffer_ms: int = 120
    player_max_hp: int = 10
    invulnerable_ms: int = 900
    tile_size: int = 32
    replay_seed: int = 1337
    level_path: Path = Path("levels/level_01.json")
    content_dir: Path = Path(__file__).resolve().parent / "content"
    max_local_players: int = 4
    release_version: str = "1.0.0"
    commit_sha: str = "development"

    def __post_init__(self) -> None:
        if self.resolution != (1280, 720):
            raise ValueError("The logical resolution must remain 1280x720.")
        if self.fixed_dt_ms != 16:
            raise ValueError("The deterministic simulation step must remain 16 ms.")
        if self.max_catch_up_steps < 1:
            raise ValueError("max_catch_up_steps must be positive.")

    @property
    def fixed_dt_seconds(self) -> float:
        return self.fixed_dt_ms / 1000.0
```

Add to `windsprig/core/rng.py`:

```python
def derive_stage_seed(base_seed: int, stage_id: str) -> int:
    if not stage_id.strip():
        raise ValueError("stage_id must not be blank")
    payload = f"windsprig:v1:{base_seed}:{stage_id}".encode("utf-8")
    digest = hashlib.blake2s(payload, digest_size=8).digest()
    return int.from_bytes(digest, byteorder="big", signed=False)
```

In `GameApp._start_selected_stage`, replace the existing seed expression with:

```python
seed=derive_stage_seed(self.config.replay_seed, node.stage_id),
```

- [ ] **Step 4: Lock seed behavior at the runtime boundary**

In `tests/integration/test_stage_runtime_new.py`, construct two runtimes with `derive_stage_seed(config.replay_seed, stage.stage_id)`, step both for 20 identical empty frames, and retain the equality assertion on `world_hash()`. Add `assert runtime_a.world.rng.seed == 17674047013880078487`.

- [ ] **Step 5: Run deterministic and full tests**

Run:

```powershell
uv run pytest tests/unit/test_config_and_seed.py tests/integration/test_stage_runtime_new.py -v
uv run pytest -q
rg -n "hash\(.*stage_id|hash\(node\.stage_id" windsprig
```

Expected: focused and full suites PASS; `rg` exits 1 with no process-randomized stage seed.

- [ ] **Step 6: Commit the deterministic configuration**

```powershell
git add windsprig/config.py windsprig/core/rng.py windsprig/app.py windsprig/gameplay/runtime.py tests/unit/test_config_and_seed.py tests/integration/test_stage_runtime_new.py
git commit -m "fix: derive stable stage seeds"
```

### Task 3: Define Platform Protocols and Implement Native Services

**Files:**
- Create: `windsprig/platform/__init__.py`
- Create: `windsprig/platform/services.py`
- Create: `windsprig/platform/native.py`
- Create: `tests/unit/platform/test_native_services.py`

**Interfaces:**
- Produces: `StorageService.read_text/write_text/delete/keys` and `StorageCapabilities(persistent, atomic_write, backup)`.
- Produces: async `AudioService.initialize(after_user_gesture=False) -> AudioStatus`, `play_cue`, `pause`, `resume`, `set_bus_volume`.
- Produces: `DisplayService.create_window/present/set_fullscreen`, `TimeService.tick/monotonic_ms/yield_frame`, `LifecycleService.consume`.
- Produces: `PlatformServices` and `create_native_services(config: GameConfig) -> PlatformServices`.

- [ ] **Step 1: Add failing native storage and service-factory tests**

```python
from __future__ import annotations

import asyncio
from pathlib import Path

from windsprig.config import GameConfig
from windsprig.platform.native import NativeStorage, create_native_services


def test_native_storage_writes_under_local_app_data_atomically(tmp_path: Path) -> None:
    storage = NativeStorage(tmp_path / "Windsprig")
    storage.write_text("save_data.json", '{"save_version": 2}')
    assert storage.read_text("save_data.json") == '{"save_version": 2}'
    assert (tmp_path / "Windsprig" / "save_data.json").is_file()
    assert not list((tmp_path / "Windsprig").glob("*.tmp"))
    assert storage.keys("save") == ("save_data.json",)


def test_native_storage_rejects_escape_from_root(tmp_path: Path) -> None:
    storage = NativeStorage(tmp_path / "Windsprig")
    try:
        storage.write_text("../outside.json", "bad")
    except ValueError as error:
        assert "storage root" in str(error)
    else:
        raise AssertionError("path traversal was accepted")


def test_native_factory_uses_local_app_data(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    services = create_native_services(GameConfig())
    assert services.capabilities.is_web is False
    assert services.storage.capabilities.atomic_write is True
    assert services.storage.root == tmp_path / "Windsprig"
    asyncio.run(services.time.yield_frame())
```

- [ ] **Step 2: Run the tests and verify the red state**

Run: `uv run pytest tests/unit/platform/test_native_services.py -v`

Expected: collection FAILS with `ModuleNotFoundError: No module named 'windsprig.platform'`.

- [ ] **Step 3: Define the narrow service contracts**

Create `windsprig/platform/services.py` with these exact public types and signatures:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, Sequence

import pygame

AudioBus = Literal["music", "sfx"]
LifecycleKind = Literal["quit", "focus_lost", "focus_gained"]


@dataclass(frozen=True, slots=True)
class StorageCapabilities:
    persistent: bool
    atomic_write: bool
    backup: bool


@dataclass(frozen=True, slots=True)
class AudioStatus:
    ready: bool
    muted: bool
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class DisplayCapabilities:
    fullscreen: bool


@dataclass(frozen=True, slots=True)
class PlatformCapabilities:
    is_web: bool
    persistent_storage: bool
    fullscreen: bool
    gamepads: bool
    audio_requires_gesture: bool


@dataclass(frozen=True, slots=True)
class LifecycleEvent:
    kind: LifecycleKind


class StorageService(Protocol):
    @property
    def capabilities(self) -> StorageCapabilities:
        raise NotImplementedError

    def read_text(self, key: str) -> str | None:
        raise NotImplementedError

    def write_text(self, key: str, value: str) -> None:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError

    def keys(self, prefix: str) -> tuple[str, ...]:
        raise NotImplementedError


class AudioService(Protocol):
    @property
    def status(self) -> AudioStatus:
        raise NotImplementedError

    async def initialize(self, after_user_gesture: bool = False) -> AudioStatus:
        raise NotImplementedError

    def play_cue(self, cue_id: str, bus: AudioBus = "sfx") -> bool:
        raise NotImplementedError

    def pause(self) -> None:
        raise NotImplementedError

    def resume(self) -> None:
        raise NotImplementedError

    def set_bus_volume(self, bus: AudioBus, value: float) -> None:
        raise NotImplementedError


class DisplayService(Protocol):
    @property
    def capabilities(self) -> DisplayCapabilities:
        raise NotImplementedError

    def create_window(self, logical_size: tuple[int, int], fullscreen: bool) -> pygame.Surface:
        raise NotImplementedError

    def present(self, canvas: pygame.Surface) -> None:
        raise NotImplementedError

    def set_fullscreen(self, enabled: bool) -> bool:
        raise NotImplementedError


class TimeService(Protocol):
    def tick(self, target_fps: int) -> float:
        raise NotImplementedError

    def monotonic_ms(self) -> float:
        raise NotImplementedError

    async def yield_frame(self) -> None:
        raise NotImplementedError


class LifecycleService(Protocol):
    def consume(self, events: Sequence[pygame.event.Event]) -> tuple[LifecycleEvent, ...]:
        raise NotImplementedError


class BrowserBridge(Protocol):
    def local_storage_get(self, key: str) -> str | None:
        raise NotImplementedError

    def local_storage_set(self, key: str, value: str) -> None:
        raise NotImplementedError

    def local_storage_remove(self, key: str) -> None:
        raise NotImplementedError

    def local_storage_keys(self, prefix: str) -> tuple[str, ...]:
        raise NotImplementedError

    def query_param(self, name: str) -> str | None:
        raise NotImplementedError

    def request_fullscreen(self) -> bool:
        raise NotImplementedError

    def document_hidden(self) -> bool:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class PlatformServices:
    storage: StorageService
    audio: AudioService
    display: DisplayService
    time: TimeService
    lifecycle: LifecycleService
    browser: BrowserBridge | None
    capabilities: PlatformCapabilities
```

- [ ] **Step 4: Implement native atomic storage**

Create `NativeStorage` in `windsprig/platform/native.py`:

```python
class NativeStorage:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._capabilities = StorageCapabilities(persistent=True, atomic_write=True, backup=True)

    @property
    def capabilities(self) -> StorageCapabilities:
        return self._capabilities

    def _path(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        root = self.root.resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError("storage key escapes storage root")
        return candidate

    def read_text(self, key: str) -> str | None:
        path = self._path(key)
        return path.read_text(encoding="utf-8") if path.is_file() else None

    def write_text(self, key: str, value: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as stream:
                stream.write(value)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def keys(self, prefix: str) -> tuple[str, ...]:
        return tuple(
            sorted(
                path.relative_to(self.root).as_posix()
                for path in self.root.rglob("*")
                if path.is_file() and path.relative_to(self.root).as_posix().startswith(prefix)
            )
        )
```

Implement `PygameAudioService`, `PygameDisplayService`, `PygameTimeService`, and `PygameLifecycleService` in the same file. Audio initialization catches `pygame.error` and returns `AudioStatus(ready=False, muted=True, error_code="audio_init_failed")`; `play_cue` returns `False` for an unknown cue or muted service. Display creates a resizable/fullscreen window, retains a 1280×720 canvas, and letterboxes it with `pygame.transform.smoothscale`. Lifecycle maps `QUIT`, `WINDOWFOCUSLOST`, and `WINDOWFOCUSGAINED` to the exact `LifecycleEvent` values above. Time uses `pygame.time.Clock.tick`, `pygame.time.get_ticks`, and `await asyncio.sleep(0)`.

The factory must be exactly:

```python
def create_native_services(config: GameConfig) -> PlatformServices:
    local_app_data = os.environ.get("LOCALAPPDATA")
    root = Path(local_app_data) / "Windsprig" if local_app_data else Path.home() / "AppData" / "Local" / "Windsprig"
    return PlatformServices(
        storage=NativeStorage(root),
        audio=PygameAudioService(requires_gesture=False),
        display=PygameDisplayService(config.resolution),
        time=PygameTimeService(),
        lifecycle=PygameLifecycleService(),
        browser=None,
        capabilities=PlatformCapabilities(
            is_web=False,
            persistent_storage=True,
            fullscreen=True,
            gamepads=True,
            audio_requires_gesture=False,
        ),
    )
```

- [ ] **Step 5: Export the native boundary and run tests headlessly**

`windsprig/platform/__init__.py` must export every dataclass/protocol from `services.py` plus `create_native_services`.

Run:

```powershell
$env:SDL_VIDEODRIVER='dummy'
$env:SDL_AUDIODRIVER='dummy'
uv run pytest tests/unit/platform/test_native_services.py -v
uv run mypy windsprig/platform
uv run ruff check windsprig/platform tests/unit/platform
```

Expected: tests PASS, mypy reports `Success: no issues found`, and Ruff exits 0.

- [ ] **Step 6: Commit native platform isolation**

```powershell
git add windsprig/platform tests/unit/platform/test_native_services.py
git commit -m "feat: add native platform services"
```

### Task 4: Implement Browser Services Through a Narrow Pygbag Bridge

**Files:**
- Create: `windsprig/platform/web.py`
- Create: `tests/unit/platform/test_web_services.py`
- Modify: `windsprig/platform/__init__.py`

**Interfaces:**
- Produces: `PygbagBrowserBridge(window: object)`, `WebStorage`, and `create_web_services(config: GameConfig) -> PlatformServices`.
- Produces: the same `StorageService`, `AudioService`, `DisplayService`, `TimeService`, and `LifecycleService` behavior as native without importing JavaScript APIs outside this adapter.
- Consumes: `platform.window` only when `create_web_services` executes under Pygbag; CPython unit-test import remains safe.

- [ ] **Step 1: Add failing bridge, storage, gesture, and capability tests**

```python
from __future__ import annotations

from dataclasses import dataclass, field

from windsprig.config import GameConfig
from windsprig.platform.web import PygbagBrowserBridge, WebStorage, create_web_services


@dataclass
class FakeLocalStorage:
    values: dict[str, str] = field(default_factory=dict)

    @property
    def length(self) -> int:
        return len(self.values)

    def getItem(self, key: str) -> str | None:
        return self.values.get(key)

    def setItem(self, key: str, value: str) -> None:
        self.values[key] = value

    def removeItem(self, key: str) -> None:
        self.values.pop(key, None)

    def key(self, index: int) -> str:
        return sorted(self.values)[index]


class FakeElement:
    def requestFullscreen(self) -> None:
        return None


class FakeDocument:
    hidden = False
    documentElement = FakeElement()


class FakeLocation:
    search = "?foundation_probe=1"


class FakeNavigator:
    def getGamepads(self) -> list[object]:
        return []


class FakeWindow:
    def __init__(self) -> None:
        self.localStorage = FakeLocalStorage()
        self.document = FakeDocument()
        self.location = FakeLocation()
        self.navigator = FakeNavigator()


def test_web_storage_roundtrips_same_text_schema() -> None:
    bridge = PygbagBrowserBridge(FakeWindow())
    storage = WebStorage(bridge)
    storage.write_text("save_data.json", '{"save_version":2}')
    assert storage.read_text("save_data.json") == '{"save_version":2}'
    assert storage.keys("save") == ("save_data.json",)
    storage.delete("save_data.json")
    assert storage.read_text("save_data.json") is None


def test_bridge_reports_browser_features_and_query() -> None:
    bridge = PygbagBrowserBridge(FakeWindow())
    assert bridge.query_param("foundation_probe") == "1"
    assert bridge.document_hidden() is False
    assert bridge.request_fullscreen() is True


def test_web_factory_marks_audio_as_gesture_gated() -> None:
    services = create_web_services(GameConfig(), window=FakeWindow())
    assert services.capabilities.is_web is True
    assert services.capabilities.audio_requires_gesture is True
    assert services.storage.capabilities.atomic_write is False
```

- [ ] **Step 2: Run the focused tests and verify the red state**

Run: `uv run pytest tests/unit/platform/test_web_services.py -v`

Expected: collection FAILS because `windsprig.platform.web` does not exist.

- [ ] **Step 3: Implement the browser bridge and local-storage adapter**

Create these exact implementations in `windsprig/platform/web.py`:

```python
class PygbagBrowserBridge:
    def __init__(self, window: object) -> None:
        self.window = window

    def local_storage_get(self, key: str) -> str | None:
        value = self.window.localStorage.getItem(key)
        return None if value is None else str(value)

    def local_storage_set(self, key: str, value: str) -> None:
        self.window.localStorage.setItem(key, value)

    def local_storage_remove(self, key: str) -> None:
        self.window.localStorage.removeItem(key)

    def local_storage_keys(self, prefix: str) -> tuple[str, ...]:
        storage = self.window.localStorage
        values = (str(storage.key(index)) for index in range(int(storage.length)))
        return tuple(sorted(key for key in values if key.startswith(prefix)))

    def query_param(self, name: str) -> str | None:
        from urllib.parse import parse_qs

        query = parse_qs(str(self.window.location.search).removeprefix("?"))
        values = query.get(name)
        return values[0] if values else None

    def request_fullscreen(self) -> bool:
        request = getattr(self.window.document.documentElement, "requestFullscreen", None)
        if request is None:
            return False
        request()
        return True

    def document_hidden(self) -> bool:
        return bool(self.window.document.hidden)


class WebStorage:
    def __init__(self, bridge: BrowserBridge) -> None:
        self.bridge = bridge
        self._capabilities = StorageCapabilities(persistent=True, atomic_write=False, backup=True)

    @property
    def capabilities(self) -> StorageCapabilities:
        return self._capabilities

    def read_text(self, key: str) -> str | None:
        return self.bridge.local_storage_get(f"windsprig:{key}")

    def write_text(self, key: str, value: str) -> None:
        self.bridge.local_storage_set(f"windsprig:{key}", value)

    def delete(self, key: str) -> None:
        self.bridge.local_storage_remove(f"windsprig:{key}")

    def keys(self, prefix: str) -> tuple[str, ...]:
        namespace = "windsprig:"
        return tuple(key.removeprefix(namespace) for key in self.bridge.local_storage_keys(namespace + prefix))
```

- [ ] **Step 4: Implement web audio/display/time/lifecycle services**

Use pygame for display and timing, but make web audio refuse pre-gesture initialization explicitly:

```python
class WebAudioService(PygameAudioService):
    def __init__(self) -> None:
        super().__init__(requires_gesture=True)

    async def initialize(self, after_user_gesture: bool = False) -> AudioStatus:
        if not after_user_gesture:
            self._status = AudioStatus(ready=False, muted=True, error_code="gesture_required")
            return self._status
        return await super().initialize(after_user_gesture=True)


def create_web_services(config: GameConfig, window: object | None = None) -> PlatformServices:
    if window is None:
        import platform

        window = getattr(platform, "window")
    bridge = PygbagBrowserBridge(window)
    fullscreen = hasattr(window.document.documentElement, "requestFullscreen")
    gamepads = hasattr(window.navigator, "getGamepads")
    return PlatformServices(
        storage=WebStorage(bridge),
        audio=WebAudioService(),
        display=WebDisplayService(config.resolution, bridge),
        time=PygameTimeService(),
        lifecycle=PygameLifecycleService(),
        browser=bridge,
        capabilities=PlatformCapabilities(
            is_web=True,
            persistent_storage=True,
            fullscreen=fullscreen,
            gamepads=gamepads,
            audio_requires_gesture=True,
        ),
    )
```

`WebDisplayService.set_fullscreen(True)` calls `bridge.request_fullscreen`; `set_fullscreen(False)` returns `False` until the browser exposes a matching exit call. `WebDisplayService.present` uses the same letterboxing implementation as native. On focus loss, the app later pauses audio and clears held input; do not call JavaScript directly from the app.

- [ ] **Step 5: Verify CPython safety and matching protocol behavior**

Run:

```powershell
$env:SDL_VIDEODRIVER='dummy'
$env:SDL_AUDIODRIVER='dummy'
uv run pytest tests/unit/platform -v
uv run python -c "import windsprig.platform.web; print('web adapter import safe')"
uv run mypy windsprig/platform
uv run ruff check windsprig/platform tests/unit/platform
```

Expected: all platform tests PASS; CPython prints `web adapter import safe`; mypy and Ruff exit 0.

- [ ] **Step 6: Commit browser service isolation**

```powershell
git add windsprig/platform tests/unit/platform/test_web_services.py
git commit -m "feat: add Pygbag platform services"
```

### Task 5: Add the Active Roster, Menu-Aware Router, and Fixed-Step Input Queue

**Files:**
- Create: `windsprig/input/roster.py`
- Create: `windsprig/input/router.py`
- Create: `windsprig/input/queue.py`
- Modify: `windsprig/input/commands.py`
- Modify: `windsprig/input/bindings.py`
- Modify: `windsprig/input/devices.py`
- Modify: `windsprig/input/__init__.py`
- Modify: `windsprig/gameplay/runtime.py`
- Create: `tests/unit/input/test_roster.py`
- Create: `tests/unit/input/test_input_queue.py`
- Create: `tests/unit/input/test_router.py`
- Modify: `tests/integration/test_stage_runtime_new.py`

**Interfaces:**
- Produces: `DeviceRef(kind: Literal["keyboard", "gamepad"], uid: str, label: str)` and `ActivePlayer(slot, device, color_token, icon_token, is_leader)`.
- Produces: `ActiveRoster.players`, `leader_slot`, `join`, `leave`, `reassign`, `player_for_device`, and `is_active`.
- Produces commands: `MoveCommand`, `JumpCommand`, `HoverCommand`, `DrawStartCommand`, `DrawReleaseCommand`, `AbilityUseCommand`, `GuardCommand`, `DodgeCommand`, `DropAbilityCommand`, `NavigateCommand`, `ConfirmCommand`, `CancelCommand`, `PauseCommand`.
- Produces: `RoutedInput(frame, join_requests, disconnected_devices)` and `InputQueue.push/consume_step/clear_held`.
- Consumes: `StageRuntime(config: GameConfig, stage: StageSpec, ability_registry: AbilityRegistry, active_players: Sequence[ActivePlayer], seed: int)`; only joined slots spawn.

- [ ] **Step 1: Add failing roster behavior tests**

```python
from windsprig.input.roster import ActiveRoster, DeviceRef


def keyboard(uid: str) -> DeviceRef:
    return DeviceRef(kind="keyboard", uid=uid, label=uid)


def test_join_uses_lowest_slot_and_first_player_is_leader() -> None:
    roster = ActiveRoster(max_players=4)
    first = roster.join(keyboard("wasd"))
    second = roster.join(keyboard("arrows"))
    assert (first.slot, first.is_leader) == (1, True)
    assert (second.slot, second.is_leader) == (2, False)
    assert roster.leader_slot == 1
    assert roster.join(keyboard("wasd")) == first


def test_leaving_leader_promotes_lowest_remaining_slot() -> None:
    roster = ActiveRoster(max_players=4)
    roster.join(keyboard("wasd"))
    second = roster.join(keyboard("arrows"))
    removed = roster.leave(1)
    assert removed is not None and removed.slot == 1
    assert roster.leader_slot == second.slot
    assert roster.players[0].is_leader is True


def test_reassign_keeps_slot_identity() -> None:
    roster = ActiveRoster(max_players=4)
    player = roster.join(keyboard("wasd"))
    pad = DeviceRef(kind="gamepad", uid="pad-7", label="Standard Gamepad")
    reassigned = roster.reassign(player.slot, pad)
    assert reassigned.slot == 1
    assert reassigned.color_token == "mint"
    assert roster.player_for_device(pad) == reassigned
```

- [ ] **Step 2: Add the zero-step-frame regression test before implementation**

```python
from windsprig.input.commands import GuardCommand, InputFrame, JumpCommand, MoveCommand
from windsprig.input.queue import InputQueue


def test_edge_survives_zero_step_frames_and_is_consumed_once() -> None:
    queue = InputQueue()
    queue.push(
        InputFrame(
            commands_by_slot={
                1: [MoveCommand(player_slot=1, axis=1), JumpCommand(player_slot=1, pressed=True)]
            }
        )
    )
    queue.push(InputFrame(commands_by_slot={1: [MoveCommand(player_slot=1, axis=1)]}))

    first_step = queue.consume_step().commands_for(1)
    second_step = queue.consume_step().commands_for(1)

    assert sum(isinstance(command, JumpCommand) for command in first_step) == 1
    assert not any(isinstance(command, JumpCommand) for command in second_step)
    assert any(isinstance(command, MoveCommand) and command.axis == 1 for command in first_step)
    assert any(isinstance(command, MoveCommand) and command.axis == 1 for command in second_step)


def test_focus_loss_clears_held_state_and_pending_edges() -> None:
    queue = InputQueue()
    queue.push(InputFrame(commands_by_slot={1: [GuardCommand(player_slot=1, held=True)]}))
    queue.clear_held()
    assert queue.consume_step().commands_for(1) == []
```

- [ ] **Step 3: Run the new tests and verify the red state**

Run: `uv run pytest tests/unit/input -v`

Expected: collection FAILS because roster, queue, and router modules are absent.

- [ ] **Step 4: Implement the roster with persistent slot visuals**

Create `windsprig/input/roster.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

DeviceKind = Literal["keyboard", "gamepad"]
SLOT_VISUALS = {
    1: ("mint", "leaf"),
    2: ("gold", "sun"),
    3: ("violet", "moon"),
    4: ("cyan", "gale"),
}


@dataclass(frozen=True, slots=True)
class DeviceRef:
    kind: DeviceKind
    uid: str
    label: str


@dataclass(frozen=True, slots=True)
class ActivePlayer:
    slot: int
    device: DeviceRef
    color_token: str
    icon_token: str
    is_leader: bool


class ActiveRoster:
    def __init__(self, max_players: int = 4) -> None:
        if not 1 <= max_players <= 4:
            raise ValueError("max_players must be between 1 and 4")
        self.max_players = max_players
        self._players: dict[int, ActivePlayer] = {}

    @property
    def players(self) -> tuple[ActivePlayer, ...]:
        return tuple(self._players[slot] for slot in sorted(self._players))

    @property
    def leader_slot(self) -> int | None:
        return next((player.slot for player in self.players if player.is_leader), None)

    def join(self, device: DeviceRef) -> ActivePlayer:
        current = self.player_for_device(device)
        if current is not None:
            return current
        free = next((slot for slot in range(1, self.max_players + 1) if slot not in self._players), None)
        if free is None:
            raise ValueError("active roster is full")
        color, icon = SLOT_VISUALS[free]
        player = ActivePlayer(free, device, color, icon, is_leader=not self._players)
        self._players[free] = player
        return player

    def leave(self, slot: int) -> ActivePlayer | None:
        removed = self._players.pop(slot, None)
        if removed is not None and removed.is_leader and self._players:
            promoted = min(self._players)
            self._players[promoted] = replace(self._players[promoted], is_leader=True)
        return removed

    def reassign(self, slot: int, device: DeviceRef) -> ActivePlayer:
        if self.player_for_device(device) is not None:
            raise ValueError("device is already assigned")
        player = self._players[slot]
        self._players[slot] = replace(player, device=device)
        return self._players[slot]

    def player_for_device(self, device: DeviceRef) -> ActivePlayer | None:
        return next(
            (
                player
                for player in self.players
                if player.device.kind == device.kind and player.device.uid == device.uid
            ),
            None,
        )

    def is_active(self, slot: int) -> bool:
        return slot in self._players
```

- [ ] **Step 5: Implement typed commands and the edge/held queue**

Keep `InputFrame.add`, `commands_for`, `continuous_only`, and `empty`. Define all commands as frozen dataclasses. Treat only `MoveCommand`, `HoverCommand`, and `GuardCommand` as held commands. Implement `windsprig/input/queue.py`:

```python
from __future__ import annotations

from windsprig.input.commands import GuardCommand, HoverCommand, InputCommand, InputFrame, MoveCommand

HELD_TYPES = (MoveCommand, HoverCommand, GuardCommand)


class InputQueue:
    def __init__(self) -> None:
        self._edges: dict[int, list[InputCommand]] = {}
        self._held: dict[int, dict[type[InputCommand], InputCommand]] = {}

    def push(self, frame: InputFrame) -> None:
        for slot, commands in frame.commands_by_slot.items():
            for command in commands:
                if isinstance(command, HELD_TYPES):
                    self._held.setdefault(slot, {})[type(command)] = command
                else:
                    self._edges.setdefault(slot, []).append(command)

    def consume_step(self) -> InputFrame:
        output = InputFrame.empty()
        for slot in sorted(set(self._held) | set(self._edges)):
            held = [self._held[slot][kind] for kind in HELD_TYPES if kind in self._held.get(slot, {})]
            output.commands_by_slot[slot] = held + self._edges.get(slot, [])
        self._edges = {}
        return output

    def clear_held(self) -> None:
        self._held = {}
        self._edges = {}
```

- [ ] **Step 6: Implement roster-aware routing and disconnect reporting**

`InputRouter.collect(events, keys, roster) -> RoutedInput` must use two stable keyboard refs (`keyboard-wasd`, `keyboard-arrows`) and joystick instance IDs (`gamepad-{instance_id}`). Enter/Start from an unassigned device yields a `join_requests` item and no gameplay command that frame. Assigned devices map directional menu edges to `NavigateCommand`, primary action to `ConfirmCommand`, escape/B to `CancelCommand`, and Start to `PauseCommand`. `JOYDEVICEREMOVED` yields the matching `DeviceRef` in `disconnected_devices`. Continuous commands are generated only for devices present in `roster.players`.

Lock the return type in `windsprig/input/router.py`:

```python
@dataclass(frozen=True, slots=True)
class RoutedInput:
    frame: InputFrame
    join_requests: tuple[DeviceRef, ...] = ()
    disconnected_devices: tuple[DeviceRef, ...] = ()
```

Add a router test that sends `pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN)`, asserts a WASD join request while the roster is empty, joins it, sends `K_w`, and asserts slot 1 receives `JumpCommand` plus `ConfirmCommand` only on the key-down edge.

- [ ] **Step 7: Make the production runtime spawn only active players**

Change the constructor to the locked signature and replace `for slot in range(1, 5)` with:

```python
self.player_entities: list[int] = []
for player in active_players:
    spawn_index = min(player.slot - 1, len(stage.player_spawns) - 1)
    x, y = stage.player_spawns[spawn_index]
    self.player_entities.append(self.factory.spawn_player(player.slot, x, y))
```

Update every runtime construction in tests/app to pass `active_players=(ActiveRoster().join(DeviceRef("keyboard", "keyboard-wasd", "Keyboard WASD")),)`. Add an integration assertion that a one-player roster produces exactly one `PlayerSlot`, and a roster with slots 1 and 2 produces exactly two. No inactive entity may contribute HUD, camera, goal, or lives.

- [ ] **Step 8: Run input, roster, and runtime tests**

Run:

```powershell
$env:SDL_VIDEODRIVER='dummy'
uv run pytest tests/unit/input tests/integration/test_stage_runtime_new.py -v
uv run mypy windsprig/input windsprig/gameplay/runtime.py
uv run ruff check windsprig/input tests/unit/input
uv run pytest -q
```

Expected: all focused and full tests PASS; mypy and Ruff exit 0.

- [ ] **Step 9: Commit joined-player input**

```powershell
git add windsprig/input windsprig/gameplay/runtime.py windsprig/app.py tests/unit/input tests/integration
git commit -m "feat: buffer input for active players"
```

### Task 6: Define Save Schema v2 and Deterministic Prototype Migration

**Files:**
- Create: `windsprig/meta/save_models.py`
- Create: `windsprig/meta/save_migrations.py`
- Modify: `windsprig/meta/completion.py`
- Modify: `windsprig/meta/__init__.py`
- Create: `tests/unit/meta/test_save_models.py`
- Create: `tests/unit/meta/test_save_migrations.py`

**Interfaces:**
- Produces: validated `SaveProfile`, `DisplaySettings`, `AudioSettings`, `AccessibilitySettings`, `ControlSettings`, `GlobalSettings`, and `SaveData`.
- Produces: `SaveData(save_version=2, campaign_version="1.0", profiles=<exactly three>, settings, prototype_imported)`.
- Produces: `SaveMigrationCatalog(mote_ids_by_stage, next_node_by_node)` and `migrate_v1(payload, catalog) -> SaveData`.
- Produces: `CompletionTracker(cleared_nodes, collected_mote_ids, challenge_rewards, best_times_ms, clear_counts)` matching the v2 profile vocabulary.
- Consumes: stable mote IDs from the campaign; prototype integer counts are clamped to available IDs and never become repeatable currency.

- [ ] **Step 1: Add failing v2 validation tests**

```python
from windsprig.meta.save_models import AudioSettings, SaveData, save_data_from_dict


def test_default_save_has_exactly_three_safe_profiles() -> None:
    data = SaveData()
    assert data.save_version == 2
    assert data.campaign_version == "1.0"
    assert tuple(profile.profile_id for profile in data.profiles) == ("profile_1", "profile_2", "profile_3")
    assert all(profile.unlocked_worlds == frozenset({"world_1"}) for profile in data.profiles)
    assert all(profile.unlocked_nodes == frozenset({"world_1_node_1"}) for profile in data.profiles)


def test_audio_ranges_are_validated() -> None:
    try:
        AudioSettings(master_volume=1.1)
    except ValueError:
        return
    raise AssertionError("volume above one was accepted")


def test_save_rejects_unknown_fields() -> None:
    try:
        save_data_from_dict({"save_version": 2, "unknown": True})
    except ValueError:
        return
    raise AssertionError("unknown save field was accepted")
```

- [ ] **Step 2: Add the failing prototype migration test**

```python
from windsprig.meta.save_migrations import SaveMigrationCatalog, migrate_v1


def test_v1_counts_map_to_stable_motes_and_are_clamped() -> None:
    payload = {
        "save_version": 1,
        "profiles": [
            {
                "profile_name": "Breeze",
                "unlocked_worlds": ["world_1"],
                "cleared_nodes": ["world_1_node_1"],
                "energy_spheres": {"world_1_stage_1": 99, "world_1_stage_2": -4},
                "best_times": {"world_1_stage_1": 9321},
                "challenge_unlocks": ["swift_clear"],
            }
        ],
    }
    catalog = SaveMigrationCatalog(
        mote_ids_by_stage={
            "world_1_stage_1": ("world_1_stage_1:mote:1", "world_1_stage_1:mote:2", "world_1_stage_1:mote:3"),
            "world_1_stage_2": ("world_1_stage_2:mote:1", "world_1_stage_2:mote:2", "world_1_stage_2:mote:3"),
        },
        next_node_by_node={"world_1_node_1": "world_1_node_2"},
    )
    data = migrate_v1(payload, catalog)
    profile = data.profiles[0]
    assert profile.collected_mote_ids == frozenset(
        {"world_1_stage_1:mote:1", "world_1_stage_1:mote:2", "world_1_stage_1:mote:3"}
    )
    assert profile.unlocked_nodes == frozenset({"world_1_node_1", "world_1_node_2"})
    assert profile.best_times_ms == {"world_1_stage_1": 9321}
    assert data.prototype_imported is True
```

- [ ] **Step 3: Run the tests and verify the red state**

Run: `uv run pytest tests/unit/meta/test_save_models.py tests/unit/meta/test_save_migrations.py -v`

Expected: collection FAILS because the v2 model and migration modules do not exist.

- [ ] **Step 4: Implement the complete v2 model**

Create `windsprig/meta/save_models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
import json
from types import MappingProxyType
from typing import Literal, Mapping, cast


def _volume(name: str, value: float) -> float:
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"{name} must be between zero and one")
    return number


def _object(payload: object, allowed: set[str], name: str) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError(f"{name} must be an object")
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError(f"unknown {name} fields: {sorted(unknown)}")
    return {str(key): value for key, value in payload.items()}


def _int_map(payload: object, name: str) -> Mapping[str, int]:
    raw = _object(payload, set(payload) if isinstance(payload, dict) else set(), name)
    values = {key: int(value) for key, value in raw.items()}
    if any(value < 0 for value in values.values()):
        raise ValueError(f"{name} values must be non-negative")
    return MappingProxyType(dict(sorted(values.items())))


@dataclass(frozen=True, slots=True)
class DisplaySettings:
    fullscreen: bool = False
    integer_scaling: bool = False


@dataclass(frozen=True, slots=True)
class AudioSettings:
    master_volume: float = 1.0
    music_volume: float = 0.8
    sfx_volume: float = 0.9
    muted: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "master_volume", _volume("master_volume", self.master_volume))
        object.__setattr__(self, "music_volume", _volume("music_volume", self.music_volume))
        object.__setattr__(self, "sfx_volume", _volume("sfx_volume", self.sfx_volume))


@dataclass(frozen=True, slots=True)
class AccessibilitySettings:
    screen_shake: bool = True
    reduced_motion: bool = False
    draw_toggle: bool = False
    guard_toggle: bool = False


@dataclass(frozen=True, slots=True)
class ControlSettings:
    keyboard_p1_preset: str = "wasd"
    keyboard_p2_preset: str = "arrows"
    gamepad_mapping: str = "standard"


@dataclass(frozen=True, slots=True)
class GlobalSettings:
    display: DisplaySettings = field(default_factory=DisplaySettings)
    audio: AudioSettings = field(default_factory=AudioSettings)
    accessibility: AccessibilitySettings = field(default_factory=AccessibilitySettings)
    language: Literal["en", "ko"] = "en"
    controls: ControlSettings = field(default_factory=ControlSettings)

    def __post_init__(self) -> None:
        if self.language not in {"en", "ko"}:
            raise ValueError("language must be en or ko")


@dataclass(frozen=True, slots=True)
class SaveProfile:
    profile_id: str
    display_name: str
    unlocked_nodes: frozenset[str] = frozenset({"world_1_node_1"})
    unlocked_worlds: frozenset[str] = frozenset({"world_1"})
    collected_mote_ids: frozenset[str] = frozenset()
    best_times_ms: Mapping[str, int] = field(default_factory=dict)
    clear_counts: Mapping[str, int] = field(default_factory=dict)
    discovered_abilities: frozenset[str] = frozenset()
    challenge_rewards: frozenset[str] = frozenset()
    play_time_ms: int = 0
    last_played_stage: str | None = None

    def __post_init__(self) -> None:
        if not 1 <= len(self.display_name) <= 16:
            raise ValueError("display_name must contain 1 to 16 characters")
        if self.play_time_ms < 0:
            raise ValueError("play_time_ms must be non-negative")
        object.__setattr__(self, "unlocked_nodes", frozenset(self.unlocked_nodes))
        object.__setattr__(self, "unlocked_worlds", frozenset(self.unlocked_worlds))
        object.__setattr__(self, "collected_mote_ids", frozenset(self.collected_mote_ids))
        object.__setattr__(self, "discovered_abilities", frozenset(self.discovered_abilities))
        object.__setattr__(self, "challenge_rewards", frozenset(self.challenge_rewards))
        object.__setattr__(self, "best_times_ms", _int_map(dict(self.best_times_ms), "best_times_ms"))
        object.__setattr__(self, "clear_counts", _int_map(dict(self.clear_counts), "clear_counts"))


def default_profiles() -> tuple[SaveProfile, SaveProfile, SaveProfile]:
    return (
        SaveProfile(profile_id="profile_1", display_name="Sprig 1"),
        SaveProfile(profile_id="profile_2", display_name="Sprig 2"),
        SaveProfile(profile_id="profile_3", display_name="Sprig 3"),
    )


@dataclass(frozen=True, slots=True)
class SaveData:
    save_version: int = 2
    campaign_version: str = "1.0"
    profiles: tuple[SaveProfile, SaveProfile, SaveProfile] = field(default_factory=default_profiles)
    settings: GlobalSettings = field(default_factory=GlobalSettings)
    prototype_imported: bool = False

    def __post_init__(self) -> None:
        if self.save_version != 2:
            raise ValueError("save_version must be 2")
        ids = tuple(profile.profile_id for profile in self.profiles)
        if ids != ("profile_1", "profile_2", "profile_3"):
            raise ValueError("profiles must use profile_1, profile_2, profile_3 in slot order")


def save_data_to_dict(data: SaveData) -> dict[str, object]:
    return {
        "save_version": data.save_version,
        "campaign_version": data.campaign_version,
        "prototype_imported": data.prototype_imported,
        "settings": {
            "display": {"fullscreen": data.settings.display.fullscreen, "integer_scaling": data.settings.display.integer_scaling},
            "audio": {
                "master_volume": data.settings.audio.master_volume,
                "music_volume": data.settings.audio.music_volume,
                "sfx_volume": data.settings.audio.sfx_volume,
                "muted": data.settings.audio.muted,
            },
            "accessibility": {
                "screen_shake": data.settings.accessibility.screen_shake,
                "reduced_motion": data.settings.accessibility.reduced_motion,
                "draw_toggle": data.settings.accessibility.draw_toggle,
                "guard_toggle": data.settings.accessibility.guard_toggle,
            },
            "language": data.settings.language,
            "controls": {
                "keyboard_p1_preset": data.settings.controls.keyboard_p1_preset,
                "keyboard_p2_preset": data.settings.controls.keyboard_p2_preset,
                "gamepad_mapping": data.settings.controls.gamepad_mapping,
            },
        },
        "profiles": [
            {
                "profile_id": profile.profile_id,
                "display_name": profile.display_name,
                "unlocked_nodes": sorted(profile.unlocked_nodes),
                "unlocked_worlds": sorted(profile.unlocked_worlds),
                "collected_mote_ids": sorted(profile.collected_mote_ids),
                "best_times_ms": dict(profile.best_times_ms),
                "clear_counts": dict(profile.clear_counts),
                "discovered_abilities": sorted(profile.discovered_abilities),
                "challenge_rewards": sorted(profile.challenge_rewards),
                "play_time_ms": profile.play_time_ms,
                "last_played_stage": profile.last_played_stage,
            }
            for profile in data.profiles
        ],
    }


def _settings_from_dict(payload: object) -> GlobalSettings:
    raw = _object(payload, {"display", "audio", "accessibility", "language", "controls"}, "settings")
    display = _object(raw.get("display", {}), {"fullscreen", "integer_scaling"}, "display settings")
    audio = _object(raw.get("audio", {}), {"master_volume", "music_volume", "sfx_volume", "muted"}, "audio settings")
    access = _object(raw.get("accessibility", {}), {"screen_shake", "reduced_motion", "draw_toggle", "guard_toggle"}, "accessibility settings")
    controls = _object(raw.get("controls", {}), {"keyboard_p1_preset", "keyboard_p2_preset", "gamepad_mapping"}, "control settings")
    language = str(raw.get("language", "en"))
    if language not in {"en", "ko"}:
        raise ValueError("language must be en or ko")
    return GlobalSettings(
        display=DisplaySettings(bool(display.get("fullscreen", False)), bool(display.get("integer_scaling", False))),
        audio=AudioSettings(float(audio.get("master_volume", 1.0)), float(audio.get("music_volume", 0.8)), float(audio.get("sfx_volume", 0.9)), bool(audio.get("muted", False))),
        accessibility=AccessibilitySettings(bool(access.get("screen_shake", True)), bool(access.get("reduced_motion", False)), bool(access.get("draw_toggle", False)), bool(access.get("guard_toggle", False))),
        language=cast(Literal["en", "ko"], language),
        controls=ControlSettings(str(controls.get("keyboard_p1_preset", "wasd")), str(controls.get("keyboard_p2_preset", "arrows")), str(controls.get("gamepad_mapping", "standard"))),
    )


def _profile_from_dict(payload: object) -> SaveProfile:
    allowed = {
        "profile_id", "display_name", "unlocked_nodes", "unlocked_worlds", "collected_mote_ids",
        "best_times_ms", "clear_counts", "discovered_abilities", "challenge_rewards", "play_time_ms",
        "last_played_stage",
    }
    raw = _object(payload, allowed, "profile")
    return SaveProfile(
        profile_id=str(raw["profile_id"]),
        display_name=str(raw["display_name"]),
        unlocked_nodes=frozenset(str(value) for value in raw.get("unlocked_nodes", ["world_1_node_1"])),
        unlocked_worlds=frozenset(str(value) for value in raw.get("unlocked_worlds", ["world_1"])),
        collected_mote_ids=frozenset(str(value) for value in raw.get("collected_mote_ids", [])),
        best_times_ms=_int_map(raw.get("best_times_ms", {}), "best_times_ms"),
        clear_counts=_int_map(raw.get("clear_counts", {}), "clear_counts"),
        discovered_abilities=frozenset(str(value) for value in raw.get("discovered_abilities", [])),
        challenge_rewards=frozenset(str(value) for value in raw.get("challenge_rewards", [])),
        play_time_ms=int(raw.get("play_time_ms", 0)),
        last_played_stage=None if raw.get("last_played_stage") is None else str(raw["last_played_stage"]),
    )


def save_data_from_dict(payload: object) -> SaveData:
    raw = _object(payload, {"save_version", "campaign_version", "profiles", "settings", "prototype_imported"}, "save")
    profiles_raw = raw.get("profiles")
    if not isinstance(profiles_raw, list) or len(profiles_raw) != 3:
        raise ValueError("save must contain exactly three profiles")
    profiles = tuple(_profile_from_dict(value) for value in profiles_raw)
    return SaveData(
        save_version=int(raw.get("save_version", 0)),
        campaign_version=str(raw.get("campaign_version", "")),
        profiles=(profiles[0], profiles[1], profiles[2]),
        settings=_settings_from_dict(raw.get("settings", {})),
        prototype_imported=bool(raw.get("prototype_imported", False)),
    )


def save_data_to_json(data: SaveData, *, indent: int | None = None) -> str:
    return json.dumps(save_data_to_dict(data), ensure_ascii=False, indent=indent, sort_keys=True)


def save_data_from_json(raw: str) -> SaveData:
    return save_data_from_dict(json.loads(raw))
```

- [ ] **Step 5: Implement deterministic v1 migration**

Create `windsprig/meta/save_migrations.py` with a frozen `SaveMigrationCatalog` and this migration core:

```python
@dataclass(frozen=True, slots=True)
class SaveMigrationCatalog:
    mote_ids_by_stage: Mapping[str, tuple[str, ...]]
    next_node_by_node: Mapping[str, str]


def migrate_v1(payload: Mapping[str, object], catalog: SaveMigrationCatalog) -> SaveData:
    raw_profiles = list(payload.get("profiles", []))
    migrated: list[SaveProfile] = []
    for index in range(3):
        raw = dict(raw_profiles[index]) if index < len(raw_profiles) else {}
        cleared = {str(value) for value in raw.get("cleared_nodes", [])}
        unlocked_nodes = set(cleared)
        if not cleared:
            unlocked_nodes.add("world_1_node_1")
        for node_id in cleared:
            next_node = catalog.next_node_by_node.get(node_id)
            if next_node is not None:
                unlocked_nodes.add(next_node)

        collected: set[str] = set()
        sphere_counts = dict(raw.get("energy_spheres", {}))
        for stage_id, value in sphere_counts.items():
            available = catalog.mote_ids_by_stage.get(str(stage_id), ())
            count = max(0, min(int(value), len(available)))
            collected.update(available[:count])

        migrated.append(
            SaveProfile(
                profile_id=f"profile_{index + 1}",
                display_name=str(raw.get("profile_name", f"Sprig {index + 1}"))[:16] or f"Sprig {index + 1}",
                unlocked_nodes=frozenset(unlocked_nodes),
                unlocked_worlds=frozenset(str(value) for value in raw.get("unlocked_worlds", ["world_1"])),
                collected_mote_ids=frozenset(collected),
                best_times_ms={str(key): max(0, int(value)) for key, value in dict(raw.get("best_times", {})).items()},
                challenge_rewards=frozenset(str(value) for value in raw.get("challenge_unlocks", [])),
            )
        )
    return SaveData(profiles=(migrated[0], migrated[1], migrated[2]), prototype_imported=True)
```

Build `SaveMigrationCatalog` from the campaign by enumerating each stage's three current collectible positions in content order as `{stage_id}:mote:1`, `{stage_id}:mote:2`, `{stage_id}:mote:3`, and by mapping each nonfinal node to its next node. These IDs become frozen compatibility IDs when explicit mote objects are added later.

Rename `CompletionTracker.energy_spheres` to `collected_mote_ids`, `challenge_unlocks` to `challenge_rewards`, and `best_times` to `best_times_ms`. `mark_stage_clear(node_id, elapsed_ms)` adds the node, keeps the lower non-negative best time, and increments `clear_counts[node_id]`. `collect_mote(mote_id)` adds one stable ID to its set and is idempotent.

- [ ] **Step 6: Verify schema, migration, serialization, and types**

Run:

```powershell
uv run pytest tests/unit/meta/test_save_models.py tests/unit/meta/test_save_migrations.py -v
uv run python -c "from windsprig.meta.save_models import SaveData,save_data_from_json,save_data_to_json; raw=save_data_to_json(SaveData()); assert save_data_from_json(raw).save_version == 2; print('save v2 roundtrip')"
uv run mypy windsprig/meta/save_models.py windsprig/meta/save_migrations.py
```

Expected: tests PASS, command prints `save v2 roundtrip`, and mypy reports no issues.

- [ ] **Step 7: Commit the versioned data contract**

```powershell
git add windsprig/meta tests/unit/meta
git commit -m "feat: define save schema v2"
```

### Task 7: Add Cross-Platform Save Backup, Migration, Quarantine, and Recovery Results

**Files:**
- Replace: `windsprig/meta/save_manager.py`
- Modify: `windsprig/meta/__init__.py`
- Modify: `windsprig/app.py`
- Create: `tests/unit/meta/test_save_manager.py`
- Create: `tests/integration/test_save_platform_parity.py`

**Interfaces:**
- Produces: `SaveNotice(code, message_key, recovery_key)`, `SaveLoadResult(data, notice)`, and `SaveWriteResult(ok, error_code)`.
- Produces: `SaveService.load() -> SaveLoadResult` and `SaveService.save(data: SaveData) -> SaveWriteResult`.
- Produces: `SaveManager(storage, migration_catalog, now_utc, key="save_data.json")`.
- Consumes: native atomic files or browser local storage through `StorageService`; app code never opens a save path.

- [ ] **Step 1: Add failing migration, backup, corrupt-primary, and failure-result tests**

```python
from __future__ import annotations

from datetime import datetime, timezone

from windsprig.meta.save_manager import SaveManager
from windsprig.meta.save_migrations import SaveMigrationCatalog
from windsprig.meta.save_models import SaveData, save_data_to_json
from windsprig.platform.services import StorageCapabilities


class MemoryStorage:
    capabilities = StorageCapabilities(persistent=True, atomic_write=True, backup=True)

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.fail_writes = False

    def read_text(self, key: str) -> str | None:
        return self.values.get(key)

    def write_text(self, key: str, value: str) -> None:
        if self.fail_writes:
            raise OSError("storage unavailable")
        self.values[key] = value

    def delete(self, key: str) -> None:
        self.values.pop(key, None)

    def keys(self, prefix: str) -> tuple[str, ...]:
        return tuple(sorted(key for key in self.values if key.startswith(prefix)))


CATALOG = SaveMigrationCatalog(
    mote_ids_by_stage={"world_1_stage_1": ("world_1_stage_1:mote:1",)},
    next_node_by_node={"world_1_node_1": "world_1_node_2"},
)
NOW = lambda: datetime(2026, 7, 11, 10, 30, tzinfo=timezone.utc)


def test_corrupt_primary_is_quarantined_and_backup_is_restored() -> None:
    storage = MemoryStorage()
    storage.values["save_data.json"] = "{broken"
    storage.values["save_data.backup.json"] = save_data_to_json(SaveData())
    result = SaveManager(storage, CATALOG, NOW).load()
    assert result.notice is not None and result.notice.code == "backup_restored"
    assert result.notice.recovery_key == "recovery/save_data.20260711T103000Z.json"
    assert storage.values[result.notice.recovery_key] == "{broken"
    assert result.data.save_version == 2


def test_invalid_primary_and_backup_offer_safe_new_data() -> None:
    storage = MemoryStorage()
    storage.values["save_data.json"] = "[]"
    storage.values["save_data.backup.json"] = "not-json"
    result = SaveManager(storage, CATALOG, NOW).load()
    assert result.notice is not None and result.notice.code == "reset_required"
    assert result.data == SaveData()


def test_write_failure_returns_failure_without_destroying_memory_state() -> None:
    storage = MemoryStorage()
    manager = SaveManager(storage, CATALOG, NOW)
    data = SaveData()
    storage.fail_writes = True
    result = manager.save(data)
    assert result.ok is False
    assert result.error_code == "storage_write_failed"
    assert data.profiles[0].display_name == "Sprig 1"
```

- [ ] **Step 2: Run the tests and verify the red state**

Run: `uv run pytest tests/unit/meta/test_save_manager.py -v`

Expected: collection or assertions FAIL because the current manager accepts a filesystem path, writes directly, and exposes no result/notice contract.

- [ ] **Step 3: Implement explicit save results and recovery algorithm**

Replace `windsprig/meta/save_manager.py` with the following public types and algorithm:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Callable, Literal, Protocol

from windsprig.meta.save_migrations import SaveMigrationCatalog, migrate_v1
from windsprig.meta.save_models import SaveData, save_data_from_dict, save_data_to_json
from windsprig.platform.services import StorageService

NoticeCode = Literal["migrated_v1", "backup_restored", "reset_required", "read_failed"]


@dataclass(frozen=True, slots=True)
class SaveNotice:
    code: NoticeCode
    message_key: str
    recovery_key: str | None = None


@dataclass(frozen=True, slots=True)
class SaveLoadResult:
    data: SaveData
    notice: SaveNotice | None = None


@dataclass(frozen=True, slots=True)
class SaveWriteResult:
    ok: bool
    error_code: str | None = None


class SaveService(Protocol):
    def load(self) -> SaveLoadResult:
        raise NotImplementedError

    def save(self, data: SaveData) -> SaveWriteResult:
        raise NotImplementedError


class SaveManager:
    def __init__(
        self,
        storage: StorageService,
        migration_catalog: SaveMigrationCatalog,
        now_utc: Callable[[], datetime],
        key: str = "save_data.json",
    ) -> None:
        self.storage = storage
        self.migration_catalog = migration_catalog
        self.now_utc = now_utc
        self.key = key
        self.backup_key = key.replace(".json", ".backup.json")

    def _decode(self, raw: str) -> tuple[SaveData, bool]:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("save root must be an object")
        version = int(payload.get("save_version", 1))
        if version == 1:
            return migrate_v1(payload, self.migration_catalog), True
        if version != 2:
            raise ValueError(f"unsupported save version: {version}")
        return save_data_from_dict(payload), False

    def load(self) -> SaveLoadResult:
        try:
            raw = self.storage.read_text(self.key)
        except Exception:
            return SaveLoadResult(SaveData(), SaveNotice("read_failed", "save.read_failed"))
        if raw is None:
            return SaveLoadResult(SaveData())
        try:
            data, migrated = self._decode(raw)
            if migrated:
                return SaveLoadResult(data, SaveNotice("migrated_v1", "save.migrated_v1"))
            return SaveLoadResult(data)
        except Exception:
            stamp = self.now_utc().strftime("%Y%m%dT%H%M%SZ")
            recovery_key = f"recovery/save_data.{stamp}.json"
            try:
                self.storage.write_text(recovery_key, raw)
            except Exception:
                recovery_key = None
            try:
                backup_raw = self.storage.read_text(self.backup_key)
                if backup_raw is not None:
                    data, _ = self._decode(backup_raw)
                    return SaveLoadResult(
                        data,
                        SaveNotice("backup_restored", "save.backup_restored", recovery_key),
                    )
            except Exception:
                pass
            return SaveLoadResult(
                SaveData(),
                SaveNotice("reset_required", "save.reset_required", recovery_key),
            )

    def save(self, data: SaveData) -> SaveWriteResult:
        raw = save_data_to_json(data, indent=2)
        try:
            current = self.storage.read_text(self.key)
        except Exception:
            return SaveWriteResult(ok=False, error_code="storage_write_failed")
        if current is not None:
            try:
                self._decode(current)
            except Exception:
                current = None
            else:
                try:
                    self.storage.write_text(self.backup_key, current)
                except Exception:
                    return SaveWriteResult(ok=False, error_code="storage_write_failed")
        try:
            self.storage.write_text(self.key, raw)
        except Exception:
            return SaveWriteResult(ok=False, error_code="storage_write_failed")
        return SaveWriteResult(ok=True)
```

The `except` blocks are intentional service boundaries: they convert adapter failure into explicit UI state. They must not log raw save contents.

- [ ] **Step 4: Integrate the service without a relative path**

Construct `SaveManager` from `services.storage`, the catalog-derived `SaveMigrationCatalog`, and `lambda: datetime.now(timezone.utc)`. Store the returned `SaveLoadResult.notice` in app state for the recovery/status screen. When the notice code is `migrated_v1`, immediately call `save_service.save(load_result.data)` and expose its result; the migration notice is informational and must not imply the rewritten v2 data persisted. `_flush_save` must update immutable profiles with this concrete pattern, call `save_service.save`, and set `save_status` to `saved` only when `result.ok` is true; on failure preserve the in-memory `SaveData` and set `save_status` to `retry_required`:

```python
from dataclasses import replace

profile = replace(
    self.save_data.profiles[0],
    unlocked_nodes=frozenset(self.unlocked_nodes),
    unlocked_worlds=frozenset(self.unlocked_worlds),
    collected_mote_ids=frozenset(self.tracker.collected_mote_ids),
    best_times_ms=dict(self.tracker.best_times_ms),
    clear_counts=dict(self.tracker.clear_counts),
)
profiles = (profile, self.save_data.profiles[1], self.save_data.profiles[2])
updated = replace(self.save_data, profiles=profiles)
result = self.save_service.save(updated)
self.save_data = updated
self.save_status = "saved" if result.ok else "retry_required"
```

Delete every `Path("save/save_data.json")`, `GameConfig.save_path`, and direct `read_text`/`write_text` save call from production code.

- [ ] **Step 5: Prove native/web schema parity**

In `tests/integration/test_save_platform_parity.py`, use `NativeStorage(tmp_path / "Windsprig")` and `WebStorage(PygbagBrowserBridge(FakeWindow()))`, save the same populated `SaveData` through two managers, load both, and assert `native_result.data == web_result.data`. Also assert neither adapter created `Path.cwd() / "save"`.

Run:

```powershell
uv run pytest tests/unit/meta/test_save_manager.py tests/integration/test_save_platform_parity.py -v
uv run mypy windsprig/meta
uv run pytest -q
rg -n "save/save_data|Path\(.*save_data" windsprig
```

Expected: tests PASS; mypy succeeds; full suite passes; `rg` exits 1 with no relative production save path.

- [ ] **Step 6: Commit robust cross-platform saves**

```powershell
git add windsprig/meta windsprig/app.py windsprig/config.py tests/unit/meta tests/integration/test_save_platform_parity.py
git commit -m "feat: migrate and recover save data"
```

### Task 8: Refactor the Application Into an Async Fixed-Step Coordinator

**Files:**
- Modify: `windsprig/core/time.py`
- Create: `windsprig/screens/__init__.py`
- Create: `windsprig/screens/base.py`
- Create: `windsprig/screens/foundation.py`
- Replace: `windsprig/app.py`
- Replace: `windsprig/__main__.py`
- Modify: `windsprig/game.py`
- Create: `tests/unit/core/test_fixed_step_clock.py`
- Create: `tests/unit/test_async_app.py`

**Interfaces:**
- Produces: `StepBatch(steps: int, alpha: float, dropped_ms: float)` and bounded `FixedStepClock.push`.
- Produces: `ScreenId`, `ScreenTransition`, `Screen`, and `ScreenFactory` in `windsprig/screens/base.py`.
- Produces: `async GameApp.run() -> int` and `async GameApp.run_frame() -> None`; neither exits the process nor quits pygame.
- Consumes: `PlatformServices`, `InputRouter`, `InputQueue`, and `ActiveRoster`; the current screen receives one `InputFrame` per fixed step.

- [ ] **Step 1: Add failing clock-budget tests**

```python
from windsprig.core.time import FixedStepClock


def test_clock_reports_zero_step_and_interpolation() -> None:
    clock = FixedStepClock(step_ms=16)
    batch = clock.push(8, max_steps=5)
    assert batch.steps == 0
    assert batch.alpha == 0.5
    assert batch.dropped_ms == 0


def test_clock_drops_excess_catch_up_time() -> None:
    clock = FixedStepClock(step_ms=16)
    batch = clock.push(200, max_steps=5)
    assert batch.steps == 5
    assert batch.dropped_ms == 112
    assert batch.alpha == 0.5
```

- [ ] **Step 2: Add the lost-edge async-loop regression test**

```python
from __future__ import annotations

from windsprig.app import GameApp
from windsprig.config import GameConfig
from windsprig.input.commands import InputFrame, JumpCommand, MoveCommand


async def test_async_app_keeps_edge_until_first_fixed_step(app_harness) -> None:
    app: GameApp = app_harness.app
    app_harness.time.elapsed = 1
    app_harness.router.next_frame = InputFrame(
        commands_by_slot={1: [MoveCommand(player_slot=1, axis=1), JumpCommand(player_slot=1, pressed=True)]}
    )
    await app.run_frame()
    assert app_harness.screen.frames == []

    app_harness.time.elapsed = 15
    app_harness.router.next_frame = InputFrame(commands_by_slot={1: [MoveCommand(player_slot=1, axis=1)]})
    await app.run_frame()
    commands = app_harness.screen.frames[0].commands_for(1)
    assert sum(isinstance(command, JumpCommand) for command in commands) == 1


async def test_async_app_yields_every_render_frame(app_harness) -> None:
    await app_harness.app.run_frame()
    await app_harness.app.run_frame()
    assert app_harness.time.yield_count == 2
```

`app_harness` is a fixture with fake display/audio/time/lifecycle services, a fake router, and a recording screen; it must not initialize a real window.

- [ ] **Step 3: Run the tests and verify the red state**

Run: `uv run pytest tests/unit/core/test_fixed_step_clock.py tests/unit/test_async_app.py -v`

Expected: FAIL because `FixedStepClock.push` returns an integer and `GameApp.run` is synchronous.

- [ ] **Step 4: Implement bounded fixed-step batches**

Replace `windsprig/core/time.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StepBatch:
    steps: int
    alpha: float
    dropped_ms: float


class FixedStepClock:
    def __init__(self, step_ms: int) -> None:
        if step_ms <= 0:
            raise ValueError("step_ms must be positive")
        self.step_ms = step_ms
        self.accumulator_ms = 0.0

    def push(self, elapsed_ms: float, max_steps: int) -> StepBatch:
        if max_steps <= 0:
            raise ValueError("max_steps must be positive")
        self.accumulator_ms += max(0.0, elapsed_ms)
        available = int(self.accumulator_ms // self.step_ms)
        steps = min(available, max_steps)
        dropped_steps = max(0, available - max_steps)
        dropped_ms = float(dropped_steps * self.step_ms)
        self.accumulator_ms -= dropped_ms
        self.accumulator_ms -= steps * self.step_ms
        return StepBatch(steps=steps, alpha=self.accumulator_ms / self.step_ms, dropped_ms=dropped_ms)
```

- [ ] **Step 5: Lock the screen/transition contract**

Create `windsprig/screens/base.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Mapping, Protocol

import pygame

from windsprig.input.commands import InputFrame

ScreenId = Literal[
    "boot", "title", "profile", "hub", "world_map", "stage_intro", "playing",
    "paused", "results", "defeat", "settings", "controls", "credits", "recovery",
]


@dataclass(frozen=True, slots=True)
class ScreenTransition:
    target: ScreenId
    payload: Mapping[str, object] = field(default_factory=dict)


class Screen(Protocol):
    def on_enter(self, payload: Mapping[str, object]) -> None:
        raise NotImplementedError

    def on_exit(self) -> None:
        raise NotImplementedError

    def fixed_update(self, dt_ms: int, input_frame: InputFrame) -> ScreenTransition | None:
        raise NotImplementedError

    def render(self, canvas: pygame.Surface, alpha: float) -> None:
        raise NotImplementedError


class ScreenFactory(Protocol):
    def create(self, screen_id: ScreenId) -> Screen:
        raise NotImplementedError
```

Move the current world-map/stage state plus `_visible_nodes`, `_start_selected_stage`, `_on_stage_progress`, `_render_world_map`, `_render_stage`, and `_camera_offset` into `windsprig/screens/foundation.py`. Name the concrete adapter `FoundationScreen`; give it the shared `ActiveRoster`, `SaveService`, catalog, registry, and config. It maps `NavigateCommand`, `ConfirmCommand`, `CancelCommand`, and `PauseCommand` rather than raw pygame key constants. When it creates `StageRuntime`, pass `roster.players` and `derive_stage_seed`.

- [ ] **Step 6: Implement the async coordinator**

Use this loop in `windsprig/app.py`; keep construction/injection in `__init__` so the unit test can supply fakes:

```python
async def run(self) -> int:
    self.running = True
    while self.running:
        await self.run_frame()
    return 0

async def run_frame(self) -> None:
    elapsed_ms = min(self.services.time.tick(self.config.target_fps), self.config.max_frame_elapsed_ms)
    events = tuple(self.event_source())
    lifecycle = self.services.lifecycle.consume(events)
    if any(event.kind == "quit" for event in lifecycle):
        self.running = False
    if any(event.kind == "focus_lost" for event in lifecycle):
        self.input_queue.clear_held()
        self.services.audio.pause()
    if any(event.kind == "focus_gained" for event in lifecycle):
        self.services.audio.resume()

    routed = self.input_router.collect(events, self.key_source(), self.roster)
    for device in routed.join_requests:
        if len(self.roster.players) < self.config.max_local_players:
            self.roster.join(device)
    self.disconnected_devices = routed.disconnected_devices
    self.input_queue.push(routed.frame)

    batch = self.fixed_clock.push(elapsed_ms, self.config.max_catch_up_steps)
    if batch.dropped_ms:
        self.performance_diagnostics.append(f"fixed_step_drop:{int(batch.dropped_ms)}")
    for _ in range(batch.steps):
        transition = self.screen.fixed_update(self.config.fixed_dt_ms, self.input_queue.consume_step())
        if transition is not None:
            self.screen.on_exit()
            self.screen = self.screen_factory.create(transition.target)
            self.screen.on_enter(transition.payload)

    self.screen.render(self.canvas, batch.alpha)
    self.services.display.present(self.canvas)
    await self.services.time.yield_frame()
```

Create `self.canvas = pygame.Surface(config.resolution)` once. A pointer-down event calls `await services.audio.initialize(after_user_gesture=True)` when audio is not ready. No method in this file calls `pygame.quit`, `sys.exit`, `Path.write_text`, or JavaScript.

- [ ] **Step 7: Make native startup own initialization and shutdown**

Replace `windsprig/__main__.py` with:

```python
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pygame

from windsprig.app import GameApp
from windsprig.config import GameConfig
from windsprig.platform.native import create_native_services
from windsprig.screens.foundation import create_foundation_screen_factory


async def run_native() -> int:
    pygame.init()
    config = GameConfig()
    services = create_native_services(config)
    factory = create_foundation_screen_factory(config, services, lambda: datetime.now(timezone.utc))
    services.display.create_window(config.resolution, config.fullscreen)
    try:
        return await GameApp(config, services, factory).run()
    finally:
        pygame.quit()


def main() -> int:
    return asyncio.run(run_native())


if __name__ == "__main__":
    raise SystemExit(main())
```

Make `windsprig/game.py::run_game` delegate to `main()` only for legacy callers; no second loop remains.

- [ ] **Step 8: Run async, headless, and regression checks**

Run:

```powershell
$env:SDL_VIDEODRIVER='dummy'
$env:SDL_AUDIODRIVER='dummy'
uv run pytest tests/unit/core/test_fixed_step_clock.py tests/unit/test_async_app.py -v
uv run pytest -q
uv run mypy windsprig/app.py windsprig/screens windsprig/core/time.py
rg -n "def run\(self\).*[^a]|while running|pygame\.quit|sys\.exit" windsprig/app.py
```

Expected: tests PASS; mypy succeeds; `GameApp.run` is reported only as `async def`; the prohibited shutdown calls have no match in `windsprig/app.py`.

- [ ] **Step 9: Commit the shared async runtime loop**

```powershell
git add windsprig/app.py windsprig/__main__.py windsprig/game.py windsprig/core/time.py windsprig/screens tests/unit/core/test_fixed_step_clock.py tests/unit/test_async_app.py
git commit -m "refactor: run Windsprig asynchronously"
```

### Task 9: Build and Exercise the Pygbag Chromium Feasibility Probe

**Files:**
- Create: `.gitignore`
- Create: `web/main.py`
- Create: `web/template.tmpl`
- Create: `web/favicon.png`
- Create: `windsprig/feasibility.py`
- Modify: `windsprig/app.py`
- Modify: `windsprig/screens/foundation.py`
- Modify: `windsprig/input/commands.py`
- Modify: `windsprig/input/router.py`
- Create: `tools/build_web.py`
- Create: `tests/e2e/conftest.py`
- Create: `tests/e2e/test_web_feasibility.py`
- Create: `tests/unit/test_feasibility_probe.py`
- Create at test time, do not commit: `dist/web/`, `artifacts/web-build.json`, `artifacts/browser-probe.json`

**Interfaces:**
- Produces: Pygbag entry `web/main.py` invoking the same async `GameApp` without process exit or pygame shutdown.
- Produces: `FoundationProbe` enabled only by `?foundation_probe=1`, publishing namespaced local-storage evidence.
- Produces: `python tools/build_web.py --probe` -> `dist/web` and `artifacts/web-build.json`.
- Consumes: real `InputRouter`, `ActiveRoster`, browser `AudioService`, `StageRuntime`, `StageGoalSystem`, and `SaveService`.

- [ ] **Step 1: Add a failing probe-state unit test**

```python
from windsprig.feasibility import FoundationProbe


class MemoryStorage:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def read_text(self, key: str) -> str | None:
        return self.values.get(key)

    def write_text(self, key: str, value: str) -> None:
        self.values[key] = value

    def delete(self, key: str) -> None:
        self.values.pop(key, None)

    def keys(self, prefix: str) -> tuple[str, ...]:
        return tuple(key for key in sorted(self.values) if key.startswith(prefix))


def test_probe_publishes_only_when_enabled() -> None:
    storage = MemoryStorage()
    disabled = FoundationProbe(storage, enabled=False)
    disabled.mark("boot", "ready")
    assert storage.values == {}

    enabled = FoundationProbe(storage, enabled=True)
    enabled.mark("boot", "ready")
    assert storage.values["probe/boot"] == "ready"
```

- [ ] **Step 2: Add the browser test before the web entry/build exists**

Create an E2E test that records page errors and error-level console messages, times initial navigation, exercises a user gesture and keyboard input, forces only the goal position through the probe hook, and reloads:

```python
from __future__ import annotations

import json
from pathlib import Path
import time

from playwright.sync_api import Page, expect


def signal(page: Page, name: str) -> str | None:
    return page.evaluate("name => localStorage.getItem('windsprig:probe/' + name)", name)


def test_pygbag_boot_input_audio_stage_and_save(page: Page, web_server: str) -> None:
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)

    started = time.perf_counter()
    page.goto(f"{web_server}/?foundation_probe=1", wait_until="domcontentloaded")
    page.wait_for_function("localStorage.getItem('windsprig:probe/boot') === 'ready'", timeout=12_000)
    cold_ms = int((time.perf_counter() - started) * 1000)
    expect(page.locator("canvas")).to_be_visible()

    page.locator("canvas").click()
    page.wait_for_function("localStorage.getItem('windsprig:probe/audio') === 'ready'", timeout=5_000)
    page.keyboard.press("Enter")
    page.keyboard.press("Enter")
    page.keyboard.press("KeyD")
    page.wait_for_function("localStorage.getItem('windsprig:probe/input') === 'consumed_once'", timeout=5_000)
    page.keyboard.press("F9")
    page.wait_for_function("localStorage.getItem('windsprig:probe/stage') === 'completed'", timeout=5_000)
    page.wait_for_function("localStorage.getItem('windsprig:probe/save') === 'written'", timeout=5_000)

    reload_started = time.perf_counter()
    page.reload(wait_until="domcontentloaded")
    page.wait_for_function("localStorage.getItem('windsprig:probe/save') === 'restored'", timeout=5_000)
    page.wait_for_function("Number(localStorage.getItem('windsprig:probe/fps')) >= 30", timeout=10_000)
    cached_ms = int((time.perf_counter() - reload_started) * 1000)
    fps = float(signal(page, "fps") or "0")

    report = {
        "boot": True,
        "input": True,
        "audio": signal(page, "audio") == "ready",
        "stage_complete": True,
        "save_restored": True,
        "cold_ms": cold_ms,
        "cached_ms": cached_ms,
        "fps": fps,
        "console_errors": errors,
    }
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/browser-probe.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert cold_ms <= 12_000
    assert cached_ms <= 5_000
    assert fps >= 30.0
    assert errors == []
```

`tests/e2e/conftest.py` starts `python -m http.server 8765 --directory dist/web` in a subprocess, polls `http://127.0.0.1:8765`, yields that URL, and always terminates the server. Its `page` fixture launches a fresh headless Chromium context at viewport 1280×720 and closes context/browser in `finally` blocks.

- [ ] **Step 3: Run the tests and verify the red state**

Run:

```powershell
uv run pytest tests/unit/test_feasibility_probe.py -v
uv run pytest tests/e2e/test_web_feasibility.py -v
```

Expected: unit collection FAILS because `windsprig.feasibility` is absent; E2E setup FAILS because `dist/web` has not been built.

- [ ] **Step 4: Add opt-in probe instrumentation without a parallel runtime**

Create `windsprig/feasibility.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from windsprig.platform.services import StorageService


@dataclass(slots=True)
class FoundationProbe:
    storage: StorageService
    enabled: bool
    input_edge_count: int = 0

    def mark(self, name: str, value: str) -> None:
        if self.enabled:
            self.storage.write_text(f"probe/{name}", value)

    def consumed_input_edge(self) -> None:
        if not self.enabled:
            return
        self.input_edge_count += 1
        self.mark("input", "consumed_once" if self.input_edge_count == 1 else "consumed_more_than_once")
```

Create the probe with `enabled=services.browser is not None and services.browser.query_param("foundation_probe") == "1"`. Mark `boot=ready` only after the display, campaign, save service, initial screen, and first render are ready. Mark audio `ready` or `muted` from `AudioStatus` after pointer engagement. Count one designated `ConfirmCommand` edge in the fixed-step update; do not count pygame events.

Add this diagnostic command to `windsprig/input/commands.py` and map `pygame.K_F9` to it in `InputRouter`:

```python
@dataclass(frozen=True)
class ProbeCompleteCommand(InputCommand):
    pass
```

`FoundationScreen.fixed_update` calls `complete_probe_stage` only when it receives `ProbeCompleteCommand`; the method itself still checks `probe.enabled`, so F9 has no effect in normal native or browser play. Add a unit test that F9 cannot move an entity when `enabled=False`.

In `FoundationScreen`, permit F9 goal positioning only when the probe is enabled:

```python
def complete_probe_stage(self) -> None:
    if not self.probe.enabled or self.runtime is None:
        return
    player_id = self.runtime.player_entities[0]
    player_transform = self.runtime.world.get_component(player_id, Transform)
    _, _, goal_transform, _ = self.runtime.world.query(StageGoal, Transform, Collider)[0]
    player_transform.x = goal_transform.x
    player_transform.y = goal_transform.y
```

The next normal fixed step must let the real `StageGoalSystem` publish stage completion. The normal completion handler then calls `SaveService.save`; mark `stage=completed` and `save=written` only after the corresponding event and successful result. On initial load, if the probe profile already contains the probe stage clear, mark `save=restored`. Calculate `fps` from 120 consecutive rendered-frame durations after boot and store the measured value, not the configured target.

- [ ] **Step 5: Add the browser entry with no native shutdown behavior**

Create `web/main.py`:

```python
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pygame

from windsprig.app import GameApp
from windsprig.config import GameConfig
from windsprig.platform.web import create_web_services
from windsprig.screens.foundation import create_foundation_screen_factory


async def main() -> None:
    pygame.init()
    config = GameConfig()
    services = create_web_services(config)
    factory = create_foundation_screen_factory(config, services, lambda: datetime.now(timezone.utc))
    services.display.create_window(config.resolution, fullscreen=False)
    await GameApp(config, services, factory).run()


asyncio.run(main())
```

The file must contain neither `raise SystemExit` nor `pygame.quit`. `web/template.tmpl` supplies a visible `Loading Windsprig…` status, a 1280×720 canvas container, a keyboard/gamepad requirement, and a `<noscript>` explanation. Generate and commit a simple mint/gold leaf favicon with a deterministic pygame drawing script inside `tools/build_web.py`; do not source an external image.

- [ ] **Step 6: Implement deterministic build staging and size reporting**

`tools/build_web.py` must clean only `build/web-stage` and `dist/web`, copy the entry plus the installable package into an isolated staging tree, run the pinned module, copy the output, and calculate compressed transfer size:

```python
def build_web(probe: bool) -> dict[str, object]:
    root = Path(__file__).resolve().parents[1]
    source = root / "web"
    stage = root / "build" / "web-stage"
    output = root / "dist" / "web"
    shutil.rmtree(stage, ignore_errors=True)
    shutil.rmtree(output, ignore_errors=True)
    stage.mkdir(parents=True)
    for filename in ("main.py", "template.tmpl", "favicon.png"):
        shutil.copy2(source / filename, stage / filename)
    shutil.copytree(root / "windsprig", stage / "windsprig")
    shutil.copytree(root / "levels", stage / "levels")
    command = [
        sys.executable,
        "-m",
        "pygbag",
        "--build",
        "--template",
        str(stage / "template.tmpl"),
        str(stage),
    ]
    subprocess.run(command, cwd=root, check=True)
    built = stage / "build" / "web"
    if not (built / "index.html").is_file():
        raise SystemExit("Pygbag did not produce build/web-stage/build/web/index.html")
    shutil.copytree(built, output)
    compressed_bytes = sum(
        len(gzip.compress(path.read_bytes(), compresslevel=9))
        for path in output.rglob("*")
        if path.is_file()
    )
    report = {
        "pygbag": "0.9.3",
        "pygame_ce": "2.5.7",
        "probe": probe,
        "compressed_bytes": compressed_bytes,
        "compressed_limit_bytes": 30 * 1024 * 1024,
    }
    artifacts = root / "artifacts"
    artifacts.mkdir(exist_ok=True)
    (artifacts / "web-build.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if compressed_bytes > report["compressed_limit_bytes"]:
        raise SystemExit("compressed web transfer exceeds 30 MiB")
    return report
```

Use `argparse` to expose only `--probe`; include the probe package path when true and exclude test files from the build. Refuse to build unless `importlib.metadata.version("pygbag") == "0.9.3"` and `version("pygame-ce") == "2.5.7"`.

- [ ] **Step 7: Build, install Chromium, and run the complete probe twice**

Run:

```powershell
uv sync --all-extras --locked
uv run playwright install chromium
uv run python tools/build_web.py --probe
uv run pytest tests/unit/test_feasibility_probe.py tests/e2e/test_web_feasibility.py -v
uv run pytest tests/e2e/test_web_feasibility.py -v
```

Expected: build prints the `dist/web` path and a compressed byte count below 31,457,280; unit test passes; both Chromium runs PASS; `artifacts/browser-probe.json` reports boot/input/audio/stage/save true, cold ≤12,000 ms, cached ≤5,000 ms, FPS ≥30, and an empty console error list.

Add these exact generated paths to `.gitignore` before committing:

```gitignore
.venv/
artifacts/
dist/
build/web-stage/
__pycache__/
.pytest_cache/
.coverage
```

- [ ] **Step 8: Commit the buildable web path and feasibility test**

```powershell
git add .gitignore web windsprig/feasibility.py windsprig/app.py windsprig/screens/foundation.py windsprig/input/commands.py windsprig/input/router.py tools/build_web.py tests/unit/test_feasibility_probe.py tests/e2e
git commit -m "feat: prove Pygbag browser flow"
```

Expected: `dist/`, `build/web-stage/`, and `artifacts/` remain untracked/ignored; no generated Pygbag payload enters the commit.

### Task 10: Add the CI Skeleton and Record the Binary Feasibility Decision

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `tools/evaluate_web_feasibility.py`
- Create: `tests/unit/tools/test_evaluate_web_feasibility.py`
- Create after running the real gate: `docs/feasibility/pygbag-0.9.3.md`

**Interfaces:**
- Produces CI jobs `quality`, `tests`, and `web-feasibility` with no release/deployment side effects.
- Produces `evaluate(build_report, browser_report) -> tuple[Literal["pass", "fallback_required"], tuple[str, ...]]`.
- Produces one evidence document whose status is exactly `pass` or `fallback_required`.
- Consumes: locked dependencies, complete native test suite, Chromium reports, identity scan, and 85% branch threshold.

- [ ] **Step 1: Add failing evaluator tests**

```python
from tools.evaluate_web_feasibility import evaluate


def passing_browser() -> dict[str, object]:
    return {
        "boot": True,
        "input": True,
        "audio": True,
        "stage_complete": True,
        "save_restored": True,
        "cold_ms": 9000,
        "cached_ms": 3200,
        "fps": 58.0,
        "console_errors": [],
    }


def test_evaluator_requires_every_signal_and_budget() -> None:
    decision, reasons = evaluate(
        {"compressed_bytes": 20_000_000, "compressed_limit_bytes": 31_457_280},
        passing_browser(),
    )
    assert decision == "pass"
    assert reasons == ()


def test_evaluator_never_calls_partial_success_a_pass() -> None:
    browser = passing_browser()
    browser["save_restored"] = False
    browser["console_errors"] = ["Uncaught RuntimeError"]
    decision, reasons = evaluate(
        {"compressed_bytes": 31_457_281, "compressed_limit_bytes": 31_457_280},
        browser,
    )
    assert decision == "fallback_required"
    assert set(reasons) == {"save_restored", "console_errors", "compressed_bytes"}
```

- [ ] **Step 2: Run the test and verify the red state**

Run: `uv run pytest tests/unit/tools/test_evaluate_web_feasibility.py -v`

Expected: collection FAILS because `tools.evaluate_web_feasibility` does not exist.

- [ ] **Step 3: Implement the decision evaluator and evidence renderer**

Create `tools/evaluate_web_feasibility.py`:

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Literal

Decision = Literal["pass", "fallback_required"]


def evaluate(build: dict[str, object], browser: dict[str, object]) -> tuple[Decision, tuple[str, ...]]:
    reasons: list[str] = []
    for key in ("boot", "input", "audio", "stage_complete", "save_restored"):
        if browser.get(key) is not True:
            reasons.append(key)
    if int(browser.get("cold_ms", 99_999)) > 12_000:
        reasons.append("cold_ms")
    if int(browser.get("cached_ms", 99_999)) > 5_000:
        reasons.append("cached_ms")
    if float(browser.get("fps", 0.0)) < 30.0:
        reasons.append("fps")
    if list(browser.get("console_errors", [])):
        reasons.append("console_errors")
    if int(build.get("compressed_bytes", 99_999_999)) > int(build.get("compressed_limit_bytes", 0)):
        reasons.append("compressed_bytes")
    return ("pass", ()) if not reasons else ("fallback_required", tuple(reasons))


def render(decision: Decision, reasons: tuple[str, ...], build: dict[str, object], browser: dict[str, object]) -> str:
    reason_text = "none" if not reasons else ", ".join(reasons)
    route = (
        "pygame-ce/Pygbag remains the approved shared runtime."
        if decision == "pass"
        else "Stop downstream implementation and create the TypeScript/Phaser replacement plans before resuming."
    )
    return f"""# Pygbag 0.9.3 Feasibility Decision

**Status:** {decision}

**Decision:** {route}

**Failed requirements:** {reason_text}

## Measurements

- pygame-ce: 2.5.7
- Pygbag: 0.9.3
- Cold interactive: {browser.get('cold_ms')} ms (limit 12000 ms)
- Cached interactive: {browser.get('cached_ms')} ms (limit 5000 ms)
- Measured FPS: {browser.get('fps')} (floor 30)
- Compressed transfer: {build.get('compressed_bytes')} bytes (limit {build.get('compressed_limit_bytes')})
- Console errors: {json.dumps(browser.get('console_errors', []))}

## Scope Invariant

This decision does not remove or defer the six worlds, 30 stages, 90 stable motes, six unique bosses, complete action/state flow, local four-player support, browser build, Windows build, English/Korean support, accessibility, performance budgets, or release evidence required by the camera-ready design.
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", type=Path, default=Path("artifacts/web-build.json"))
    parser.add_argument("--browser", type=Path, default=Path("artifacts/browser-probe.json"))
    parser.add_argument("--write", type=Path, required=True)
    args = parser.parse_args()
    build = json.loads(args.build.read_text(encoding="utf-8"))
    browser = json.loads(args.browser.read_text(encoding="utf-8"))
    decision, reasons = evaluate(build, browser)
    args.write.parent.mkdir(parents=True, exist_ok=True)
    args.write.write_text(render(decision, reasons, build, browser), encoding="utf-8")
    print(f"Pygbag feasibility: {decision}")
    return 0 if decision == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Add the initial non-deploying GitHub Actions workflow**

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
        with:
          python-version: "3.12"
          enable-cache: true
      - run: uv sync --all-extras --locked
      - run: uv run ruff check .
      - run: uv run mypy windsprig/platform windsprig/input windsprig/meta windsprig/app.py windsprig/screens
      - run: uv run pytest tests/unit/test_public_identity.py -v

  tests:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest]
        python: ["3.12", "3.13"]
    runs-on: ${{ matrix.os }}
    env:
      SDL_VIDEODRIVER: dummy
      SDL_AUDIODRIVER: dummy
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
        with:
          python-version: ${{ matrix.python }}
          enable-cache: true
      - run: uv sync --all-extras --locked
      - run: uv run pytest -q --cov=windsprig --cov-branch --cov-report=term-missing --cov-fail-under=85

  web-feasibility:
    runs-on: ubuntu-latest
    env:
      SDL_VIDEODRIVER: dummy
      SDL_AUDIODRIVER: dummy
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
        with:
          python-version: "3.12"
          enable-cache: true
      - run: uv sync --all-extras --locked
      - run: uv run playwright install --with-deps chromium
      - run: uv run python tools/build_web.py --probe
      - run: uv run pytest tests/e2e/test_web_feasibility.py -v
      - run: uv run python tools/evaluate_web_feasibility.py --write docs/feasibility/pygbag-0.9.3.md
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: web-feasibility-evidence
          path: artifacts/
```

This skeleton deliberately has no publish, Vercel, PyInstaller, tag, or release job. The distribution plan adds those only after their artifacts and smoke tests exist.

- [ ] **Step 5: Run every local CI command from the locked environment**

Run:

```powershell
uv lock --check
uv sync --all-extras --locked
uv run ruff check .
uv run mypy windsprig/platform windsprig/input windsprig/meta windsprig/app.py windsprig/screens
$env:SDL_VIDEODRIVER='dummy'
$env:SDL_AUDIODRIVER='dummy'
uv run pytest -q --cov=windsprig --cov-branch --cov-report=term-missing --cov-fail-under=85
uv run python tools/build_web.py --probe
uv run pytest tests/e2e/test_web_feasibility.py -v
uv run python tools/evaluate_web_feasibility.py --write docs/feasibility/pygbag-0.9.3.md
```

Expected on the selected architecture: every command exits 0, branch coverage is at least 85%, and the evaluator prints `Pygbag feasibility: pass`. Inspect the generated evidence and confirm its measured values match both JSON reports.

- [ ] **Step 6A: If and only if the evaluator passes, commit the selected route**

Run:

```powershell
git add .github/workflows/ci.yml tools/evaluate_web_feasibility.py tests/unit/tools/test_evaluate_web_feasibility.py docs/feasibility/pygbag-0.9.3.md
git commit -m "ci: gate the shared browser runtime"
```

Expected: `docs/feasibility/pygbag-0.9.3.md` contains `**Status:** pass`. Proceed to the production-gameplay plan only after the commit and a green `git status --short`.

- [ ] **Step 6B: If the evaluator returns 2, record fallback_required and stop this plan**

Run:

```powershell
Select-String -Path docs/feasibility/pygbag-0.9.3.md -Pattern '\*\*Status:\*\* fallback_required'
git add .github/workflows/ci.yml tools/evaluate_web_feasibility.py tests/unit/tools/test_evaluate_web_feasibility.py docs/feasibility/pygbag-0.9.3.md
git commit -m "docs: record Pygbag feasibility failure"
```

Expected: `Select-String` finds exactly one status line and the evidence lists each failed hard requirement. Do not execute the current Python-specific gameplay/presentation/distribution plans. Use the writing-plans workflow to create these replacement documents before further feature implementation:

- `docs/superpowers/specs/2026-07-11-windsprig-phaser-fallback-design.md`: TypeScript/Phaser browser runtime, deterministic parity fixtures, and a Windows desktop wrapper, with every master-spec invariant copied unchanged.
- `docs/superpowers/plans/2026-07-11-windsprig-phaser-foundation.md`: package/tooling, deterministic simulation port, input roster, save v2, browser/native adapters, and CI.
- `docs/superpowers/plans/2026-07-11-windsprig-phaser-gameplay.md`: the full production action/state/ECS behavior and parity evidence.
- `docs/superpowers/plans/2026-07-11-windsprig-phaser-campaign-presentation.md`: all 30 stages, 90 motes, six bosses, art/audio/localization/accessibility.
- `docs/superpowers/plans/2026-07-11-windsprig-phaser-distribution.md`: hosted browser build, Windows wrapper, Sites/Vercel/GitHub release, and complete QA.

The fallback decision changes technology only. It is not permission to remove content, controls, multiplayer slots, accessibility, localization, target platforms, quality gates, or evidence.

## Final Foundation Verification

After a pass decision, run this clean-room sequence once more from a fresh checkout or isolated worktree:

```powershell
uv sync --all-extras --locked
$env:SDL_VIDEODRIVER='dummy'
$env:SDL_AUDIODRIVER='dummy'
uv run ruff check .
uv run mypy windsprig/platform windsprig/input windsprig/meta windsprig/app.py windsprig/screens
uv run pytest -q --cov=windsprig --cov-branch --cov-fail-under=85
uv run python tools/build_web.py --probe
uv run pytest tests/e2e/test_web_feasibility.py -v
uv run python tools/evaluate_web_feasibility.py --write docs/feasibility/pygbag-0.9.3.md
git status --short
```

Expected: all commands exit 0; the evidence remains `pass`; coverage is at least 85%; the browser report has no console errors; `git status --short` is empty. This completes only subproject 1. The full product remains incomplete until the gameplay, campaign/presentation, distribution/launch, and master requirement-to-evidence gates pass.
