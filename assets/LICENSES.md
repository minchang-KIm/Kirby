# Asset Provenance Ledger

## Noto Sans KR

| Family/file | Upstream | Pinned revision | SHA-256 | License |
| --- | --- | --- | --- | --- |
| Noto Sans KR — `assets/fonts/NotoSansKR[wght].ttf` | [Google Fonts](https://github.com/google/fonts/tree/ec0464b978de222073645d6d3366f3fdf03376d8/ofl/notosanskr) | `ec0464b978de222073645d6d3366f3fdf03376d8` | `194018e6b2b293a7964f037b25c0249ce1418bc9ab3c971060a03aa57861e252` | SIL Open Font License 1.1 |
| Windsprig runtime subset — `assets/fonts/WindsprigSansKR.ttf` | Deterministic static 500-weight subset of the pinned Noto Sans KR source | `fonttools 4.63.0`; `tools/generate_font_subset.py` | `12a7caf5a82170940ea1dd73112e70ea353edf0a0230621268593fb30ef98a53` | SIL Open Font License 1.1 |
| Retained license — `assets/fonts/OFL-NotoSansKR.txt` | [Google Fonts OFL.txt](https://github.com/google/fonts/blob/ec0464b978de222073645d6d3366f3fdf03376d8/ofl/notosanskr/OFL.txt) | `ec0464b978de222073645d6d3366f3fdf03376d8` | `1c05c68c34f9708415aada51f17e1b0092d2cea709bf4a94cd38114f9e73d7d9` | SIL Open Font License 1.1 |

The pinned Noto Sans KR source is redistributed unmodified. The shipped runtime file is a deterministic static subset
covering printable ASCII and every glyph in the bilingual release catalogs. Both are distributed under the
SIL Open Font License 1.1 retained at `assets/fonts/OFL-NotoSansKR.txt`.

## Original generated art

The 52 PNGs under `assets/generated/player`, `enemies`, `bosses`, `worlds`, and `ui` are original Windsprig project
art generated solely from checked-in geometric recipes and deterministic seeds in `tools/generate_art.py`. They use no
third-party character, logo, raster, or vector inputs. The canonical recipe IDs, dimensions, frame counts, seeds,
mandatory flags, and decoded-pixel SHA-256 hashes are recorded in `assets/generated/art-provenance.json`.

Original generated art is distributed under the project MIT license in `LICENSE`.

## Original generated audio provenance — reserved for Task 8

Task 5 does not distribute generated audio. Task 8 will record each committed synthesis/composition recipe and decoded
PCM hash in `assets/generated/audio-provenance.json` when those assets exist.

## Repository-authored release content

The campaign, reward, ability, English, and Korean JSON documents are original repository-authored data distributed
under the project MIT license in `LICENSE`.
