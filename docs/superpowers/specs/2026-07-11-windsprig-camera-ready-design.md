# Windsprig: Echoes of the Gale — Camera-Ready Product Design

**Status:** Approved

**Date:** 2026-07-11

**Working public title:** *Windsprig: Echoes of the Gale*

**Release target:** One original, production-quality game shipped as a playable browser build and a Windows desktop build from the same Python/pygame-ce codebase.

## 1. Decision Summary

The existing project has a sound deterministic ECS foundation, a 30-stage campaign catalog, local four-player input abstractions, progression data, and 25 passing tests. Its executable surface is still a prototype: it renders primitive shapes, spawns four players unconditionally, has no complete menu/results/defeat flow, contains silent audio stubs, lacks browser packaging and CI, and retains Nintendo/Kirby identifiers that are unsuitable for a public product.

The approved direction is to preserve and harden the production ECS runtime while replacing the prototype shell with an original game called *Windsprig: Echoes of the Gale*. The same asynchronous pygame-ce application will run natively and through Pygbag/WebAssembly. Vercel will host the playable production build, Sites will host a polished launch/press surface linked to it, and GitHub will hold the source, CI, versioned releases, checksums, and Windows artifact.

This is a full-product program, not a vertical-slice reduction. The six-world, five-stage campaign remains the v1.0 scope. Content may be regenerated or replaced where the current data repeats layouts, but no world or stage is removed merely to make the release easier.

## 2. Alternatives Considered

### A. Unified pygame-ce/Pygbag release — selected

Keep one deterministic Python gameplay implementation, refactor the application loop to be async-aware, separate platform services, and build both browser and Windows packages from it.

Benefits:

- Reuses the tested ECS, campaign loader, progression rules, and replay foundations.
- Keeps browser and Windows gameplay behavior in one implementation.
- Avoids a long parity rewrite and duplicated bug surface.
- Produces static browser output that Vercel and Sites can host.

Costs and mitigations:

- WebAssembly startup is heavier than a native JavaScript game. The build gets a branded loading shell, compressed assets, caching, and a measurable startup budget.
- Browser audio, fullscreen, persistence, and gamepads have platform constraints. They are isolated behind adapters and covered by browser E2E tests.
- Pygbag requires pygame-ce and an async-aware loop. The first implementation milestone is a feasibility gate proving boot, input, audio, save, and stage completion in Chromium before presentation work expands.

### B. TypeScript/Phaser rewrite — fallback only

Port the runtime and content to a browser-native game, then wrap it for desktop. This offers excellent web tooling but duplicates a tested engine, creates parity risk, and delays player-facing improvements. It is allowed only if the feasibility gate produces evidence that pygame-ce/Pygbag cannot meet the release criteria; the feature and campaign scope must remain unchanged.

### C. Desktop game with hosted landing page — rejected

This would be the fastest release, but the hosted product would not be playable and would not fulfill the approved browser-first experience.

## 3. Product Identity and Audience

### 3.1 Original identity

The public game, package, executable, window title, repository display name, documentation, screenshots, and website must not use Nintendo, Kirby, Return to Dream Land, or any Nintendo character, logo, visual asset, audio, level, or copy. The mechanic is re-expressed through an original wind-and-echo fiction rather than copied terminology or character design.

*Windsprig* is a working release name selected after a preliminary web collision scan found no obvious video-game title match. That scan is not a trademark opinion. Public copy must avoid claiming formal clearance, and any later evidence of a material naming conflict triggers a like-for-like rebrand without changing product scope.

### 3.2 Fiction and tone

The player controls Sprig, a small mint-and-gold seed spirit wearing a wind-sail scarf. Sprig restores motion to six sky islands after a force called the Stillness traps their living weather. Sprig draws loose echoes and enemies into a vortex, then releases, launches, or harmonizes with the captured echo to gain an ability.

The tone is bright, kinetic, warm, and suitable for a general audience. Visual silhouettes, terminology, lore, and interface motifs must be recognizably original. The art direction is layered storybook geometry: crisp dark outlines, paper-cut shapes, soft gradients, wind ribbons, leaf motifs, and high-contrast UI panels.

