# M1 Tank Platoon — Changelog

Consolidated record of the modifications completed through **2026-10-15**.
Earlier combined Amiga builds have been confirmed working by the user.

Final disk images: `output/M1TankPlatoon_modded.adf` and `output/M1TankPlatoon_modded.st`.

## Mi-24D support arrival — Amiga and Atari ST

- Fixed the original helicopter command check that rejected Mi-24D support calls because it accepted only the AH-64 identifier. Selected Mi-24 units can now leave the off-map holding state and enter the battlefield after the original arrival delay.
- Preserved mission selection, weather restrictions, support availability, random timing, aircraft statistics and weapons. This does not add a helicopter to every mission.
- Kept AH-64 and OH-58 command handling and arrivals unchanged. Enemy Mi-24 calls do not display friendly AH-64 radio messages.
- Added shared assembly source and automatic build checks for actual ground-unit-to-army-to-helicopter command propagation, all eight Mi-24 formation templates, all five simulation time steps, repeated orders during the countdown, unavailable helicopters and user-mode 68000/68020 execution.
- Verified 1,344 command/identifier/state combinations and 40 formation/time-step arrival cases per platform, plus friendly helicopter controls. These are instruction-level checks through map entry, not a complete visual mission playthrough.
- Added extended regression tests with 55,020 command/identifier/state combinations and 54 complete support cycles per platform. Movement, navigation, spatial allocation, departure, cooldown and repeat deployment match the original routines at every tested tick. AH-64, OH-58 and both attack-aircraft types are included as controls.
- Compared Mi-24 target acquisition, firing and projectile trajectories with the original routines at all five simulation time steps, and checked terminal damage, crashes and wrecks that cannot be recalled. These tests execute real instructions on a controlled flat battlefield; the original Mi-24 control bypasses only its broken call-in guard.
- Verified the current ST disk in an isolated Hatari 2.6.1 instance: normal and enlarged gunner views, a Mi-24 loaded by the real formation loader, its call-in and flight over the mission terrain, departure, cooldown and a second arrival. The test explicitly adds support to a training formation and submits normal call commands; it does not force the arrival state or shorten timers. No additional gameplay patch was required by this regression pass.
- Allowed Atari ST builds from the supported source disk after the game saves its crew roster. Only `ROSTER.TNK` contents and its modification timestamp are excluded from the source checksum; executable, boot and filesystem changes remain rejected. The saved roster is preserved in the output.

## Atari ST port

- Added a separate complete build for the supplied `assets/M1 Tank Platoon.st`, producing `output/M1TankPlatoon_modded.st`.
- Ported dark green enemy vehicle materials, the brown distant vehicle point, valid-range laser acquisition, moving/turning lead corrections, viewport-edge clipping fixes, and consistent gunner-style thermal colors. Enemy map markers retain their original colors.
- Ported Shift+F3 with the shared editable cockpit, reticles, distance font and Smoke 1 atlas. The enlarged scene renders at native pixel resolution, with the status line preserved and only Smoke 1 clickable.
- Added native Atari ST interleaved-word sprite rendering and separate cockpit caches for both screen buffers. Unchanged cockpit and Smoke graphics are not repainted every frame.
- Preserved the target when switching F3 to Shift+F3 or back, while retaining the original view-entry behavior from other views.
- Added FAT12 disk updating, TOS relocation handling, ST asset compilation and actual 68000 instruction regression tests. Shared gameplay patch sources remain common to the two platforms.
- Build with `python src/build_all.py --platform st` or `python src/build_st.py`; use `--platform all` to build both. The default command continues to build only the Amiga ADF.
- Builds read the original disk and current PNGs, preserve other disk files, and do not modify either the source disk, PNGs, or the other platform's output.
- Verified disk boot, a static gunnery mission, F3/Shift+F3 transitions, Smoke 1 and its status message, and commander/driver/gunner thermal selection in an isolated Hatari 2.6.1 instance configured as an 8 MHz Atari ST with 1 MB RAM and TOS 1.04.

## Loading and CPU compatibility

- Fixed the black screen and apparent freeze when entering a mission after the polygon-edge fix.
- Replaced a privileged status-register read in the clipping patch with condition-code saving that works in user mode on both the 68000 and later processors. The previous instruction caused a privilege exception on the 68020.
- Added regression checks for 68000, 68020 and 68040 user-mode execution, including an explicit check for the privileged instruction that the instruction-test emulator did not reliably reject.
- Reproduced the failure with the previous ADF and verified the corrected build in a separate, hidden WinUAE instance using a 68020/A1200 configuration.

