# Asset Provenance Ledger

Windsprig currently ships only original, repository-authored release content. This ledger must be updated before any third-party asset is added to a distribution.

| Asset | Source | License | Use |
| --- | --- | --- | --- |
| Procedural shapes, colors, and HUD elements | Original runtime rendering in `windsprig/app.py`, `windsprig/assets.py`, and `windsprig/hud.py` | MIT (`LICENSE`) | Players, enemies, terrain, goals, collectibles, and interface placeholders |
| Campaign layouts | Original data in `windsprig/content/campaign.json` and `levels/level_01.json` | MIT (`LICENSE`) | Six-island campaign structure, stage geometry, spawns, and Wind Mote placement |
| Echo-ability definitions | Original data in `windsprig/content/abilities.json` | MIT (`LICENSE`) | Echo ability behavior and tuning |
| Audio | No audio asset is currently distributed | Not applicable | Runtime audio hooks remain silent until an original or separately licensed asset is recorded here |