### 3.3 Audience and supported play

- Primary: solo players using keyboard or one gamepad on Windows or a desktop Chromium browser.
- Secondary: two-to-four local players using two keyboard layouts and/or gamepads.
- The website is responsive, but v1.0 gameplay requires a physical keyboard or standards-compatible gamepad and a viewport at least 1024×576.
- Online multiplayer, accounts, cloud saves, monetization, and touch controls are not v1.0 features.

## 4. Product Goals and Release Invariants

The product is release-ready only when all of these are true:

1. A new player can launch from the hosted URL, select or create a profile, learn the controls in-game, complete a stage, see results, and resume progress after reloading.
2. A Windows user can download a versioned ZIP from GitHub Releases, launch it from any directory without Python installed, complete the same flow, and retain saves under the OS user-data directory.
3. Solo play never spawns inactive players or lets them influence the camera, HUD, goal logic, or difficulty.
4. Players can join and leave intentionally, identify their avatar and device, navigate menus with that device, and recover from disconnects.
5. Movement, buffered jump, coyote time, hover, draw/capture, launch, harmonize, ability use, guard, dodge, damage, death, checkpoint, victory, and defeat are implemented in the production ECS runtime and verified there.
6. The complete campaign contains 30 playable stages, 90 stable collectible motes, six visually and mechanically distinct worlds, and six unique multi-phase bosses.
7. Every player-facing object has an original cohesive visual treatment; every core action has immediate visual and/or audible feedback.
8. No public build contains protected Nintendo assets or public-facing Nintendo/Kirby identifiers.
9. Browser and desktop builds are produced reproducibly from the same tagged commit, and the release page includes licenses, notes, artifact hashes, and known requirements.
10. Automated checks, browser/desktop smoke tests, hands-on computer QA, and production URL verification all pass from current artifacts before v1.0 is declared complete.

## 5. Player Experience

### 5.1 State flow

The application uses explicit screens and transitions:

```text
Boot/Loading
  -> Title
  -> Profile Select/Create
  -> Main Hub
       -> World Map -> Stage Intro -> Playing
            -> Paused -> Playing | Restart Confirm | Map Confirm
            -> Results -> Next Stage | Replay | World Map
            -> Defeat -> Checkpoint Retry | Stage Retry | World Map
       -> Settings
       -> Controls & Accessibility
       -> Credits
```

No gameplay action immediately destroys progress or exits a stage without confirmation. Stage clear pauses the simulation, presents results and rewards, commits the save, and waits for a player choice. A visible but unobtrusive status indicator confirms successful saves.

### 5.2 Title and profile flow

- Title screen: logo, animated background, Start, Settings, Controls, Credits, and Quit on desktop.
- Three profile slots show player name, completion percentage, total motes, last played stage, and play time.
- Creating a profile accepts a short local display name with a safe default.
- Deleting a profile requires a hold-to-confirm action and creates one recoverable backup.
- The browser never asks for an account and does not transmit save data.

### 5.3 Join and device flow

- P1 joins with the first Start/Enter input and may be keyboard or gamepad.
- Additional players join from the hub, map, stage intro, or pause lobby by pressing the displayed join control.
- Only joined players receive entities, HUD panels, camera weight, lives, and goal participation.
- Each slot has a persistent color, icon, label, and device prompt that remain distinguishable without color.
- Disconnecting a required device pauses the game and offers reconnect, reassign, or remove-player actions.
- Menu navigation is available from every joined device. One designated leader confirms destructive navigation.

### 5.4 Core action loop

The production loop is move -> explore -> draw an echo/enemy -> choose how to use it -> overcome traversal/combat -> collect motes -> reach the goal -> review results and unlocks.

Capture has three readable outcomes:

- **Release:** cancel the vortex safely when nothing is captured.
- **Launch:** release a captured enemy as a visible high-impact wind projectile.
- **Harmonize:** press the ability action while holding a compatible capture to equip its echo ability.