## Consistent thermal colors

- Changed the commander's thermal binoculars and the driver's thermal view to use the original gunner thermal material table.
- Unified thermal terrain, object and sky colors across these views, including the enlarged gunner view.
- Preserved the normal day/night view selection, sensor switches and cockpit palette.
- Applied the change without adding rendering work or runtime memory.

## Polygon clipping and viewport edges

- Fixed an original-game clipping error that produced vertical slivers along the left and right edges of the 3D viewport.
- Closed clipped polygons at their actual viewport intersections instead of using the heights of vertices outside the window.
- Applied the correction to normal F3, Shift+F3 and the other 3D views.
- Handled polygons completely outside the viewport without leaving unwanted top or bottom rows.
- Cleared cached boundary information when an edge is rejected behind the camera, preventing data from a previous object from being reused.
- Preserved the original projection, line clipping, polygon fill and special horizon rendering.

## Gun lead while driving and turning

- Corrected the player's velocity contribution to a fired round. The projectile inherits the tank's full world velocity, with the simulation time step applied when the projectile moves.
- Removed the extra time-step scaling that caused large aiming errors while driving, especially when firing towards the sides of the tank.
- Changed angular lead to use the sight's change in world direction, preventing hull rotation from introducing false lead while holding a target.
- Preserved relative turret rotation for the turret motor sound.
- Applied the fixes to manual aiming and locked targets in both normal F3 and Shift+F3.
- Preserved the original stationary firing results against moving targets when the tank is not turning.
- Checked all five simulation time steps and transitions between them, including slow-update cases relevant to low-FPS systems.
- Left the original random shot dispersion, random-number generator, ammunition coefficients and ballistic tables unchanged.

## Laser rangefinder and target acquisition

- Fixed false target acquisition after an invalid laser measurement, which could make the sight jump and display a flashing `0` with a target-lock star, particularly near terrain edges.
- Restricted new laser target acquisition to valid measurements from **200 to 7998 metres**.
- Routed invalid measurements through the original unsuccessful-acquisition path, retaining manual aiming.
- Preserved flashing `0` as the indication of an invalid measurement.
- Preserved valid target acquisition and the original flashing distance display from **4000 to 7998 metres**.
- Applied the correction to normal F3 and Shift+F3 without changing terrain intersection calculations or ballistics.

## Enlarged gunner view — Shift+F3

- Added an enlarged gunner cockpit view activated with **Shift+F3**.
- Rendered the 3D scene directly at native **1:1 pixel resolution** in the larger viewport, replacing the initial scaled-up 3D image. The view retains the normal F3 camera framing.
- Added a separate enlarged cockpit bitmap, normal and thermal reticles, range digits and target-lock star.
- Kept the bottom status-message area available; rows 192–199 remain reserved for it.
- Kept **Smoke 1** as the only interactive cockpit control in the enlarged view, with its switch and indicator reflecting the actual smoke state.
- Disabled clicks on the other enlarged cockpit controls.
- Preserved normal gunner gameplay and continuous 3D rendering.
- Fixed AI gunner retargeting in both directions when switching **F3 ↔ Shift+F3**. Switching between these two views keeps the current target and aim.
- Preserved normal F3 entry behavior when Shift+F3 is selected from a different station or view.
- Restored the regular cockpit and current instrument states when leaving the enlarged view.

## Enlarged-view rendering performance

- Cached the cockpit separately for each of the two display buffers, drawing it on entry or refresh instead of every frame.
- Redrew the Smoke 1 switch and indicator only when their state changes or the relevant buffer needs initialization.
- Skipped hidden instrument rendering, including the tank/turret orientation indicators, while the enlarged view is active.
- Kept the 3D scene, status messages and game logic updating normally.
- Converted the enlarged reticle and font to sparse planar drawing blocks at build time, preserving transparency and the original runtime text-color behavior.

## Enemy colors and distant markers

- Recolored the originally red enemy ground-vehicle model materials to dark green, retaining the models' shading and detail levels.
- Used separate material IDs so the recoloring does not alter the global palette, cockpit graphics or unrelated models.
- Changed the distant enemy-vehicle point to brown, using palette entry **06** (`#AA5500`) in the normal color views.
- Kept enemy markers on the tactical map **red**.
- Retained the sensor-specific appearance of distant markers and models rather than forcing normal-view brown/green colors into thermal views.
- Left aircraft, helicopters and infantry that already used gray materials in their original colors; the vehicle recoloring does not make every enemy model green.

