# Editable graphics

These PNGs are shared by the Amiga and Atari ST builds. Each pixel is one in-game pixel: keep the existing image dimensions and disable resizing, antialiasing and partial transparency.

| File | Size | Purpose |
| --- | --- | --- |
| `kokpit.png` | 320 × 200 | Enlarged gunner cockpit |
| `zamerovac_normal.png` | 103 × 38 | Normal reticle |
| `zamerovac_thermal.png` | 103 × 38 | Thermal reticle |
| `font_atlas.png` | 165 × 14 | Range digits and target-lock star |
| `smoke1_atlas.png` | 56 × 36 | Smoke 1 switch and indicator states |
| `paleta.png` | 16 × 1 | Exact fixed palette |
| `paleta_prehled.png` | Reference image | Numbered palette overview |

Use only the existing palette colors or fully transparent pixels. Keep the palette unchanged.

In `kokpit.png`, the 3D viewport from `(64, 10)` through `(257, 187)` inclusive and the entire bottom status area, rows `192–199`, must remain transparent.

The font atlas contains `0123456789*` from left to right. Each character occupies a **13 × 12** interior. The first interior starts at `(1, 1)`; subsequent characters start 15 pixels to the right.

The Smoke 1 atlas has state 0 on the left and state 1 on the right. Switch interiors are **26 × 20**, starting at `(1, 1)` and `(29, 1)`. Indicator interiors are **26 × 12**, starting at `(1, 23)` and `(29, 23)`.

Pink borders lie outside the atlas interiors and are excluded from the compiled graphics. Keep the field positions fixed and edit the interiors. Coordinates start at zero.

Run `build.bat` from the project root to rebuild both disk images after editing. The builders reject invalid dimensions, palette colors or transparency and do not overwrite these source PNGs.

See [CTI_ME.txt](CTI_ME.txt) for Czech editing instructions and placement coordinates. [rozmisteni.json](rozmisteni.json) records the editing layout; current compiled offsets and checksums are generated under `analysis/build`.