The captured state is shown above the player and in the HUD. Enemies without an ability can still be launched. Dropping an equipped ability creates a recoverable echo pickup rather than silently deleting it.

### 5.5 Movement and defense

- Ground movement has acceleration, deceleration, facing, slope-safe collision, and clear run/idle transitions.
- Jump supports the configured 100 ms coyote window and 120 ms input buffer in `StageRuntime`.
- Holding jump after takeoff activates a finite hover with visible stamina/readiness feedback.
- Guard reduces qualifying damage and knockback while slowing movement; attacks from behind or guard-breaking boss moves remain dangerous.
- Dodge produces a short directional burst with a tested invulnerability window, cooldown, afterimage, and reduced-motion alternative.
- Hazard recovery uses the last checkpoint, applies a clear cost, and prevents unwinnable soft locks.

### 5.6 Ability families

The six public abilities are mechanically distinct and all appear in campaign content:

| Ability | Role | Required distinction |
|---|---|---|
| Bloomblade | close melee | short combo, directional arc, projectile cutting |
| Cinder | ranged pressure | charged ember, lingering burn zone |
| Voltsong | area control | chained pulse, conductor interactions |
| Galehook | mobility/control | boomerang pull, switch activation |
| Stoneheart | heavy/defense | ground slam, temporary armor, breakable floors |
| Tempest | rare super | meter-limited screen action, never a permanent dominant loadout |

Ability names, icons, palette accents, attack timing, hitbox shape, sound, particles, and enemy source are unique. Generic projectiles are not an acceptable implementation for every family.

### 5.7 Combat feedback

- Projectiles and melee effects render visibly and advance exactly once per simulation step.
- Hits provide impact flash, particles, directional knockback, short hit-stop within comfort limits, and distinct audio.
- Invulnerability is visible through a patterned flash that remains readable with reduced motion.
- Boss attacks telegraph with silhouette, ground marker, sound, and sufficient reaction time.
- Damage, guard, dodge, capture, harmonize, mote collection, checkpoint, goal, defeat, and victory each have distinct feedback.

## 6. Campaign and Progression

### 6.1 Campaign structure

Each world contains four stages and one boss stage. Stages may share modular art primitives but must not duplicate complete geometry, encounter order, hidden-mote route, or boss arena.

| World | Identity | Mechanics | Boss concept |
|---|---|---|---|
| 1. Sunleaf Vale | warm meadows and windmills | onboarding, gust lifts, simple breakables | Rootjaw, a burrowing bramble beast |
| 2. Emberglass Works | glowing kiln city | conveyors, heat vents, timed shutters | Crucible Crab, armor and molten lanes |
| 3. Tidemoon Grotto | moonlit water caverns | currents, buoyant pods, falling water | Luma Eel, arena currents and light decoys |
| 4. Thunderrail Heights | storm observatory | rails, conductors, rotating towers | Volt Roc, aerial dives and lightning chains |
| 5. Prismbloom Dream | crystalline living garden | mirrors, color beams, gravity blooms | Prism Warden, reflection and clone phases |
| 6. Stillstar Crown | fractured sky palace | mastery remix, silence fields, ability locks | The Stillness, three phases using learned systems |

Every non-boss stage has three collectible Wind Motes with stable IDs, not a repeatable integer reward. Replaying a stage can improve time or recover missed motes but cannot inflate the permanent total beyond that stage's maximum.

### 6.2 Stage quality rules

- Each stage has an authored name and a two-to-six minute target clear time for an experienced solo player.
- Stage 1 introduces a world's mechanic safely; stages 2–3 combine it with traversal and combat; stage 4 is a mastery gauntlet; stage 5 is the boss.
- Checkpoints occur after major challenge clusters and before bosses.
- Critical progression never requires a hidden collectible.
- Optional routes reward motes, time-saving mastery, or ability choice rather than blind leaps.
- No goal can trigger from an inactive or dead player. In co-op, a clear requires the active team to reach the goal or accept a leader-confirmed gather countdown.

