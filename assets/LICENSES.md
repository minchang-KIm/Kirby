# Asset License Notes

This repository currently ships with generated placeholder art/audio surfaces created in code (`kirby_clone/assets.py` and `kirby_clone/audio.py`), so no third-party binary assets are required to run the game.

Planned drop-in free packs (for future visual/audio upgrade):

1. Kenney Platformer Art (CC0)
- URL: https://kenney.nl/assets
- License: CC0 1.0
- Attribution: Not required (optional credit to Kenney)

2. OpenGameArt CC0 SFX collections
- URL: https://opengameart.org/
- License: Depends on pack; only CC0 packs should be used
- Attribution: Per selected pack metadata

3. itch.io free CC0 retro packs
- URL: https://itch.io/game-assets/free/tag-cc0
- License: CC0 only
- Attribution: Per selected pack metadata

Rules for adding external assets:
- Add source URL, exact pack name, license, and attribution text in this file.
- Keep license files alongside imported assets inside `assets/`.
- Do not add copyrighted Kirby proprietary assets.