## Editable graphics

- Moved all editable PNG assets to the root-level `gfx` directory.
- Made the enlarged cockpit, reticles, range font and Smoke 1 states actual build inputs, so edited PNGs are included when rebuilding the ADF.
- Supplied the editable graphics at their final **1:1 game-pixel size**.
- Added `kokpit.png` at 320 × 200 pixels and separate normal/thermal reticles at 103 × 38 pixels.
- Consolidated the range digits and star into `font_atlas.png`, with marked outer cell borders; individual character PNGs are no longer used.
- Consolidated both switch states and both indicator states into `smoke1_atlas.png`; individual Smoke 1 state PNGs are no longer used.
- Excluded atlas border annotations from the compiled game graphics.
- Exported the exact palette as `paleta.png`, with a separate numbered overview in `paleta_prehled.png`.
- Added asset dimensions, placement and editing instructions in `gfx/CTI_ME.txt` and `gfx/rozmisteni.json`.
- Added validation of dimensions, palette colors, transparency and the clear areas required for the viewport and status line. Builds do not overwrite the source PNGs.

## Repeatable builds and output organization

- Added a root-level Windows `build.bat` wrapper that builds both platforms by default, accepts `--platform amiga` or `--platform st`, uses a local virtual environment when available, and propagates build errors.
- Added English project, input-disk and graphics documentation, Git ignore/line-ending rules, and GitHub Actions checks for Python syntax and both graphics formats. Final disks and release packages are included; original inputs, local tools and working data are excluded from Git.
- Verified installation of pinned dependencies and both complete builds in a clean project copy, including a path containing spaces and invocation from another directory. Both rebuilt disks matched the existing outputs and release package byte for byte.
- Added maintained Python builders and assembly patch sources under `src` for the vehicle colors, enlarged view, graphics conversion, lead, clipping and thermal changes.
- Added `python src/build_all.py` as the complete build entry point, rebuilding from the original ADF and current PNG assets.
- Kept `python src/build_dark_green.py` and `python src/build_zoom_f3.py` as compatible entry points to the same complete build.
- Added `python src/build_assets.py` for graphics conversion without publishing an ADF.
- Standardized the sole final output as **`output/M1TankPlatoon_modded.adf`**, containing the full set of fixes and changes.
- Stopped publishing separate `M1TankPlatoon_DarkGreen.adf` and `M1TankPlatoon_DarkGreen_ZoomF3.adf` variants.
- Kept intermediate executables, compiled graphics, test disks, reports and diagnostic images in `analysis`, with build intermediates in `analysis/build`.
- Preserved the original source disk, boot blocks, unrelated game files and their metadata.
- Added verified publication of the final disk after automated checks pass, retaining the previous output when a build fails.
- Added clean-input rebuild checks, checks that atlas edits reach the ADF, and checks that invalid PNGs cannot replace a successful output.

## Verification and development tools

- Added execution tests for the original and patched game instructions, including lead, laser acquisition, view transitions, Smoke 1, cockpit drawing, clipping and thermal material selection.
- Added geometry comparisons and native planar-rendering tests for viewport-edge artifacts, horizon rendering and rejected-edge reuse.
- Added low-FPS/time-step tests and a read-only comparison of the game's original random projectile dispersion.
- Added an enlarged-view rendering-overhead benchmark. Its instruction and memory-access counts are not measurements of the full game's FPS.
- Added model/LOD inspection tools and generated previews of enemy units and their detail levels using the game's model data and updated material colors.
- Recorded background-only emulator testing in `AGENTS.md`: use an isolated hidden instance without taking keyboard/mouse focus or interfering with the user's instance.
- Used process-ID-checked WinUAE IPC for test input, memory inspection and display captures.
- Verified the combined ADF before the Mi-24 fix through a fresh WinUAE boot, mission loading, normal F3, Shift+F3, return to F3, gunner thermal mode, the other crew views and the tactical map. The user subsequently confirmed that the game works.

The low-FPS tests exercise simulation timing and projectile calculations; they do not constitute a complete mission playthrough on an A500. The latest live WinUAE check covers startup and view/sensor switching, not completion of an entire mission.