### 6.3 Progression

- Clearing a stage unlocks the next node; clearing a boss unlocks the next world.
- Mote thresholds unlock challenge variants, gallery entries, and palette rewards, never mandatory story progression.
- Results show clear time, best-time comparison, mote status, ability discoveries, and newly unlocked content.
- The world map displays locked routes, connectors, boss nodes, stage names, motes, best times, and completion state using icon, shape, and text in addition to color.
- Completion percentage is derived from stages, motes, bosses, and optional challenges through a documented formula.

## 7. Presentation System

### 7.1 Rendering and display

- Render to a 1280×720 logical canvas and scale with letterboxing to common desktop aspect ratios and DPI settings.
- Support windowed, borderless/fullscreen, integer scaling where possible, and persisted display settings.
- The camera uses smooth damped tracking, directional look-ahead, stage bounds, a solo safe frame, and co-op catch-up/respawn rules.
- Reduced-motion mode disables shake and afterimage-heavy effects while preserving state readability.

### 7.2 Art

- Runtime art uses original layered vector-style raster sprites and procedural backgrounds designed specifically for this project.
- Sprig must not be a pink sphere or mimic Kirby's face, proportions, feet, pose language, or iconography. The approved silhouette uses a seed/leaf body, scarf sail, twig limbs, and asymmetrical leaf crest.
- Each world has its own palette, parallax background, tile family, environmental props, particles, and transition card.
- Each standard enemy type, elite, boss phase, player slot, ability, collectible, hazard, checkpoint, and goal has a distinct silhouette.
- Required player states include idle, run, jump, fall, hover, draw, captured, harmonize, attack, guard, dodge, hurt, defeated, and victory.
- All third-party fonts or auxiliary assets must be permissively licensed and recorded in `assets/LICENSES.md`. Mandatory assets missing from a release fail CI.

### 7.3 UI and accessibility

- Player-facing text uses consistent localized names rather than internal IDs.
- English is the source locale; Korean remains fully supported. Text is loaded from locale data rather than embedded throughout the renderer.
- Bundle an OFL-licensed font with Korean coverage and retain its license.
- Body text and critical HUD text target at least 4.5:1 contrast; large decorative text targets at least 3:1.
- HUD panels use icons, shapes, labels, and patterns; no status depends on color alone.
- Settings include master/music/SFX volume, mute, fullscreen/windowed, screen shake, reduced motion, hold/toggle behavior where applicable, and control reference.
- Controls are remappable on desktop where pygame supplies stable identifiers; the browser supplies preset keyboard layouts plus gamepad mapping guidance when persistence is unreliable.

### 7.4 Audio

- Ship original generated or authored music and SFX, not placeholder silence.
- Each world has a loopable theme and its boss has a phase-aware variation; the title, map, results, and credits have dedicated cues.
- Core actions listed in section 5.7 have unique SFX.
- Browser audio begins only after user engagement and resumes gracefully after tab suspension.
- Audio initialization failure falls back to a visible muted state and never blocks gameplay.
- Music and SFX assets, generation scripts, provenance, and licenses are committed or reproducibly generated.

## 8. Technical Architecture

### 8.1 Package boundary

The public Python package becomes `windsprig`. Nintendo-derived package, executable, title, and copy identifiers are removed from active source and release artifacts. Legacy modules are migrated into the production package or deleted after their tested behavior is absorbed; the shipped executable must not contain two competing game runtimes.

Target structure:

```text
windsprig/
  app.py                    async application coordinator
  config.py                 validated settings and release metadata
  platform/
    services.py             storage/audio/display/browser protocols
    native.py               Windows/local implementation
    web.py                  Pygbag/browser implementation
  screens/
    title.py profile.py hub.py world_map.py stage.py results.py settings.py
  input/
    devices.py bindings.py commands.py router.py roster.py
  core/
    ecs.py events.py rng.py time.py
  gameplay/
    runtime.py components/ systems/ abilities/
  render/
    assets.py renderer.py animation.py effects.py camera.py ui.py
  audio/
    manager.py music.py
  content/
    campaign.json abilities.json strings.en.json strings.ko.json
  meta/
    save_manager.py completion.py unlock_rules.py world_map.py
web/
  main.py                   Pygbag entry point
  favicon.png
  template.tmpl             branded loader and accessibility shell
tools/
  build_web.py validate_content.py generate_audio.py
tests/
  unit/ integration/ e2e/ visual/
```

