# Windows preview launcher

The launcher packages the first-run setup for Windows 11 x64. Supply your own North American PS2 disc, `SLUS-21182` v1.02, as an ISO, a matching DVD CHD, or a directory of extracted disc files. Keep the disc available at launch. The launcher builds the runner locally and reads the original disc in place. The package includes the launcher, setup scripts, patches, and pinned upstream source archives.

## Build the package

From the project directory, run this in PowerShell on Windows.

```powershell
.\scripts\New-WindowsPreview.ps1
```

The default package directory is `build\windows-preview-x64`. Use `-Destination` to choose another directory and `-ArchiveCache` to choose where the build script keeps the two verified source archives. Copy the entire package directory to the test machine. `TocaRecomp.exe` is the entry point and `support` contains its setup files.

## Set up and run the game

From the package directory, run the launcher with the path to your disc.

```powershell
.\TocaRecomp.exe --disc 'D:\Games\TOCA Race Driver 3.iso'
```

The first launch fetches and verifies the portable compiler and graphics dependencies, extracts the boot ELF, builds the runner, and starts the game. It needs an internet connection until the dependencies have been cached. For an offline first setup, place the upstream dependency archives under `downloads` inside the setup directory. Use the filenames in [WindowsPreviewSources.psd1](../scripts/WindowsPreviewSources.psd1). The upstream setup verifies these archives against its pinned checksums.

After setup, the same command runs the local build. Use `--direct` to require an existing build, or `--setup-only` to prepare the build without starting the game. `--help` lists all switches. For example, this command stores game data and build files in separate directories and starts fullscreen.

```powershell
.\TocaRecomp.exe --disc 'D:\Games\TOCA Race Driver 3.iso' `
    --data-dir 'D:\TOCA\Player Data' --setup-dir 'D:\TOCA\Setup' --fullscreen
```

The data directory defaults to the launcher directory and holds `toca-slus-21182.ps2`, controller settings, runtime caches, and logs. The setup directory defaults to `setup` inside the data directory. After the game closes, preserve the memory card and settings before removing a portable copy. Be sure to include the separately selected data directory if you used `--data-dir`.

The launcher returns exit code `2` for an invalid argument or unsupported disc and `3` for an incomplete setup or a build failure. It passes through the game process exit code after launch.

## Verification

A clean offline Windows 11 Sandbox on build `26100.9606` started with the verified dependency archives and no prepared build. No compiler, CMake, Ninja, or Git was on the guest's initial `PATH`. The package ran from `C:\`, with separate setup and data paths containing spaces and brackets. It validated the ISO, compiled 224 build units, and ran the first 780 guest frames in 3 minutes and 44 seconds. The setup used 1.98 GiB, including the preseeded archives. The ISO stayed mounted read-only and setup created no duplicate image.

From the same guest, an offline `--direct --no-save` run reached 540 frames. Both a matching DVD CHD and extracted disc files reached 780 frames with the same runner. Its SHA-256 stayed unchanged. A short invalid ISO returned exit code `2` before creating a setup directory. `--direct` before setup returned `3` and left the setup directory absent.

The launcher ran fullscreen with an SDL virtual controller and created Player One on a fresh portable memory card. The card passed the filesystem and ECC check. A separate windowed runner process booted from the ISO and that card, confirmed the profile load, and reached the Oschersleben race. The card retained its SHA-256 and the second process reported zero card writes.

A separate clean Sandbox started from the package and original ISO with networking enabled, no preseeded archives, and the default portable paths. The launcher downloaded and verified the pinned dependencies, built the runner, and ran the first 780 guest frames in 6 minutes and 4 seconds. All setup and game data used the package directory even though the process started from `C:\`. A direct no-save launch reused the build for 540 frames. `--setup-only` validated the ready setup without starting the game.

The exact runner built in the guest also completed a 4,580-frame windowed profile-creation run on the Windows host with a GeForce RTX 4070, Direct3D 12, and scripted SDL input. WASAPI received 76.13 seconds of game audio with zero queue underruns or dropped samples. The Sandbox used software rendering and its longer profile run had underruns.

The same Direct3D 12 runner drove the recorded Silverstone National Clio Cup round from the grid to the finish. All 652 replay checkpoints matched. The game awarded tied second overall with 28 points. Its new autosave matched the reference card and passed the filesystem and ECC check. A cold boot restored both Tier 2 offers with zero card writes. Frames 4000–10500 averaged 58.68 fps during the concurrent online Sandbox setup. The race logged one WASAPI queue underrun with zero dropped samples. The distinct guest stream-buffer allocation and close warnings for slot 4 recurred at frames 4766 and 5739.

Clean desktop hardware rendering, sustained race audio, and physical input remain open. See the [Windows 11 acceptance checklist](acceptance-checklist.md#1-windows-11-end-to-end-test).

The offline and online setup logs, exit codes, and runner checksums are under `local/sandbox-qa/preview-verified/evidence/` and `local/sandbox-qa/preview-online/evidence/`. The full Silverstone trace, frame timings, card hashes, and captures are in `local/sandbox-qa/preview-verified/hardware-silverstone/`.
