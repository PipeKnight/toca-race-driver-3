# TOCA Race Driver 3 Recompilation for Windows 11 x64

Version `0.1.0-preview.8` is a development preview for the North American PS2 disc `SLUS-21182` v1.02. Use a disc image from your own copy. The launcher compiles the original executable locally and reads the original disc at runtime. A PS2 BIOS and PCSX2 are unnecessary.

## Changes in this preview

- The optional circuit pack supports authored Tsukuba alongside Foundry Oval, Road America, and both A1-Ring layouts. The Clio Cup track selector can display generated circuit outlines. Tsukuba's revised pit route and sixteen stalls classified all 20 cars in a five-lap race with a mandatory stop.
- The Race Driver 2 circuit importer rebuilds the pit driving line, stall markers, and distances. It audits collisions across the pit route and supports standalone layouts. A1-Ring Short and Adelaide completed player pit service in Windows tests.
- The DTM add-on supports the experimental Aston Martin DB5 converted from Race Driver 2. Its pack offers a donor cockpit and sound options, and the runner supports its forward and rear-facing bonnet positions. The other RD2 vehicle conversions remain development tools.

Build the add-ons locally with the scripts from this release and your own copies of the two games. [Tsukuba and track authoring](https://github.com/PipeKnight/toca-race-driver-3/blob/v0.1.0-preview.8/docs/author-a-circuit.md) · [Race Driver 2 circuit and DB5 conversion](https://github.com/PipeKnight/toca-race-driver-3/blob/v0.1.0-preview.8/docs/race-driver-2-import.md)

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

Clean setup uses Windows Sandbox with software graphics. Race and mod validation uses Direct3D 12 on an existing Windows 11 installation. Stock windshields can appear brighter than the PCSX2 reference. Mandatory stops across the entire imported circuit set, mirror reflections on the DB5, general-purpose car import, and full-game desktop acceptance remain open. Stream-buffer warnings can still occur on Silverstone and UK Rally 3, and software graphics can cause audio underruns. [Verification and open acceptance items](https://github.com/PipeKnight/toca-race-driver-3/blob/v0.1.0-preview.8/docs/acceptance-checklist.md)