File boundaries may adapt to existing conventions, but application coordination, platform services, gameplay simulation, rendering, screens, and content validation must remain independently testable.

### 8.2 Application loop

`GameApp.run()` becomes an async application loop that yields once per rendered frame. Desktop uses `asyncio.run`, while the Pygbag entry point invokes the same loop without calling `sys.exit` or `pygame.quit` after browser startup. Fixed simulation steps remain deterministic and are separated from rendering cadence.

Discrete input events are queued until at least one fixed step consumes them, preventing button presses from disappearing on zero-step render frames. Continuous input is sampled per render frame and copied into subsequent fixed steps as held state only.

### 8.3 Data flow

```text
pygame events / connected devices
  -> InputRouter + ActiveRoster
  -> current Screen or device-agnostic InputFrame
  -> GameSession / StageRuntime
  -> deterministic ECS systems
  -> domain events + frame snapshot
  -> Effects/Audio subscribers + Renderer
  -> logical canvas -> scaled display

stage result
  -> CompletionService
  -> versioned SaveService
  -> Native atomic file OR Browser local storage
  -> results/world-map view model
```

Screens consume immutable view models rather than querying unrelated ECS internals. Gameplay systems publish semantic events such as `PlayerDamaged`, `EnemyCaptured`, `AbilityEquipped`, `MoteCollected`, `CheckpointReached`, and `StageCompleted`; presentation subscribers turn them into effects and sound without altering deterministic state.

### 8.4 Platform services

Define narrow protocols for:

- storage load/save/backup and capability reporting;
- audio initialization, buses, cue playback, pause/resume, and volume;
- display sizing/fullscreen and browser-safe feature detection;
- monotonic time and app lifecycle notifications;
- optional browser bridge calls.

Native saves use `%LOCALAPPDATA%/Windsprig/save_data.json` by default, with temp-file write, flush, atomic replace, and one known-good backup. Browser saves use local browser storage through the Pygbag JavaScript bridge, encode the same schema, and expose storage failure to the UI. No code path writes relative to the launch directory in a release build.

### 8.5 Save schema

Schema v2 contains:

- three named profiles;
- campaign version and save version;
- unlocked nodes/worlds;
- stable collected-mote IDs;
- best times and clear counts;
- discovered abilities and challenge rewards;
- per-profile play time;
- global display, audio, accessibility, language, and control settings.

Loading validates types and ranges. Malformed or incompatible data is moved to a timestamped recovery record, the last known-good backup is attempted, and a new safe schema is offered with an in-game explanation. Migrations are explicit, deterministic, and tested. A save from the prototype may be imported once by mapping cleared nodes, best times, and capped sphere counts; invalid accumulated counts are clamped to available mote IDs.

### 8.6 Determinism and content validation

- Replace process-randomized `hash(stage_id)` with a stable digest-derived integer seed.
- Every stage and collectible has a stable unique ID.
- A content validator checks references, bounds, spawn safety, reachable goal metadata, required ability sources, mote counts, boss definitions, locale keys, and duplicate full-layout signatures.
- Runtime snapshots and replay hashes exclude presentation-only state.
- Browser and desktop replay fixtures must produce the same deterministic snapshot sequence for representative stages.

## 9. Error Handling and Recovery

