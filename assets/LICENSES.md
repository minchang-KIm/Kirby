# Asset Provenance Ledger

## Noto Sans KR

| Family/file | Upstream | Pinned revision | SHA-256 | License |
| --- | --- | --- | --- | --- |
| Noto Sans KR — `assets/fonts/NotoSansKR[wght].ttf` | [Google Fonts](https://github.com/google/fonts/tree/ec0464b978de222073645d6d3366f3fdf03376d8/ofl/notosanskr) | `ec0464b978de222073645d6d3366f3fdf03376d8` | `194018e6b2b293a7964f037b25c0249ce1418bc9ab3c971060a03aa57861e252` | SIL Open Font License 1.1 |
| Windsprig runtime subset — `assets/fonts/WindsprigSansKR.ttf` | Deterministic static 500-weight subset of the pinned Noto Sans KR source | `fonttools 4.63.0`; `tools/generate_font_subset.py` | `4211e2545aa28f0a9e6c72d61a9996663b3160f7b6ce54d6563e065543743f58` | SIL Open Font License 1.1 |
| Retained license — `assets/fonts/OFL-NotoSansKR.txt` | [Google Fonts OFL.txt](https://github.com/google/fonts/blob/ec0464b978de222073645d6d3366f3fdf03376d8/ofl/notosanskr/OFL.txt) | `ec0464b978de222073645d6d3366f3fdf03376d8` | `1c05c68c34f9708415aada51f17e1b0092d2cea709bf4a94cd38114f9e73d7d9` | SIL Open Font License 1.1 |

The pinned Noto Sans KR source is redistributed unmodified. The shipped runtime file is a deterministic static subset
covering printable ASCII, every modern precomposed Hangul syllable, and the bilingual release catalogs. Both are distributed under the
SIL Open Font License 1.1 retained at `assets/fonts/OFL-NotoSansKR.txt`.

## Original generated art

The 52 PNGs under `assets/generated/player`, `enemies`, `bosses`, `worlds`, and `ui` are original Windsprig project
art generated solely from checked-in geometric recipes and deterministic seeds in `tools/generate_art.py`. They use no
third-party character, logo, raster, or vector inputs. The canonical recipe IDs, dimensions, frame counts, seeds,
mandatory flags, and decoded-pixel SHA-256 hashes are recorded in `assets/generated/art-provenance.json`.

Original generated art is distributed under the project MIT license in `LICENSE`.

The Windows executable icon at `assets/branding/windsprig.ico` is a deterministic ICO container that embeds the
canonical original `assets/generated/ui/favicon.png` bytes without re-encoding. It is produced and checked by
`tools/generate_windows_icon.py` and is distributed under the same project MIT license.

## Original generated audio

The 57 WAV files under `assets/generated/audio` are original Windsprig project audio: 28 loopable music cues and 29
one-shot sound effects. They are synthesized solely from the checked-in composition, oscillator, envelope, and seeded
noise recipes in `tools/generate_audio.py`; no third-party samples, recordings, or AI-generated audio are used. The
canonical algorithm, seeds, parameters, PCM metadata, durations, themes, phase variants, and byte/decoded-PCM SHA-256
hashes are recorded in `assets/generated/audio-provenance.json`.

Original generated audio is distributed under the project MIT license in `LICENSE`.

## Repository-authored release content

The campaign, reward, ability, English, and Korean JSON documents are original repository-authored data distributed
under the project MIT license in `LICENSE`.
