# TOCA Race Driver 3 Recompilation for Windows 11 x64

Version `0.1.0-preview.1` is a development preview for the North American PS2 disc `SLUS-21182` v1.02. Use a disc image from your own copy. The launcher compiles the original executable locally and reads the original disc at runtime. A PS2 BIOS and PCSX2 are unnecessary.

## First launch

Extract the entire archive into a writable folder. Leave the `support` folder next to `TocaRecomp.exe`. Open PowerShell in that folder and pass the path to your ISO.

```powershell
.\TocaRecomp.exe --disc 'D:\Games\TOCA Race Driver 3.iso'
```

The first setup downloads and verifies a portable compiler and graphics dependencies, then builds the runner. Allow several minutes, an internet connection, and room for the setup and game data. The tested offline setup occupied about 2 GiB including dependency archives. Later launches reuse the local build. Keep the disc available for each launch. `--help` lists options for fullscreen, separate data and setup folders, and direct launch.

A matching DVD CHD or folder of extracted disc files can also launch a prepared build. The ISO has the clean first-run coverage for this preview. [Supported disc checksums and more about setup](https://github.com/PipeKnight/toca-race-driver-3/blob/main/docs/windows-preview.md)

## Saves and updates

The launcher folder holds the memory card `toca-slus-21182.ps2` and game settings unless you select another data folder with `--data-dir`. The card stores normal game progression. Keep it and your settings before removing a portable installation. After replacing the launcher and its support files, run once without `--direct` so the launcher can prepare the updated runner.

## Verification scope

Clean Windows Sandbox tests built the game from the ISO both online and offline. Recorded Windows 11 tests reached the finish and restored championship progress, including Silverstone National and UK Rally 3. The latest checkpoint fixes preserve the SPU2's buffered ADPCM end flags. Stream-buffer warnings can still occur on Silverstone and UK Rally 3, and software graphics can cause audio underruns. [Windows verification and open acceptance items](https://github.com/PipeKnight/toca-race-driver-3/blob/main/docs/acceptance-checklist.md)