- Missing mandatory content, sprite, font, or audio is a build/CI failure. In developer mode, the runtime shows a diagnostic fallback with the missing asset ID.
- Optional audio failure produces a visible mute indicator and preserves playability.
- Save read/write failure never crashes the render loop; it preserves the in-memory session, displays a retryable notice, and avoids reporting success.
- A controller disconnect pauses only when it removes an active player's sole device.
- Browser focus loss pauses local input and audio safely; returning never applies stale held commands.
- If fixed-step catch-up exceeds a bounded budget, the application drops excess accumulated render time, records a performance diagnostic, and avoids a spiral of death.
- Unhandled production errors transition to a branded recovery screen containing a short error code, restart action, and local log/export guidance without exposing secrets.

## 10. Testing and Quality Gates

### 10.1 Automated coverage

- Unit tests cover platform-independent rules, state transitions, input buffering, roster behavior, save migrations, completion math, content validation, camera targeting, and every ability strategy.
- Integration tests drive `StageRuntime` through movement, capture/launch/harmonize, combat, checkpoints, victory, defeat, co-op join/leave, and deterministic replay.
- Headless application tests cover title -> profile -> map -> stage -> pause/results/defeat transitions and assert view models plus semantic events.
- Visual tests render representative screens and stages at fixed seeds and compare approved perceptual snapshots with tolerances.
- Packaging smoke tests launch the Windows build with a `--smoke-test` path that initializes mandatory systems, renders frames, saves to an isolated directory, and exits successfully.
- Browser E2E tests load the built Pygbag output, dismiss the audio gate, exercise keyboard input, start a stage, write/reload a save, toggle fullscreen where supported, and report uncaught console errors.

Production modules target at least 85% branch coverage overall. More importantly, every release invariant in section 4 must have a named automated or manual verification; aggregate coverage cannot substitute for missing flow coverage.

### 10.2 Performance budgets

- Simulation remains stable at a 16 ms fixed step.
- Target: 60 rendered FPS at 1280×720 on a typical modern Windows laptop and desktop Chromium; minimum sustained gameplay floor is 30 FPS on the documented baseline.
- Browser time from cached loader start to interactive title is at most 5 seconds on the test connection; cold start is at most 12 seconds with visible progress and no blank canvas.
- Compressed browser transfer target is at most 30 MB for v1.0. Any exception requires an asset-size report and a documented optimization decision.
- A 30-minute soak produces no unbounded entity, event, surface, or audio-channel growth.

### 10.3 Hands-on QA

Before release, use computer control for the Windows artifact and browser control for the deployed build. Verify:

- keyboard-only solo completion;
- gamepad-only title-to-results flow;
- two-player join, identity, camera, pause, disconnect, and rejoin;
- profile create/delete/recovery;
- settings persistence;
- every world, boss, ability source, and collectible total;
- 1280×720, 1440×900, and 1920×1080 presentation;
- muted/audio-device-unavailable behavior;
- save corruption recovery;
- browser refresh, focus loss, cache, and clean-profile behavior;
- Windows launch from a path containing spaces and from outside the repository.

### 10.4 Code-study readability

- Treat the repository as both production source and a learning artifact. Public modules, protocols, classes, and non-obvious functions receive concise docstrings that state their contract, ownership, timing, or failure semantics.
- Comments explain *why* an invariant, ordering rule, compatibility seam, or safety check exists. Do not add comments that simply translate the next statement into prose.
- Prefer explicit types, domain names, small cohesive functions, dependency injection at platform boundaries, and immutable value objects. Avoid unexplained abbreviations, hidden global state, and duplicate implementations.
- Record project-wide conventions in `docs/development/code-conventions.md`. Every task review checks new code against that guide, and the final whole-codebase review repairs stale or misleading comments before release.
- Architectural boundaries and surprising tradeoffs remain discoverable through focused design notes, test names, and links from the code-convention guide; comments must never be used to excuse unclear code.

## 11. Build, CI, and Release

### 11.1 Dependency and build reproducibility

- Declare runtime and optional development/web dependencies in `pyproject.toml` with a supported Python floor and reproducible lockfile.
- Use pygame-ce for both targets and pin a verified Pygbag toolchain version.
- Remove unused runtime dependencies.
- README commands use the actual installed `uv` executable or a documented standard-venv fallback.
- Windows packaging analyzes a supported entry module, includes the package, content, assets, root license, notices, icon, and version metadata, and is built from a clean environment.

