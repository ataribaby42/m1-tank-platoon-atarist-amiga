# M1 Tank Platoon — Amiga & Atari ST mod

Gameplay fixes and an enlarged gunner sight for the Amiga and Atari ST versions of **M1 Tank Platoon**. Both versions share the editable graphics and the gameplay patch sources.

## Ready-to-use images

- [Amiga ADF](output/M1TankPlatoon_modded.adf)
- [Atari ST disk image](output/M1TankPlatoon_modded.st)
- [ZIP package with both versions and a changelog](release/M1TankPlatoon_modded.zip)

The `output` and `release` directories are included in the repository. The ZIP is a packaged release; rebuilding a disk does not automatically update the ZIP.

## Changes

- **Dark green enemy ground vehicles**, with their shading and detail levels preserved. Distant enemy vehicle points are brown; enemy map markers remain red. Originally gray aircraft, helicopters and infantry retain their colors.
- **Shift+F3 enlarged gunner sight**, with the same framing as F3, native 1:1 rendering, larger reticles, range digits and target-lock star, and room for status messages.
- **Working Smoke 1 switch and indicator** in the enlarged cockpit. Other controls in that cockpit are inactive.
- **Target preservation** when switching between F3 and Shift+F3.
- **Reduced cockpit drawing overhead** through caching and skipping hidden instruments.
- **Laser acquisition fix** preventing a false target lock and sight jump after an invalid range measurement.
- **Lead corrections while driving and turning**, preserving stationary tracking, random shot dispersion and the original ballistic tables.
- **Polygon clipping fix** for vertical artifacts at viewport edges, including ordinary 3D views.
- **Consistent thermal colors** across the driver's view, commander's binoculars and gunner's sight.
- **Mi-24D support arrival fix** on both platforms. Selected helicopters can enter the battlefield after the original delay; support selection and availability are unchanged.

See the [full changelog](changelog.md) for implementation details and verification scope.

## Build requirements

The full build is verified with **Python 3.13** and **vasm 1.9a** (Motorola syntax, `vasmm68k_mot`). Python dependencies are pinned in [src/requirements.txt](src/requirements.txt).

1. Place the supported original game images in `assets`:
   - `assets/M1TankPlatoon.adf` for Amiga.
   - `assets/M1 Tank Platoon.st` for Atari ST.
2. Install vasm as `.tools/vasmm68k_mot.exe` on Windows, `.tools/vasmm68k_mot` on other systems, or put `vasmm68k_mot` on `PATH`.
3. Install the Python dependencies as shown below.

Original source disks and local tools are excluded from Git. Exact disk sizes and checksums are documented in [assets/README.md](assets/README.md). A full rebuild needs the original input for each selected platform; the modded output is not a substitute.

### Windows

Run in a terminal from the project directory:

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r src\requirements.txt
build.bat
```

In PowerShell, use `.\build.bat`. The wrapper prefers `.venv\Scripts\python.exe` when present and otherwise uses `python` from `PATH`. It can also be invoked by its full path from another directory. With no arguments it builds both platforms; `--platform` selects a single one:

```bat
build.bat
build.bat --platform amiga
build.bat --platform st
build.bat --help
```

The wrapper returns a nonzero exit code if the build fails. It does not install dependencies or launch an emulator.

### Direct Python commands

With dependencies installed in the active Python environment:

```sh
python -m pip install -r src/requirements.txt
python src/build_all.py                  # Amiga
python src/build_all.py --platform st    # Atari ST
python src/build_all.py --platform all   # Both
```

On Linux/macOS, a virtual environment can be created with `python3 -m venv .venv` and activated with `source .venv/bin/activate`. Supply a native vasm executable. Full builds have been verified on Windows; the asset checks also run in the Linux CI configuration.

Do not use Python's `-O` or `-OO` options: verification relies on assertions. A build compiles the PNGs, applies the complete patch set, executes regression checks and then replaces the selected platform's final disk. Failed checks leave that platform's previous output intact. When building both platforms, publication happens separately for each one.

| Platform | Final output | Intermediate files and reports |
| --- | --- | --- |
| Amiga | `output/M1TankPlatoon_modded.adf` | `analysis/build/` |
| Atari ST | `output/M1TankPlatoon_modded.st` | `analysis/build/st/` |

Each platform build leaves the other platform's disk untouched. Source disks and editable PNGs are preserved. No previous build or emulator memory dump is required.

## Editing the graphics

Edit the PNGs in [gfx](gfx/README.md) at their existing **1:1 pixel size**. The cockpit, normal and thermal reticles, range font atlas and Smoke 1 atlas are shared by both platforms. Use the fixed palette, preserve the atlas layout and keep the viewport/status areas transparent.

After editing, run `build.bat` on Windows or `python src/build_all.py --platform all` to rebuild both versions. To compile only the graphics:

```sh
python src/build_assets.py
python src/build_st_assets.py
```

These commands write intermediate data under `analysis/build`; they do not publish disk images or change the source PNGs.

## Verification

Full builds include instruction-level regression checks for view transitions, drawing, Smoke 1, laser acquisition, lead, clipping, thermal colors and helicopter call-in behavior, plus disk integrity checks.

Additional checks, after building both platforms:

```sh
python src/test_mi24_lifecycle.py
python src/test_lead_low_fps.py
python src/test_st_source.py
python src/test_build_pipeline.py
```

The lifecycle test compares support movement, departure, cooldown, repeat arrivals, combat routines and crash states with the original code. The pipeline test rebuilds Amiga from clean inputs and checks edited/invalid graphics. These tests use copies and CPU instruction emulation, without opening an emulator window. Reports remain under `analysis`.

The [GitHub Actions workflow](.github/workflows/checks.yml) checks Python syntax, graphics validation and graphics compilation on Windows and Linux. It needs neither original disks nor vasm and does not build or publish disk images. Its actions are configured using the official [checkout](https://github.com/actions/checkout) and [setup-python](https://github.com/actions/setup-python) documentation.

For detailed commands in Czech, see [src/CTI_ME.txt](src/CTI_ME.txt). The changelog distinguishes automated instruction tests from live emulator verification; these checks do not represent a complete campaign playthrough.

## Project layout

| Path | Contents |
| --- | --- |
| `src/` | Maintained Python builders, assembly patches and regression tests |
| `gfx/` | Editable PNGs, atlases, palette and layout information |
| `assets/` | Local original game images; the README is tracked |
| `output/` | Final ADF and ST disk images, tracked in Git |
| `release/` | Packaged releases, tracked in Git |
| `analysis/` | Local diagnostics, previews, reports and intermediate builds; ignored |
| `.tools/` | Local assembler, dependencies and emulator tools; ignored |
| `build.bat` | Windows entry point; builds both platforms by default |

Keep new implementation work in `src` and editable graphics in `gfx`. Development instructions, including background-only emulator testing, are in [AGENTS.md](AGENTS.md).
