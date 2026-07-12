# Windsprig: Echoes of the Gale

Ride the living wind, harmonize enemy echoes, and restore six hand-crafted sky worlds in a storybook action-platform adventure for one to four local players.

[Play in your browser](https://windsprig.vercel.app/) · [Windows releases](https://github.com/minchang-KIm/windsprig/releases) · [Support](SUPPORT.md) · [Privacy](PRIVACY.md) · [Security](SECURITY.md)

Windsprig is an original local action-platform game starring Sprig, a mint-and-gold seed spirit with a wind-sail scarf. Draw nearby echoes into a vortex, launch them through hazards, or harmonize with their resonance to carry one of six abilities through 30 stages, six multi-phase bosses, and 90 hidden Wind Motes.

## Play requirements

- Browser: desktop Chromium, a viewport of at least 1024×576, and a physical keyboard or compatible gamepad.
- Windows: Windows 10 or newer, x64, and a physical keyboard or XInput-compatible gamepad.
- Local co-op: one to four joined players sharing one display. Only joined players affect gameplay, camera, HUD, and goals.
- Saves are local. Browser profiles remain in that browser; Windows profiles remain under `%LOCALAPPDATA%/Windsprig`.
- No account or telemetry is used.

## Controls

| Action | Player 1 keyboard | Player 2 keyboard | Gamepad |
| --- | --- | --- | --- |
| Move / navigate | `A` / `D` | `Left` / `Right` | Left stick / D-pad |
| Jump / hover | `W` | `Up` | South face button |
| Draw / release | Hold / release `S` | Hold / release `Down` | West face button |
| Use ability | `F` | `.` | North face button |
| Guard | `G` | `/` | Left bumper |
| Dodge | `H` | `Right Shift` | East face button |
| Drop ability | `T` | `,` | Right bumper |
| Confirm / gather | `Enter` | `Enter` | South face button |
| Back / pause | `Esc` | `Esc` | Menu button |

Players 3 and 4 require compatible gamepads. The Controls screen always shows the active bindings and join guidance.

## Accessibility and languages

Windsprig includes English and Korean, keyboard and gamepad control references, remappable native gamepad bindings, hold/toggle options for draw and guard, reduced motion, screen-shake control, master/music/SFX volume controls, mute, fullscreen/windowed display, integer scaling, redundant icon/pattern/text HUD cues, and high-contrast gameplay UI.

## Develop and verify

Python 3.12 or 3.13 is supported. The lockfile is authoritative.

```powershell
uv sync --all-extras --locked
uv run --locked --no-sync python -m windsprig
uv run --locked --no-sync pytest -q
uv run --locked --no-sync ruff check .
uv run --locked --no-sync mypy windsprig/platform windsprig/input windsprig/meta windsprig/app.py windsprig/screens tools
uv run --locked --no-sync python tools/validate_content.py
uv run --locked --no-sync python -I tools/build_web.py --output dist/web
```

The Windows release builder and packaged smoke test are documented by `python tools/build_windows.py --help` once the desktop packaging extras are installed.

## Architecture and provenance

- `windsprig/core/`: deterministic ECS, events, fixed-step time, and random-number ownership.
- `windsprig/gameplay/`: the production stage runtime, abilities, systems, snapshots, and sessions.
- `windsprig/input/`: device-independent commands, bindings, rosters, and routing.
- `windsprig/render/`: logical display, camera, animation, effects, HUD, and renderer.
- `windsprig/meta/`: profiles, progression, completion, saves, and migrations.
- `windsprig/content/`: the canonical bilingual campaign and gameplay data.

All shipped art and audio are original deterministic Windsprig project assets. The Korean font is a pinned, licensed Noto Sans KR subset. See [asset and font provenance](assets/LICENSES.md), [credits](CREDITS.md), and the [code-study conventions](docs/development/code-conventions.md).

Windsprig uses only its original characters, names, art, audio, levels, and copy. Code is available under the [MIT License](LICENSE).
