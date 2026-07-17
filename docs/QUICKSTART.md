# Windsprig: Echoes of the Gale — Quickstart Manual

Ride the living wind, harmonize enemy echoes, and restore six sky worlds. This
guide gets one to four players into the game in a couple of minutes.

## 1. Start playing in 60 seconds

**Browser (fastest)**
1. Open **https://windsprig.vercel.app/** in a desktop Chromium browser
   (Chrome, Edge, or similar).
2. Make sure the window is at least **1024×576** and a keyboard or
   XInput-compatible gamepad is connected.
3. Press **Enter** at the title to reach the main menu, then choose **Play**.

**Windows**
1. Download the latest build from the
   [releases page](https://github.com/minchang-KIm/Kirby/releases)
   (Windows 10+, x64).
2. Unzip and run the executable. No install or account is needed.
3. Saves live under `%LOCALAPPDATA%/Windsprig`.

There is no account, login, or telemetry. Everything is local.

## 2. Join players (local co-op, 1–4)

Windsprig is shared-screen local co-op. **Only joined players affect gameplay,
the camera, the HUD, and stage goals** — so an idle controller never drags the
group along.

- **Player 1 / Player 2** can join on the keyboard.
- **Players 3 and 4** require compatible gamepads.
- To join, press **Confirm** (`Enter` or the South face button) at the join
  prompt. The **Controls** screen always shows live bindings and join guidance.

## 3. Controls

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

## 4. Core loop: Draw → Capture → Harmonize

Sprig has no built-in weapon. Power comes from enemy **echoes**:

1. **Draw** — Hold **Draw** (`S` / West button) to open a wind vortex that
   pulls nearby echoes toward you.
2. **Capture** — Keep holding until a drawn echo is captured in the vortex.
3. **Choose the outcome:**
   - **Release** it as a projectile through hazards and enemies, or
   - **Harmonize** with it to gain that echo's **ability**, then use it with
     **Use ability** (`F` / North button).
4. **Drop ability** (`T` / Right bumper) discards your current ability so you
   can capture a different one.

Explore each stage for the hidden **Wind Motes** — 90 in total, used for
completion goals.

## 5. The six echo abilities

Harmonize with the matching enemy echo to carry one of these through a stage:

| Ability | What it does |
| --- | --- |
| **Bloomblade** | A three-step melee combo; each press cuts an arc that can slice projectiles. |
| **Cinder** | Hold to charge an ember, then release a scaled fireball. |
| **Voltsong** | A conductor pulse that chains between nearby targets. |
| **Galehook** | Throws a boomerang that flies out and returns. |
| **Stoneheart** | An airborne-only armored ground slam (won't fire while grounded). |
| **Tempest** | Spends a full ability meter for a one-shot screen-clearing attack, then restores your previous ability. |

## 6. The journey: six worlds

Thirty stages across six hand-crafted sky worlds, each ending in a multi-phase
boss that unlocks the next world:

1. **Sunleaf Vale** — gust lifts and breakables
2. **Emberglass Works** — heat vents and conveyors
3. **Tidemoon Grotto** — currents and buoyant pods
4. **Thunderrail Heights** — storm rails and conductors
5. **Prismbloom Dream** — color beams and mirrors
6. **Stillstar Crown** — the final ascent

## 7. Options worth knowing

Open the pause menu (`Esc`) or the main-menu **Options** to adjust:

- **Languages:** English and Korean.
- **Controls:** remappable native gamepad bindings; hold *or* toggle modes for
  Draw and Guard.
- **Accessibility:** reduced motion, screen-shake control, high-contrast
  gameplay UI, and redundant icon/pattern/text HUD cues.
- **Audio:** master / music / SFX volume, plus mute.
- **Display:** fullscreen or windowed, and integer scaling.

## 8. Troubleshooting

- **No input registered:** confirm the player has actually *joined* — unjoined
  controllers do nothing by design.
- **Ability won't fire:** Stoneheart only works in the air; Tempest needs a full
  meter.
- **Browser won't start / looks cramped:** use desktop Chromium and a viewport
  of at least 1024×576.
- **Lost progress:** saves are per-browser-profile (browser) or under
  `%LOCALAPPDATA%/Windsprig` (Windows); they do not sync between the two.

---

More help: [Support](../SUPPORT.md) · [Privacy](../PRIVACY.md) ·
[Security](../SECURITY.md). Developers should see the **Develop and verify**
section of the [README](../README.md).
