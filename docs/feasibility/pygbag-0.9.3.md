# Pygbag 0.9.3 Feasibility Decision

**Status:** pass

**Decision:** pygame-ce/Pygbag remains the approved shared runtime.

**Failed requirements:** none

## Source and toolchain

- Source commit: `71d8836f0739181b104dfed6fbcbd7a5bedf1182`

| Component | Observed version |
| --- | --- |
| pygame-ce | `2.5.7` |
| Pygbag | `0.9.3` |
| Pygbag Python build | `3.12` |
| Windsprig release | `1.0.0` |
| Evaluator Python | `3.12.10` |
| mypy | `1.20.2` |
| Playwright | `1.61.0` |
| pytest | `8.4.2` |
| pytest-cov | `6.3.0` |
| Ruff | `0.15.21` |
| uv | `0.11.28` |

## Requirement evidence

| Requirement | Observed | Rule | Result |
| --- | --- | --- | --- |
| probe artifact | `true` | exactly true | pass |
| boot | `true` | exactly true | pass |
| input | `true` | exactly true | pass |
| audio available or visibly muted | `true` | exactly true | pass |
| audio status | `ready` | ready or muted | pass |
| stage complete | `true` | exactly true | pass |
| save written | `true` | exactly true | pass |
| save restored | `true` | exactly true | pass |
| gameplay active | `true` | exactly true | pass |
| cold interactive | `2983` | ≤ 12000 ms | pass |
| cached interactive | `1824` | ≤ 5000 ms | pass |
| Gameplay FPS | `60.181` | ≥ 30, active StageRuntime only | pass |
| console errors | `[]` | exact empty list | pass |
| compressed transfer | `165784` | ≤ 31457280 bytes | pass |

## Gameplay-only measurements

FPS is sampled only across consecutive rendered frames backed by an active real `StageRuntime`.

| Metric | Observed | Rule |
| --- | ---: | --- |
| Gameplay FPS | 60.181 | ≥ 30, active StageRuntime only |

| Run | Cold interactive (ms) | Cached interactive (ms) | Gameplay FPS | Gameplay active | Console errors |
| --- | ---: | ---: | ---: | --- | --- |
| local run 1 | 5217 | 1889 | 60.181 | true | [] |
| local run 2 | 2915 | 1760 | 60.09 | true | [] |

## Artifact integrity

- Declared uncompressed bytes: 179818
- Declared compressed bytes: 165784
- Canonical compressed limit: 31457280 bytes
- Declared files: ["favicon.png", "index.html", "web-stage.apk", "web-stage.tar.gz"]

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `favicon.png` | 624 | `b49eb01e33b16db661b059926694a6585e103bf966e7cf385c8d3d74ce15de8e` |
| `index.html` | 6366 | `a9eb9dd403d26f73f2af5618d1ad5878f4f3b85bda3f21fb62436921e2848884` |
| `web-stage.apk` | 98796 | `14b9332ce7d024abf8bc76851e250a06210726f882b3961ebff24f1119570e98` |
| `web-stage.tar.gz` | 74032 | `521aaa0515204e2e388a3652e9504bff92411bd59edf8e92c556cfd87793032b` |

## Scope Invariant

This decision does not remove or defer the six worlds, 30 stages, 90 stable motes, six unique bosses,
complete action/state flow, local four-player support, browser build, Windows build, English/Korean support,
accessibility, performance budgets, or release evidence required by the camera-ready design.