### 11.2 GitHub

GitHub Actions provides:

1. lint/type/content validation;
2. unit and integration tests with coverage;
3. headless visual/application tests;
4. Pygbag web build plus browser smoke tests;
5. Windows PyInstaller build plus package smoke test;
6. release job on an annotated `v1.0.0` tag, attaching the Windows ZIP, web archive, checksums, notices, and generated release notes.

The repository is renamed and described with the original product identity before public promotion. Existing commit history is retained, while current documentation explains that no Nintendo assets are included and that the released product is unaffiliated and original.

### 11.3 Vercel and Sites

- The Pygbag build emits a static `dist/web` artifact with a branded HTML loader, favicon, metadata, social card, privacy-safe analytics disabled by default, cache headers, service worker, and game canvas.
- Vercel serves `dist/web` as the canonical playable production URL and is verified after every production deployment.
- Sites hosts the launch/press surface: product story, trailer or gameplay capture, screenshots, controls, accessibility/support details, credits, GitHub link, Windows download link, and Play button pointing to the canonical game URL.
- Both surfaces use the same approved brand copy and assets. No release is announced while either has broken links or stale version metadata.

### 11.4 Version and artifact policy

- The first camera-ready public release is `v1.0.0`.
- All artifacts embed the same semantic version and commit SHA.
- Release archives are immutable and accompanied by SHA-256 checksums.
- Root MIT license, third-party notices, font licenses, asset/audio provenance, and source link ship with every artifact.
- Code signing is preferred when a certificate is available; absence of signing is disclosed rather than hidden.

## 12. Implementation Decomposition

The work is large enough to require independently testable subprojects, but all remain part of the approved v1.0 objective:

1. **Release foundation and browser feasibility:** original package identity, reproducible dependencies, async loop, platform adapters, active roster, stable seed, repaired saves, Pygbag boot/input/audio/save spike, and CI skeleton.
2. **Production gameplay loop:** consolidate the ECS runtime; implement movement/defense/capture choices/abilities/combat/checkpoints/states/results; add flow-level tests.
3. **Campaign, progression, and presentation:** rebuild 30 distinct stages and six bosses; add stable motes, world map, art, animation, HUD, localization, music, SFX, settings, accessibility, and visual tests.
4. **Distribution and launch:** Windows package, PWA/static shell, Vercel production deployment, Sites press surface, GitHub release automation, complete manual QA, and v1.0 release evidence.

Each subproject receives a detailed implementation plan. A subproject is complete only when its own tests pass and its interfaces satisfy downstream plans. Completing an early subproject does not redefine the full product goal as achieved.

## 13. Requirement-to-Evidence Matrix

| Requirement | Authoritative completion evidence |
|---|---|
| Original public identity | release artifact/string scan, repository/website inspection, asset provenance file |
| 30 stages / 6 worlds / 6 bosses / 90 motes | content validator output plus automated full-catalog load and traversal checks |
| Solo and four-player behavior | production-runtime integration tests plus hands-on keyboard/gamepad QA |
| Complete action and state flow | named unit/integration/E2E tests and recorded Windows/browser QA |
| Cohesive visuals/audio | asset manifest, visual snapshots, runtime captures, event-to-cue coverage |
| Robust native/browser saves | migration/corruption/atomicity tests plus browser reload and native path QA |
| Browser release | successful Pygbag build, browser E2E report, verified Vercel production URL |
| Windows release | clean CI artifact, isolated smoke test, checksum, verified GitHub Release |
| Sites launch surface | published URL inspection, link/version checker, responsive screenshots |
| Camera-ready quality | all automated gates, performance report, full manual checklist, zero open release-blocking issues |

## 14. Non-Negotiable Completion Rule

The project is not camera-ready merely because tests pass, a prototype deploys, or a subset of stages looks polished. Completion requires current evidence for every release invariant and every row in the requirement-to-evidence matrix. Unknown, indirect, stale, or partial evidence counts as incomplete.
