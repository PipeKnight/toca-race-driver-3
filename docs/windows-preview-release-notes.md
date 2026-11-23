# TOCA Race Driver 3 Recompilation for Windows 11 x64

Version `0.1.0-preview.7` is a development preview for the North American PS2 disc `SLUS-21182` v1.02. Use a disc image from your own copy. The launcher compiles the original executable locally and reads the original disc at runtime. A PS2 BIOS and PCSX2 are unnecessary.

## Changes in this preview

- The DTM add-on can load an additional Mercedes variant with edited model meshes and the original Mercedes mechanics. Its default driver is QA Touring. The introductory race assigns it to the player, and it becomes selectable in DTM Free Race after the usual unlock.
- Build a new add-on directory with the updated `BuildDtmVariant.py` to see QA Touring in the selector. The `--dtm-mod PATH` option still supports the earlier introductory-only add-on and the stock mesh overlays.
- The optional circuit pack still supports Foundry Oval, Road America, and both A1-Ring layouts. It can be enabled at the same time as the DTM add-on.

Build the add-ons from your own files. [Additional DTM variant](https://github.com/PipeKnight/toca-race-driver-3/blob/main/docs/modding.md#test-an-additional-dtm-variant) · [Foundry Oval instructions](https://github.com/PipeKnight/toca-race-driver-3/blob/main/docs/modding.md#build-and-play-foundry-oval)

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

The clean setup checks use Windows Sandbox with software graphics. The DTM race checks use Direct3D 12 on an existing Windows 11 installation. The Free Race test used an isolated profile with the DTM event data assigned to an unlocked event. It selected QA Touring and started a 21-car field on Hockenheim GP and Oschersleben. General-purpose car import, extra Road America weather, and full-game desktop acceptance remain open. Stream-buffer warnings can still occur on Silverstone and UK Rally 3, and software graphics can cause audio underruns. [Windows verification and open acceptance items](https://github.com/PipeKnight/toca-race-driver-3/blob/main/docs/acceptance-checklist.md)
