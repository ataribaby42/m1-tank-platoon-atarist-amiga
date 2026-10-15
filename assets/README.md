# Original build inputs

Place the original disk images here before running a full build. These input images are ignored by Git; the finished modified images are tracked in `output`.

| Platform | Filename | Size (bytes) |
| --- | --- | --- |
| Amiga | `M1TankPlatoon.adf` | 901120 |
| Atari ST | `M1 Tank Platoon.st` | 737280 |

Supported original SHA-256 checksums:

```text
f713c20cb1f012fdce352924067783282814a3ec519515c4d7d939ed14d61275  M1TankPlatoon.adf
004347f9eedd028fbc1020f00464fbfb809fbffb0eeadbf7383ee3d1e0803c9c  M1 Tank Platoon.st
```

The Atari ST input may also contain a saved crew roster. Validation permits changes only to the existing `ROSTER.TNK` data and its modification timestamp; all other disk data must match the supported original. The saved roster is preserved in the output.

Use the original image for the selected platform. A modified image from `output` cannot be used as a build input. Building both platforms requires both originals.

See the [build instructions](../README.md#build-requirements) for Python dependencies and vasm setup.
