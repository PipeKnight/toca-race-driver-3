# Windows preview launcher

The launcher packages the first-run setup for Windows 11 x64. Supply your own North American PS2 disc, `SLUS-21182` v1.02, as an ISO, a matching DVD CHD, or a directory of extracted disc files. Keep the disc available at launch. The launcher builds the runner locally and reads the original disc in place. The package includes the launcher, setup scripts, patches, and pinned upstream source archives.

The current Windows release, `v0.1.0-preview.2`, ships as a single portable `TocaRecomp.exe`. It loads the previous preview's saves and settings. Clean installation was verified in Windows Sandbox with software graphics. Full races on Direct3D 12 used an existing Windows installation. [Windows x64 release](https://github.com/PipeKnight/toca-race-driver-3/releases/tag/v0.1.0-preview.2)

The earlier `0.1.0-preview.1` archive requires its `support` directory next to `TocaRecomp.exe`. [Previous Windows release](https://github.com/PipeKnight/toca-race-driver-3/releases/tag/v0.1.0-preview.1)

## Build the package

From the project directory, run this in PowerShell on Windows.

```powershell
.\scripts\New-WindowsPreview.ps1
```

The default output is `build\windows-preview-x64\TocaRecomp.exe`. Use `-Destination` to choose another directory and `-ArchiveCache` to choose where the build script keeps the two verified source archives. Copy `TocaRecomp.exe` to the test machine. It includes the setup scripts, patches, upstream source archives, license notice, and release notes.

## Set up and run the game

From the package directory, run the launcher with the path to your disc.

```powershell
.\TocaRecomp.exe --disc 'D:\Games\TOCA Race Driver 3.iso'
```

The first launch fetches and verifies the portable compiler and graphics dependencies, extracts the boot ELF, builds the runner, and starts the game. It needs an internet connection until the dependencies have been cached. For an offline first setup, place the upstream dependency archives under `downloads` inside the setup directory. Use the filenames in [WindowsPreviewSources.psd1](../scripts/WindowsPreviewSources.psd1). The upstream setup verifies these archives against its pinned checksums.

Use a setup directory without square brackets for an offline first launch. The bundled checksum tool could not open a dependency archive under a setup path containing brackets. The verified configuration used a separate data directory with brackets and a setup directory with spaces.

A local probe reproduced the failure with both BusyBox `sha256sum` and CMake. For the directory containing brackets, both native programs received the `/c/...` path from MinGit and reported it missing. Bash could read the same file and compute its hash through standard input. Both native tools succeeded when given an explicit Windows path with a drive letter. The full offline build still needs that conversion at the affected tool calls.

After setup, the same command runs the local build. Use `--direct` to require an existing build, or `--setup-only` to prepare the build without starting the game. `--help` lists all switches. For example, this command stores game data and build files in separate directories and starts fullscreen.

```powershell
.\TocaRecomp.exe --disc 'D:\Games\TOCA Race Driver 3.iso' `
    --data-dir 'D:\TOCA\Player Data' --setup-dir 'D:\TOCA\Setup' --fullscreen
```

The data directory defaults to the launcher directory and holds `toca-slus-21182.ps2`, controller settings, runtime caches, and logs. The launcher writes its bundled support files to a build-specific directory under `.launcher` in the data directory. The setup directory defaults to `setup` inside the data directory. After the game closes, preserve the memory card and settings before removing a portable copy. Be sure to include the separately selected data directory if you used `--data-dir`.

To upgrade from `0.1.0-preview.1`, close the game and replace `TocaRecomp.exe` in the previous launcher folder. To keep the new executable elsewhere, pass the previous data directory with `--data-dir`. If you chose a separate setup directory, keep passing its path with `--setup-dir`. Run once without `--direct` to prepare any required files. To resume normal game progress, open the existing profile on the portable memory card.

The launcher returns exit code `2` for an invalid argument or unsupported disc and `3` for an incomplete setup or a build failure. It passes through the game process exit code after launch.

## Clean desktop release test

Use a clean Windows 11 x64 installation with a working graphics driver, a physical keyboard, and an SDL-supported controller. Use the candidate executable and your own [reference disc](ps2-disc-and-archives.md#reference-disc). Run from a fresh writable directory with the default portable setup and data paths. Record the executable SHA-256, launcher version, Windows build, GPU and driver, and controller model.

1. With the keyboard, boot the candidate, navigate the menus, create a profile, and enable autosave. Verify the keyboard can steer, accelerate, and brake. Check the on-screen controls or the portable `keys.ini` for the key bindings.
2. With the physical controller, start an event such as the first World Sprintcar Series round in Pro Career. Drive the full race from the grid, confirm Race Results, and continue until the game writes its autosave. Note any audible interruptions. The runtime log records the active graphics adapter, audio queue underruns, and card writes.
3. Exit normally, then start the same package with `--direct --fullscreen`. Load the profile and check the race result or next round. Switch to windowed mode and exit normally again. Record the card SHA-256 after the race and after reloading. Save the runtime logs and results screen locally with the report.

For input diagnostics, set `PS2_PAD_LOG=1` in the PowerShell session before launching. Keep the memory card and logs private when reporting a result. The report can include the hashes, device models, and relevant log lines without sharing the ISO or card image.

### Check a physical controller on an existing Windows installation

Connect the controller before launching. Use a fresh data directory to test profile creation and autosave independently of your regular profile. A prepared setup can be reused through `--setup-dir`. Start in windowed mode and confirm the controller moves the menu selection, accepts a choice, and controls steering, throttle, and brake in a race. On the default Xbox mapping, A is Cross, X is Square, and the left stick steers. Check the in-game controls if you changed the driving bindings.

Finish an event, wait for autosave, and close the game. Use `--direct --fullscreen` with the same data and setup directories to confirm that the profile and progress load. The data directory contains `logs/ps2run_*.log`. With `PS2_PAD_LOG=1`, the log records the controller name and input transitions for the guest ports. This run provides physical input and driver coverage on the existing installation. The clean desktop release test uses the full combination in a fresh installation.

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

#### Silverstone audio retest

The same runner repeated frames 2910–12700 using the same grid checkpoint, recorded input, and card copies in normal windowed Direct3D 12 mode. No Sandbox build was running. One pass started with empty live compilation caches. The other reused the first pass's EE and VU1 caches. Both matched all 652 replay checkpoints, preserved the grid cards, and averaged 60.00 fps at frames 4000–10500 with a 16.71 ms 95th-percentile frame interval.

The cold-cache pass logged zero WASAPI queue underruns. The warm-cache pass logged one at frame 11247, which took 334.94 ms and produced about 0.22 seconds of output silence. Neither pass dropped samples. Both chip captures contained 7,832,000 identical stereo sample frames at 48 kHz and recorded the slot 4 allocation and close warnings at frames 4766 and 5739. The PCM payload SHA-256 was `6984222c6dd3f8e7527966f29ef52f65caa174443705588c544a5e1a0c36dbef`. These runs locate the single output interruption separately from the repeatable guest warnings. The cause of the warm-cache stall and audio mix parity remain open. Traces and captures are under `local/release-preview-qa/isolated-audio/`.

#### Portable player data and normal exit

A fresh extraction of the candidate ZIP used an existing prepared setup and a separate portable directory containing copies of a completed Clio Cup card and `keys.ini`. `--setup-only` preserved both file hashes. Two launches from another working directory reused the setup with `--direct`, first in windowed mode and then fullscreen. Each used the RTX 4070 through Direct3D 12, took SDL virtual controller input, and performed 341 page reads without writing the memory card. Both runs closed through the normal Windows close request and the launcher returned exit code zero. The card and settings hashes stayed unchanged, and neither run logged a WASAPI underrun or a dropped sample. See `local/release-preview-qa/launcher-lifecycle/`.

#### Physical controller test on the existing Windows installation

The published `v0.1.0-preview.1` ran on Windows 11 25H2 build `26220.9606` using the GeForce RTX 4070 on Direct3D 12 with driver `32.0.16.2101`. SDL detected the physical **8BitDo Pro 2 Wired Controller** on port 1. The windowed run received menu and driving input, created a profile, and wrote its card. The first manual drive ended with terminal damage. The game exited normally and the card passed its filesystem and ECC check. This run logged two WASAPI underruns totaling about 2.13 seconds, with zero dropped samples.

The same package reopened the card in fullscreen. The player won the first **World Sprintcar Series** round with the physical controller. The game wrote the autosave and closed normally. WASAPI received 182.25 seconds of audio with zero underruns or dropped samples in this session. After a cold launch from a copy of the saved card, the profile loaded, **Dirt Raceway 2 · Sunny** resumed, and Championship Standings showed **Player One** first with **150 points**. The verification process wrote no card pages and retained the post-win card SHA-256 `a991f8300fef6aeaa7baf0a4214ab157a8ea0b206b9413a500c74499605c755e`. See `local/preview-controller-test/logs/`, `local/multiplayer-qa/physical-win-reload/`, and `local/multiplayer-qa/physical-win-standings/`.

#### Sandbox hardware attempt

The Windows 11 vGPU guest reached its desktop and enumerated the RTX 4070, Intel UHD 770, and a Remote Desktop keyboard. The initial candidate built successfully from the original ISO. At startup the guest session stopped during graphics initialization, before the runner logged an active Direct3D 12 adapter or rendered a frame. A separate `D3D12CreateDevice` call for the default adapter in the guest's system session succeeded. A later guest prepared for the low-power FXC probe reached the system session without reaching interactive logon during the test. The physical controller test still requires an accessible device on an interactive clean Windows installation.

Candidate evidence is under `local/release-preview-qa/`.

### Single-executable preview candidate

The Windows x64 `0.1.0-preview.2` candidate contains one `TocaRecomp.exe`. Its SHA-256 is `f5802e342950a2f673091cb97140ac7eaacc94de17d528c573aafc6a746246ff`. The executable contains 15 embedded support files. A rebuild in a directory with spaces and brackets produced only the executable. Two concurrent `--setup-only` checks published the same complete support files, and a later launch repaired a deliberately modified cached helper before running it.

The standalone candidate launched from a folder holding a copy of an existing `0.1.0-preview.1` memory card and `keys.ini`. It reused the previous prepared setup and ran on the RTX 4070 through Direct3D 12. World Sprintcar Series standings showed **Player One** in first place with **150 points**. The runner reported 341 card reads and zero writes on normal window close. The original card, test copy, and settings retained their hashes. The card passed the filesystem and ECC check. A separate direct launch from a different working directory opened the same data through an explicit `--data-dir` and showed **Dirt Raceway 2 · Sunny** as the next session. Host migration logs are under `local/executable-preview-qa/`.

A clean offline Windows 11 Sandbox on build `26100.9606` copied only the executable and reused verified dependency downloads. Its first launch built the runtime and reached 780 guest frames in 3 minutes and 44 seconds. A direct no-save launch reached 540 frames with the same runner hash. The executable folder still contained only `TocaRecomp.exe`. The unsupported short ISO returned exit code `2` and created no backend or memory card. `--direct` before setup returned exit code `3` and created neither setup nor data. These checks used software graphics and provide clean installation coverage. See `local/executable-preview-qa/guest-plain/` for the guest report and logs.

### Verify an in-place update and reinstall

The public GitHub download matched the single-executable candidate's SHA-256. The test launched `0.1.0-preview.1` from its published archive with a copied memory card, then replaced `TocaRecomp.exe` in that same directory with the downloaded `0.1.0-preview.2` file. The new executable used its bundled support, and the old support files retained their hashes. After the test moved the old application directory aside, a fresh copy of the executable launched with the retained data in a separate `--data-dir` and the existing prepared setup.

The old version, in-place update, and reinstall each reached frame 3120 with 341 card reads and zero card writes. The memory card, `keys.ini`, and prepared runner retained their SHA-256 hashes. These checks used software graphics and scripted controller input. See `local/executable-preview-qa/public-upgrade/` for the local evidence.

A replay of the input recorded during the in-place update showed **Load Successful** and **Dirt Raceway 2 · Sunny**. The first differing checkpoint was frame 2970 in both the headless and windowed diagnostics. Continuing the windowed replay reached frame 3120 with zero card writes and preserved the card hash. The restored menu and card checks passed. Exact replay parity at that transition remains open.
