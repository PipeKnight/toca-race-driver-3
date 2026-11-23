# TOCA Race Driver 3 Recompilation for Windows 11 x64

Version `0.1.0-preview.6` is a development preview for the North American PS2 disc `SLUS-21182` v1.02. Use a disc image from your own copy. The launcher compiles the original executable locally and reads the original disc at runtime. A PS2 BIOS and PCSX2 are unnecessary.

## Changes in this preview

- The optional circuit pack can include Foundry Oval in a fourth slot alongside Road America and the two A1-Ring layouts. Foundry Oval is a simple original circuit for testing authored PS2 track geometry, collision, routes, and saves.
- The existing `--road-america PATH` option opens earlier packs or the new four-course pack. Road America retains its dedicated Rain scene when the pack includes the Rain resources.

Build the add-ons from your own files. [Foundry Oval instructions](https://github.com/PipeKnight/toca-race-driver-3/blob/main/docs/modding.md#build-and-play-foundry-oval) · [DTM model guide](https://github.com/PipeKnight/toca-race-driver-3/blob/main/docs/ps2-dtm-models.md)

## First launch

Place `TocaRecomp.exe` in a writable folder. The executable bundles its setup files. Open PowerShell in that folder and pass the path to your ISO.

```powershell
.\TocaRecomp.exe --disc 'D:\Games\TOCA Race Driver 3.iso'
```

The first setup downloads and verifies a portable compiler and graphics dependencies, then builds the runner. Allow several minutes, an internet connection, and room for the setup and game data. The tested offline setup occupied about 2 GiB including dependency archives. Later launches reuse the local build. Keep the disc available for each launch. `--help` lists options for fullscreen, separate data and setup folders, and direct launch.

A matching DVD CHD or folder of extracted disc files can also launch a prepared build. The ISO has the clean first-run coverage for this preview. [Supported disc checksums and more about setup](https://github.com/PipeKnight/toca-race-driver-3/blob/main/docs/windows-preview.md)

## Saves and updates

The launcher folder holds the memory card `toca-slus-21182.ps2` and game settings unless you select another data folder with `--data-dir`. To upgrade from an earlier preview, replace `TocaRecomp.exe` after the game closes, or pass your previous data folder with `--data-dir`. Keep using your previous `--setup-dir` if you chose a separate one. Run once without `--direct` so the launcher can prepare any required files. Keep your memory card and settings before removing a portable installation.

## Verification scope

The Windows Sandbox setup checks use software graphics. The Direct3D 12 race checks use an existing Windows 11 installation. Road America finished a Free Race in 3:06.68 and restored a 2:47.56 Time Trial ghost after a restart. The DTM tests loaded edited stock meshes. General-purpose car import, extra Road America weather, and full-game desktop acceptance remain open. Stream-buffer warnings can still occur on Silverstone and UK Rally 3, and software graphics can cause audio underruns. [Windows verification and open acceptance items](https://github.com/PipeKnight/toca-race-driver-3/blob/main/docs/acceptance-checklist.md)
