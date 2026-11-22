# Windows preview launcher

The launcher packages the first-run setup for Windows 11 x64. Supply your own North American PS2 disc, `SLUS-21182` v1.02, as an ISO, a matching DVD CHD, or a directory of extracted disc files. Keep the disc available at launch. The launcher builds the runner locally and reads the original disc in place. The package includes the launcher, setup scripts, patches, and pinned upstream source archives.

## Build the package

From the project directory, run this in PowerShell on Windows.

```powershell
.\scripts\New-WindowsPreview.ps1
```

The default package directory is `build\windows-preview-x64`. Use `-Destination` to choose another directory and `-ArchiveCache` to choose where the build script keeps the two verified source archives. Use `-ArchivePath` to also create a ZIP containing the launcher, release notes, and the files listed in the package manifest. Copy the entire package directory to the test machine or extract the ZIP there. `TocaRecomp.exe` is the entry point and `support` contains its setup files.

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

After updating the launcher package, run once without `--direct` to prepare the updated runtime. The [version 11 checkpoint format](native-recompilation.md#preserve-buffered-adpcm-end-flags-in-version-11-checkpoints) retains additional SPU2 state. To resume normal game progress, open the profile on the portable memory card.

The launcher returns exit code `2` for an invalid argument or unsupported disc and `3` for an incomplete setup or a build failure. It passes through the game process exit code after launch.

## Clean desktop release test

Use a clean Windows 11 x64 installation with a working graphics driver, a physical keyboard, and an SDL-supported controller. Use the candidate ZIP and your own [reference disc](ps2-disc-and-archives.md#reference-disc). Run from a fresh writable directory with the default portable setup and data paths. Record the archive SHA-256, launcher version, Windows build, GPU and driver, and controller model.

1. With the keyboard, boot the candidate, navigate the menus, create a profile, and enable autosave. Verify the keyboard can steer, accelerate, and brake. Check the on-screen controls or the portable `keys.ini` for the key bindings.
2. With the physical controller, start an event such as the first World Sprintcar Series round in Pro Career. Drive the full race from the grid, confirm Race Results, and continue until the game writes its autosave. Note any audible interruptions. The runtime log records the active graphics adapter, audio queue underruns, and card writes.
3. Exit normally, then start the same package with `--direct --fullscreen`. Load the profile and check the race result or next round. Switch to windowed mode and exit normally again. Record the card SHA-256 after the race and after reloading. Save the runtime logs and results screen locally with the report.

For input diagnostics, set `PS2_PAD_LOG=1` in the PowerShell session before launching. Keep the memory card and logs private when reporting a result. The report can include the hashes, device models, and relevant log lines without sharing the ISO or card image.

## Verification

A clean offline Windows 11 Sandbox on build `26100.9606` started with the verified dependency archives and no prepared build. No compiler, CMake, Ninja, or Git was on the guest's initial `PATH`. The package ran from `C:\`, with separate setup and data paths containing spaces and brackets. It validated the ISO, compiled 224 build units, and ran the first 780 guest frames in 3 minutes and 44 seconds. The setup used 1.98 GiB, including the preseeded archives. The ISO stayed mounted read-only and setup created no duplicate image.

From the same guest, an offline `--direct --no-save` run reached 540 frames. Both a matching DVD CHD and extracted disc files reached 780 frames with the same runner. Its SHA-256 stayed unchanged. A short invalid ISO returned exit code `2` before creating a setup directory. `--direct` before setup returned `3` and left the setup directory absent.

The launcher ran fullscreen with an SDL virtual controller and created Player One on a fresh portable memory card. The card passed the filesystem and ECC check. A separate windowed runner process booted from the ISO and that card, confirmed the profile load, and reached the Oschersleben race. The card retained its SHA-256 and the second process reported zero card writes.

A separate clean Sandbox started from the package and original ISO with networking enabled, no preseeded archives, and the default portable paths. The launcher downloaded and verified the pinned dependencies, built the runner, and ran the first 780 guest frames in 6 minutes and 4 seconds. All setup and game data used the package directory even though the process started from `C:\`. A direct no-save launch reused the build for 540 frames. `--setup-only` validated the ready setup without starting the game.

The exact runner built in the guest also completed a 4,580-frame windowed profile-creation run on the Windows host with a GeForce RTX 4070, Direct3D 12, and scripted SDL input. WASAPI received 76.13 seconds of game audio with zero queue underruns or dropped samples. The Sandbox used software rendering and its longer profile run had underruns.

The same Direct3D 12 runner drove the recorded Silverstone National Clio Cup round from the grid to the finish. All 652 replay checkpoints matched. The game awarded tied second overall with 28 points. Its new autosave matched the reference card and passed the filesystem and ECC check. A cold boot restored both Tier 2 offers with zero card writes. Frames 4000–10500 averaged 58.68 fps during the concurrent online Sandbox setup. The race logged one WASAPI queue underrun with zero dropped samples. The distinct guest stream-buffer allocation and close warnings for slot 4 recurred at frames 4766 and 5739.

Clean desktop hardware rendering, sustained race audio, and physical input remain open. See the [Windows 11 acceptance checklist](acceptance-checklist.md#1-windows-11-end-to-end-test).

The offline and online setup logs, exit codes, and runner checksums are under `local/sandbox-qa/preview-verified/evidence/` and `local/sandbox-qa/preview-online/evidence/`. The full Silverstone trace, frame timings, card hashes, and captures are in `local/sandbox-qa/preview-verified/hardware-silverstone/`.

### Versioned preview candidate

The `0.1.0-preview.1` ZIP was checked entry by entry against its build directory. The archive builder also passed an allowlist check with an unrelated test file in the build directory and rejected a request to replace an existing archive.

Installing inside a Git checkout exposed a case where Git skipped patches and returned success. The launcher now isolates patch application from an enclosing Git repository and uses a new setup revision to select the prepared backend. A rebuild inside the same checkout verified version 11 checkpoint support, passed all 21 SPU2 checks, and read the ISO in place. The host RTX 4070 reached 780 frames through Direct3D 12 with zero audio queue underruns or dropped samples.

The corrected candidate archive has SHA-256 `ff8ed1d713c637608ce5c8fbae446ffe84fb88b4536f45d55022e8e9a163a6a2`. A clean Windows Sandbox extracted that exact archive, installed it from verified offline dependencies, and ran the first 780 frames with software graphics. A direct no-save relaunch reused the same runner for 540 frames. The guest passed all 21 SPU2 checks.

The runner built from that archive on the current Windows host completed the scripted Silverstone National Clio Cup round through Direct3D 12 on the RTX 4070. It matched all 652 replay checkpoints and reached tied second overall with 28 points. The autosave matched the original reference card and passed filesystem and ECC checks. A cold launch restored both Tier 2 offers and preserved the card SHA-256. Across frames 4000–10500 the race averaged 59.38 fps with a 17.54 ms 95th-percentile interval. It had 19 WASAPI queue underruns and zero dropped samples. The log reported 18 of the underruns by frame 3012 during initial live compilation. The two known guest stream-buffer warnings remained.

The Windows 11 vGPU guest reached its desktop and enumerated the RTX 4070, Intel UHD 770, and a Remote Desktop keyboard. The initial candidate built successfully from the original ISO. At startup the guest session stopped during graphics initialization, before the runner logged an active Direct3D 12 adapter or rendered a frame. A separate `D3D12CreateDevice` call for the default adapter in the guest's system session succeeded. A later guest prepared for the low-power FXC probe reached the system session without reaching interactive logon during the test. The physical controller test still requires an accessible device on an interactive clean Windows installation.

Candidate evidence is under `local/release-preview-qa/`.
