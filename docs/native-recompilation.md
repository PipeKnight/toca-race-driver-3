# Native recompilation on Windows 11

The developer build for the North American PS2 release `SLUS-21182` v1.02 translates the Emotion Engine executable from a local disc image. The Windows runner boots that image directly and reads its resources at runtime. It uses [ps2-native-recomp v0.0.5](https://github.com/exoteric33/ps2-native-recomp/releases/tag/v0.0.5) and runs without PCSX2 or a BIOS file.

## Launch the local build

From PowerShell 7 at the project root, pass your copy of the supported DVD as an ISO, a matching DVD CHD, or a directory of extracted disc files.

```powershell
.\scripts\Play-RecompiledToca.ps1 -Disc 'C:\path\to\your copy.iso'
```

Use `-Fullscreen` to launch fullscreen or `F11` to toggle it. The default mappings include `Esc` for Start, `A` and `D` for the left stick, and `Space` or `Enter` for Cross. Open **F1 → Keys** for the active mappings.

The launcher attaches a dedicated virtual memory card in slot 1. On first launch, select the first profile slot, confirm both format prompts for the new card, and acknowledge the save confirmation. On subsequent launches, select **PLAYER ONE** or your chosen profile. Select **World Tour** in the main menu to enter the verified race. The card file is `games/toca-slus-21182/toca-slus-21182.ps2` under the backend folder.

For a session without a card, pass `-NoSave`, choose **Continue** in the memory card prompt, then choose **Continue** and **Yes** in the profile screen.

The developer build and its runtime data live under `.tools/ps2-native-recomp-0.0.5/`. The image is needed on each launch. The launcher can be called from a different working directory with its absolute script path. A relative disc path is resolved against the current directory. `-Iso` remains an alias for `-Disc`.

The launcher checks the supplied input against the [reference sizes and SHA-256 digests](ps2-disc-and-archives.md#reference-disc) before creating runtime files or starting the game. It streams decoded DVD bytes for a CHD and reads sectors directly from the CHD during play. For a directory, it verifies a virtual DVD that combines the original file data and sector locations with generated volume metadata. The launcher keeps ISO and CHD source handles open for shared read access until the runner exits. On Windows the native directory reader opens the required files for shared read access and denies write access while it holds them. The launcher returns exit code 2 for an unreadable, unsupported, or different source. CHD support requires a [build with libchdr](#enable-dvd-chd-reading).

To reuse a locally prepared build, put `ps2run.exe`, its runtime DLLs, and the `ee-live` and `vu1-live` caches from the same disc build in a writable directory. Launch it through the same script.

```powershell
.\scripts\Play-RecompiledToca.ps1 -Disc 'C:\path\to\your copy.chd' -PreparedDirectory 'D:\Games\TOCA Local Build'
```

The launcher uses the prepared directory for its working directory, virtual memory card, and temporary files. The runner keeps its keys, logs, states, and caches there. The script accepts a prepared build without a local compiler. The runner still needs compiled EE code for paths the game uses.

## Rebuild from your own ISO

Use a dedicated PowerShell session for the build. Download the [pinned upstream ZIP](https://github.com/exoteric33/ps2-native-recomp/releases/download/v0.0.5/ps2-native-recomp-v0.0.5.zip) under `.tools/downloads/` and verify SHA-256 `cc2c7478463a967a80d058feac9359efce74683aee8805e5e8fa4ad1c8c84cd0` before extraction. The upstream portable setup downloads and verifies its Windows toolchain and graphics dependencies. It takes about 1.3 GB for the unpacked toolchain, plus dependencies, build outputs, and caches.

```powershell
tar.exe -xf .tools\downloads\ps2-native-recomp-v0.0.5.zip -C .tools
Set-Location .tools\ps2-native-recomp-0.0.5
git apply --no-index ..\..\patches\ps2-native-recomp-v0.0.5-toca-reflections.patch
git apply --no-index ..\..\patches\ps2-native-recomp-v0.0.5-gs-upload-cache-overlap.patch
$iso = 'C:/path/to/your copy.iso'
$env:TEMP = (New-Item -ItemType Directory -Path temp -Force).FullName
$env:TMP = $env:TEMP
$env:MSYSTEM = 'MINGW64'
$env:PS2_JOBS = '8'
.\scripts\portable.ps1
. .\tools\portable\env.ps1 -Quiet -Keep 'MSYSTEM','PS2_JOBS'
bash scripts/port.sh toca-slus-21182 $iso --native-only --no-explore
```

For this revision, the extracted `games/toca-slus-21182/disc/SLUS_211.82` must have SHA-256 `350ec46060655197f383dc15ab893231f575d99bfe03f40257ab476525b3b34e`. The upstream build reuses an existing `games/toca-slus-21182/disc.iso` link. Use a fresh game name and build directory when testing a different disc revision. Keep the local ELF, generated sources, executable, and runtime captures out of Git.

### Enable DVD CHD reading

Download the [pinned libchdr source archive](https://codeload.github.com/rtissera/libchdr/tar.gz/93d8c239ff0d4e8d7722985992649fce12d2463b) to `.tools/downloads/libchdr-v0.3.0.tar.gz`. Verify SHA-256 `f38fb1b3e907c8927271a57ad6e3c02347eaa2d5803f910880b4b3c3021b3657` and extract it into `.tools`. To add CHD support to an existing ISO build, run the following from the backend directory in the configured build shell. Apply the patch once per source checkout.

```powershell
git apply --no-index ..\..\patches\ps2-native-recomp-v0.0.5-dvd-chd.patch
$libchdr = (Resolve-Path '../libchdr-93d8c239ff0d4e8d7722985992649fce12d2463b').Path
$clang = (Resolve-Path 'tools/portable/llvm-mingw/bin/clang.exe').Path
$native = 'build/native-toca-slus-21182'
$runtimeEntry = Select-String -LiteralPath "$native/CMakeCache.txt" -Pattern '^PS2_RUNTIME_LIB:FILEPATH='
$runtimeArchive = ($runtimeEntry.Line -split '=', 2)[1]
$runtimeBuild = Split-Path -Parent $runtimeArchive
$chdOptions = @("-DPS2_LIBCHDR_DIR:PATH=$libchdr", "-DCMAKE_C_COMPILER:FILEPATH=$clang")
cmake -S . -B $runtimeBuild @chdOptions
cmake --build $runtimeBuild --target ps2runtime
cmake -S . -B $native @chdOptions
cmake --build $native --target ps2run
```

The tested input is a standalone CHDv5 DVD with 2,048-byte sectors, created with [MAME chdman](https://docs.mamedev.org/tools/chdman.html). For example, run `chdman createdvd -i "your copy.iso" -o "your copy.chd" -c zstd,zlib`. Point the launcher at the result.

### Build directly from your DVD CHD

Unpack and verify the same backend and libchdr sources, then follow the [Windows build setup](#rebuild-from-your-own-iso) through loading the portable tools. From the backend directory, apply the DVD CHD runtime patch if it is still pending, then apply the setup patch once. Use the following build command in place of the ISO command.

```powershell
git apply --no-index ..\..\patches\ps2-native-recomp-v0.0.5-dvd-chd.patch
git apply --no-index ..\..\patches\ps2-native-recomp-v0.0.5-dvd-chd-setup.patch
$env:PS2_LIBCHDR_DIR = (Resolve-Path '../libchdr-93d8c239ff0d4e8d7722985992649fce12d2463b').Path.Replace('\', '/')
$disc = 'C:/path/to/your copy.chd'
$digest = '08c1f20904bb99067588f0aff8637f0e97cbd46d2570f4a0247245e32e5ddf29'
bash scripts/port.sh toca-slus-21182 $disc --native-only --no-explore --chd-sha256 $digest
```

Setup builds a small native reader and streams the decoded DVD bytes to verify the reference hash. It reads the volume directory and extracts `SYSTEM.CNF` and `SLUS_211.82` from the CHD. Recompilation uses that ELF, and the runner opens the original CHD for boot and resource reads. The build and launch steps use the CHD directly without writing an ISO. Run the Windows launcher with `-Disc` after the build.

### Build directly from extracted disc files

Keep the original filenames and subdirectories. The source directory must contain the supported disc's `SYSTEM.CNF`, `SLUS_211.82`, `RDH.DIR`, archives, and supporting files. Use a copy of the extracted files or the root of a mounted copy of the supported DVD. Setup builds a native reader that supplies the 67 files at their reference sector locations and generates ISO 9660 directory metadata in memory. Reads outside the generated metadata and file ranges return zeros. The virtual layout has its own SHA-256 because its metadata and padding differ from the original ISO.

Use the [Windows build setup](#rebuild-from-your-own-iso) through loading the portable tools. Apply the DVD runtime and setup patches in the order shown in [Build directly from your DVD CHD](#build-directly-from-your-dvd-chd), then apply the directory patch from the backend directory. Use the following build command in place of the ISO command.

```powershell
git apply --no-index ..\..\patches\ps2-native-recomp-v0.0.5-dvd-folder.patch
$disc = 'C:/path/to/extracted disc files'
$digest = '437b2dd9d69f92487c996f783316170ea1d1e3700407d982f40f63c2dc8bd3ed'
bash scripts/port.sh toca-slus-21182 $disc --native-only --no-explore --dvd-sha256 $digest
```

The folder build works without libchdr. Set `PS2_LIBCHDR_DIR` as in the CHD instructions if you also want that runner to accept DVD CHDs. Run the Windows launcher with `-Disc` pointing to the directory. The build and the runner read the original files in place.

Use `-DPS2_EMBED_COMPILER_PATH:BOOL=OFF` when configuring the runtime CMake build for a prepared runner that should skip the absolute compiler path used during setup. Build `ps2runtime` again, then relink `ps2run`. Include the prepared `ee-live` and `vu1-live` caches in the portable directory.

## Reproduce the race check

Run the following from `.tools/ps2-native-recomp-0.0.5/` in the configured build shell. This uses a fixed set of guest controller inputs and captures selected frames. It uses the disc directly and does not attach a memory card.

```powershell
$env:PS2_EE_LIVE = '1'
$env:PS2_VU_LIVE = '1'
$env:PS2_GPU_BACKEND = 'dx12'
$env:PS2_TOCA_EFU_TIMING = '1'
$frames = (New-Item -ItemType Directory -Force ../../local/native-toca/drive-frames).FullName
$inputs = @(
    '--press','300:start:15', '--press','600:start:15',
    '--press','900:start:15', '--press','1200:start:15',
    '--axis','1440:lx:255:18', '--press','1590:cross:20',
    '--press','1750:cross:12', '--axis','1920:lx:0:12',
    '--press','2070:cross:12', '--press','2320:cross:12',
    '--press','2560:cross:12', '--press','2800:cross:12', '--press','3060:cross:12',
    '--press','3240:cross:360', '--axis','3370:lx:104:25', '--axis','3470:lx:151:25'
)
.\build\native-toca-slus-21182\ps2run.exe --disc $iso --game-dir games/toca-slus-21182 `
    --frames 3720 --frames-dir $frames --frame-every 999999 `
    --frame-at 3230 --frame-at 3310 --frame-at 3390 --frame-at 3490 --frame-at 3590 --frame-at 3700 @inputs 2>&1 |
    Tee-Object -FilePath ../../local/native-toca/drive.log
```

## Verify championship completion across restarts

Use a separate virtual memory card with an autosave-enabled profile. In **Pro Career → Oval → World Sprintcar Series**, select the **WSC Sprintcar**, set the race length to **1 Lap**, and use **Skip Session** to advance past practice and qualifying. Finish **National Dirt Raceway Stage 1** and continue through **Race Results** and **Championship Standings** until **Dirt Raceway 2 · Sunny** is shown as the next session. Once the autosave has finished, exit the runner.

Start a new runner process with the same ISO and card. Select the profile, acknowledge **Load Successful**, and enter **Pro Career → Oval**, which shows **Championship in Progress**. Resume the Sprintcar series. In the next round's practice session, open the pause menu and check **Championship Standings** and **Race Fixtures**. The standings should retain the points awarded in the first race. The fixtures should show points for Stage 1 and mark Stage 2 as the current round.

On Windows 11 with Direct3D 12, the test driver finished 10th of 10 with a time of `2:21.55`. The test used scripted controller inputs with checkpoints during the race. The runtime wrote the test card after the finish, and the upstream `mcformat.py check` reported `RESULT: fine`. The restart began at boot with the test card as its only source of game progress. After the restart, the fixtures showed `0` points for Stage 1 and highlighted Stage 2. The player had `0` points in ninth place tied in the championship standings, with the same points as before the restart for the other drivers. The elapsed race time was verified on the original results screen. The post-restart screens verified points and advancement to the next round. Local captures and logs are in `local/native-toca/finish-test/`.

With the EFU timing fix enabled, the timed interpreter build and the timed compiled build each repeated the last straight from its checkpoint on a copy of the pre-finish card. Both finished in the same time and position, and both restored the standings after a cold restart. The repeat captures and logs are in `local/native-toca/reflection-validation/`.

For the full championship check, start the compiled build from the Stage 1 autosave and resume **Dirt Raceway 2 · Sunny**. Skip practice and qualifying, finish the race, and continue through **Race Results** and **Championship Results** to **Select Championship**. Exit after the autosave completes. On the next boot, load the same profile from the card and enter **Pro Career → Oval**. Oval should show its completion percentage where it previously showed **Championship in Progress**. World Sprintcar Series should be available to select again.

This run covered both one-lap rounds on Windows 11 with Direct3D 12 and the compiled VU1 timing fix. The second race finished in `1:00.32`, in 10th place. The final championship table recorded **PLAYER ONE** in 10th place with 0 points. The championship objective required 6th place or better, and the profile had 0 Oval cups after reloading. The game wrote the card after Stage 2, and `mcformat.py check` reported `RESULT: fine`. Both restarts loaded the memory card without a runtime checkpoint. The driving test used scripted controller inputs and runtime checkpoints within races. The captures and logs are in `local/native-toca/championship-test/`.

### Verify cup and unlock persistence

On an isolated copy of the profile with 0 cups, run World Sprintcar Series with the game's **Custom 50%** difficulty and **1 Lap** settings. Stage 1 finished 10th in `1:05.62`. A cold launch restored the championship from the card and resumed Stage 2. Stage 2 finished 2nd in `0:35.00`, earned 125 points, and placed **PLAYER ONE** tied for 4th overall. During the races the test used recorded and scripted controller inputs, checkpoints, and a local driver that read car position to steer. The game produced the results and wrote the save through its normal autosave.

After leaving the results and closing the process, boot again with the awarded card as the only source of progress. The fresh Windows 11 run loaded the profile, showed **Total Cups 1/177** and **Cups 1/3** on World Sprintcar Series, and opened the Chevrolet Silverado selection in **US Speedtruck Challenge**. At zero cups this championship was locked. The award also announced **Bonus 1960's Grand Prix**. A separate cold launch opened it under **Simulation Modes → Free Race → Classics** and reached the Donington GP Circuit grid in the Lotus Type 49. The memory card passed `mcformat.py check`.

Captures and logs are in `local/native-toca/championship-cup-test/`. `cup-race2-award-results-frames.png` shows the final race and championship tables. `cup-award-before-restart-frames.png` shows the bonus notification. `cup-cold-pro-career-frames.png` shows the saved cup and Speedtruck entry. `cup-free-race-bonus-entry-frames.png` and `cup-free-race-bonus-start-frames.png` show entry into the bonus race after boot.

The version 10 SPU2 runner repeated the second-round finish on a copy of the pre-award card. It loaded the version 9 checkpoint from the final straight at frame 8625 and held Cross from frame 8626 for 132 frames. Cross at frames 8850, 9290, and 9880 advanced from the finish to the results and award screens. The game finished 2nd in `0:35.13`, placed tied 4th overall with 125 points, and recorded the cup through its ordinary autosave. Two fresh launches then used independent copies of the newly written card. One showed **Total Cups 1/177**, **Cups 1/3** for World Sprintcar Series, and the Chevrolet Silverado selection in **US Speedtruck Challenge**. The other started **Bonus 1960's Grand Prix** in the Lotus Type 49 at Donington GP Circuit. Both cold runs preserved the card hash and passed `mcformat.py check`. No guest stream-buffer warnings appeared. Each run used the original ISO and Direct3D 12 on Windows 11. See `local/clio-window-qa/sprintcar-envx-finish-autosave/` and `sprintcar-envx-fresh-award-*/` for captures, logs, and input arguments.

A prepared runner with the upload cache correction and no detected compiler cold-booted another copy of the awarded card. One run reached Chevrolet Silverado practice at **Nashville Speedway · Sunny**. A second run skipped practice and qualifying and started the one-lap race from 20th place. Both runs used scripted input, retained the awarded card hash, and reached the track directly from boot. A driving trial also exercised the yellow flag. See `local/clio-window-qa/cache-prepared-speedtruck/`, `cache-prepared-speedtruck-cold-grid/`, and `cache-prepared-speedtruck-first-finish/`.

### Verify US SpeedTruck Challenge across cold starts

The Windows 11 test used the custom four-round series with Custom 50% difficulty, one lap per race, and practice and qualifying skipped. A local driver followed a path sampled from an AI truck and recorded normal controller input. The uninstrumented prepared runner replayed the inputs from each race checkpoint with the reference ISO and Direct3D 12. All 42 shared frame captures matched, and the replay logs reported no checkpoint divergence through the tested endpoints or guest stream-buffer warnings. The test fixed the RTC at `1763726400`.

After Race Results, Championship Standings showed **PLAYER ONE**, 20th with 25 points. The next session was **Dover International · Sunny**. A cold launch restored the championship from the memory card alone. The standings in Dover practice still showed 25 points, and Race Fixtures showed 25 for Nashville Super Speedway and highlighted Dover as round 2 of 4. A separate cold launch from the same card skipped practice and qualifying and reached the one-lap Dover race in 20th position. The cold checks retained the saved card's SHA-256.

The same prepared runner replayed the Dover controller input from the race checkpoint and continued from the finish menu to the game's autosave. Race Results showed 20th place in `1:09.71` and 25 points. Two reads of the finish checkpoint advanced to identical autosaves. A cold boot from that card showed 50 points overall and separate 25-point results for Nashville and Dover. Race Fixtures highlighted **Indianapolis Motor Speedway Oval** as round 3. A separate cold boot reached its race grid. See `dover-prepared-replay/`, `dover-final-table/`, `indy-restored-points/`, and `indy-race-grid/` under `local/nashville-qa/`.

Indianapolis finished 20th in `2:34.79` and added 25 points. All 14 captured frames and the autosave matched between the driving run and the prepared replay. A cold boot from the identical card restored 75 points from the three completed rounds and selected **Gateway International · Sunny** as round 4. A second boot from that card reached the Gateway race after skipping practice and qualifying. See `indy-prepared-replay/`, `indy-table/`, `gateway-restored-points/`, and `gateway-race-grid/`.

Gateway finished 20th in `1:27.81` and added 25 points. The game wrote the final autosave and recorded 20th overall with 100 points. Continuing from Championship Results returned to **Select Championship**. A fresh process booted from the final card alone. Oval displayed its completion percentage and opened **Select Championship** with US SpeedTruck Challenge available to select again. Separate boots opened the new SpeedTruck setup and started **Bonus 1960's Grand Prix** at Donington GP Circuit in the Lotus Type 49. The existing Sprintcar cup remained in the total. SpeedTruck recorded zero cups because the objective required 6th place or better. The final card passed `mcformat.py check`, and its SHA-256 stayed identical across the driving run, the prepared replay, the results check, and the cold reloads. See `gateway-prepared-replay/`, `gateway-final/`, `gateway-final-cold/`, `speedtruck-new-after-finish/`, and `bonus-after-speedtruck/`.

| Round | Track | Finish | Championship points |
| --- | --- | ---: | ---: |
| 1 | Nashville Speedway | 1:17.72 | 25 |
| 2 | Dover International | 1:09.71 | 50 |
| 3 | Indianapolis Motor Speedway Oval | 2:34.79 | 75 |
| 4 | Gateway International | 1:27.81 | 100 |

Local evidence is under `local/nashville-qa/`. The captured input and first finish are in `drive-line-30/`. The prepared replay, result screens, cold standings and fixtures, and next race start are in `nashville-prepared-replay/`, `nashville-results/`, `dover-restored-points/`, and `dover-race-grid/`, respectively.

## Verification and limits

- Windows 11 x64, build `26220`, RTX 4070. The recompilation produced 224 C++ units. The runner booted the ISO, reached the main menu, and started the World Tour race at Oschersleben. The Direct3D 12 check ran through 3,720 guest frames. The car responded to throttle and steering after the race start. A separate Vulkan run reproduced race startup and matched the corresponding Direct3D 12 captures at frames 3230, 3310, and 3390.
- A windowed Direct3D 12 run with the same inputs reached the race and ran through 3,610 frames. The runtime reported about 60 seconds of WASAPI audio with no queue underruns. To repeat this variant, add `--window --no-record`, use `--frames 3610`, and omit `--frame-at 3700` in the command above. A separate launch through `Play-RecompiledToca.ps1` verified the launcher from outside the repository to its 600-frame limit.
- A separate blank card was formatted through the game. The game reported **Save successful** and created a `BASLUS-21182profile` save directory. The upstream `mcformat.py check` passed. A fresh run loaded **PLAYER ONE**, displayed **Load Successful**, and reached the World Tour race. The card SHA-256 stayed the same across both reload checks. Launcher tests verified that the default launch attaches its own card and that `-NoSave` starts without a card. The local capture and log files are under `local/native-toca/save-test/`.
- The two-round completion, cup award, and unlock persistence checks cover World Sprintcar Series on the North American v1.02 disc. Complete playthroughs of other championships, disc revisions, and Linux and macOS builds remain unverified.

### Isolated Windows 11 run

The acceptance run used a private folder with the runner, SDL2, the Direct3D shader compiler libraries, and the existing VU1 and EE caches. It ran from a separate working directory with a system-only `PATH` and with temporary files, logs, and saves inside the test folder. The first pass found Clang at a path embedded in the developer build. The follow-up used the same build objects with the compiler-discovery object rebuilt without that embedded path. The log confirmed that neither live recompiler found a C++ compiler.

The compiler-free follow-up booted in fullscreen, formatted a new card, saved a profile, and entered the Oschersleben World Tour intro. WASAPI supplied 74.96 seconds of audio with zero queue underruns. A separate windowed run exited through the normal Close control with exit code 0. The automated keyboard injection did not produce guest pad events in that run, so keyboard mappings and the fullscreen hotkey still need a manual or equivalent input test. Windows testing so far uses the existing Windows 11 installation and the private folder.

A foreground retry on Windows 11 25H2 build 26220.9606 did not show a fullscreen switch or quick menu after automated F11 and F1 presses. The runner closed normally and logged 55.51 seconds of WASAPI playback with zero underruns. See `keyboard-hotkey-check.log`. Keyboard behavior with a physical input device remains open.

The SDL controller harness initially read the guest ports before the frame boundary where host input becomes visible. It also treated the host quick menu and its Select chord as ordinary game buttons. With the [test harness patch](../patches/ps2-native-recomp-v0.0.5-pad-test.patch), all 62 checks passed on Windows 11. The checks cover buttons, analog sticks, trigger pressure, two controller ports, rumble and unplugging. The separate runtime save suite passed 87 checks, including recovery after an interrupted write, backup recovery and locking out competing card writers. See `local/chd-dvd/pad-vblank.log` and `local/chd-dvd/save-files.log`.

The test restored a profile from the automatic backup created when Time Trial saved a ghost slot. The recovered card loaded on a cold boot and showed the World Sprintcar Series cup. Player One recorded a `0:30.87` lap on National Dirt Raceway Stage 2, ended the session, and the game saved the ghost. A fresh launch restored the profile and reported a successful load after selecting the player ghost. In local Multiplayer, the second virtual guest pad joined and accelerated its own car in the lower split-screen view. The upper view continued responding to the first pad.

#### Windows Sandbox verification

A fresh Windows 11 Sandbox on build `26100.9606` used the prepared runner, its DLLs and caches, and the PowerShell launcher. The package and original ISO were mapped read-only. The guest copied the package to a writable local directory and shared only the test evidence folder with write access. Networking was disabled. Both live translators reported that no C++ compiler was available. [Windows Sandbox configuration](https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/windows-sandbox-configure-using-wsb-file)

The virtual GPU session showed a black screen before guest login. Starting a separate Sandbox with vGPU disabled reached the desktop and opened the game through Direct3D 12 using Microsoft Basic Render Driver. The WebGPU surface acquired frames after roughly one second each in both Mailbox and FIFO. The Mailbox process closed normally with exit code 0 at frame 207. Its Remote Audio device received 3.25 seconds of game audio and reported 96 queue underruns. See `local/sandbox-qa/clean-windows/evidence-warp/`.

An independent clean session used the CPU graphics renderer and SDL presentation with `PS2_GS=cpu` and `SDL_RENDER_DRIVER=software`. The unchanged launcher, started from a separate working directory, validated the ISO, opened a window, and exited at the requested 780-frame limit with code 0. The Remote Audio device received 12.80 seconds of game audio with zero underruns or dropped samples during that startup check. See `local/sandbox-qa/clean-windows/evidence-cpu/launcher-logs/`.

The same guest then ran the prepared executable in fullscreen with a new card. Scripted input selected both format confirmations, enabled autosave, created Player One, and reached the Oschersleben intro grid sequence. The game wrote the card three times and `mcformat.py check` passed. A fresh windowed process reported **Load Successful** for Player One and reached the Oschersleben race after the starting countdown. The first run delivered 76.13 seconds of game audio over 210.38 seconds with 146 queue underruns. This capture covers startup, menus, and the race entry while a separate graphics diagnostic was running in the guest. See `local/sandbox-qa/clean-windows/evidence-cpu/fresh-profile/` and `fresh-profile-relaunch/`.

An SDL virtual controller entered the game, loaded a profile, and reached the main menu. Its recording shows the guest receiving Start and Cross, and the log records attachment and removal on port 1. The CPU renderer delivered 36.46 seconds of game audio to Remote Audio with zero underruns in this menu test. The separate attempt to keep Direct3D 12 rendering and use only SDL for presentation stalled before its first capture and was stopped. See `local/sandbox-qa/clean-windows/evidence-cpu/sdl-controller/` and `sdl-presentation/`.

The prepared runner resumed World Sprintcar Series from the checkpoint on the final straight and posted tied fourth with 125 points. The game displayed the Bonus 1960's Grand Prix unlock and wrote the normal autosave. The resulting card was byte-identical to the separately verified native Windows award card and passed `mcformat.py check`. After a full runner exit, a new process opened the profile from that card alone, displayed **Load Successful**, and reported zero card writes. The post-race and reload hashes matched. This case covers the finish through autosave and relaunch. The fullscreen intro and windowed race tests still had audio underruns under software rendering. See `local/sandbox-qa/clean-windows/evidence-cpu/sprintcar-finish/`, `sprintcar-relaunch/`, and `card-hashes.json`.

#### Replay and audio verification

The game saved the World Sprintcar Series Stage 2 replay from Race Results. In a continuous cold run from the card, **Simulation Modes → Load Replay** found the replay, loaded the track, and displayed the cars moving through the saved race. The guest logged `SOUND_SetStreamBuffer` allocation errors, while WASAPI reported 116.13 seconds of queued game audio without an underrun in that run. The device counter covers the whole run. A repeat captured non-silent stereo output during playback to `race-replay-audio-evidence.wav`. The ghost and replay cards both passed `mcformat.py check`.

An isolated PCSX2 2.8.2 reference loaded the same profile and replay from a copy of the native runtime's memory card and played the saved race. With IOP console logging enabled, the reference log recorded zero stream-buffer errors through the playback check. A native diagnostic run with `PS2_TTY_FRAME=1` reported that stream buffer 2 was already allocated at guest frame 7092, just after loading, then reported that it was unallocated when the guest closed it at frame 7732 during playback. The first playback frame in the diagnostic captures is 7130. The effect on individual sounds still needs verification. See `race-replay-sound-diagnostic.log`, `race-replay-sound-diagnostic-frames.png`, `pcsx2-reference-saved-replay.png`, and `pcsx2-reference-saved-replay.log`.

The same replay also logged both stream-buffer errors with the unmodified native runner, so this reproduction predates the VU1 reflection fix. The `--trace-iop` run identified distinct sound RPC payloads. A probe of the guest sound handlers and a byte watch confirmed that the first allocation set slot 2's state to `2`, a close cleared it, and the next allocation set it back to `2`. About 2.09 seconds later another allocation requested slot 2 with a different IOP buffer address while the state was still `2`. The original sound module raised the warning and kept the existing buffer pointer. The source of the conflicting request sequence and its audible effect remain open. The local evidence is in `replay-stock-audio-ab.log`, `stream-call-trace.log`, `replay-stream-handler-probe.log`, and `replay-stream-slot-watch.log`.

For this disc revision, the diagnostic checkpoint loaded `SOUND.IRX` at IOP address `0x00026F00`. Run with `PS2_IOP_PROBE=30cb0,33da4,30d78,33f78` to log the allocation and close handlers and their error paths. Set `PS2_WATCH_IOP=4ab90:4ab94` to watch the slot 2 state and adjacent bytes. The addresses apply to this boot configuration. Check the module base before using them with another boot.

An isolated timing experiment advanced the IOP to the current EE cycle before each EE SIF DMA submission. Both errors still occurred in the experiment, three guest frames later than in its control. See `replay-sif-sync-control.log` and `replay-sif-sync-experiment.log`.

A paired audio capture booted the same saved Sprintcar replay from matching memory-card copies. The native SPU2 dump and the PCSX2 2.8.2 PCM capture both contained stereo audio at 48 kHz and 16 bits. The comparison used 100 ms stereo RMS windows from seconds 87–117 of the native capture and tested PCSX2 starting offsets from 123 to 135 seconds in 100 ms steps. The highest Pearson correlation was 0.27 at an offset of 130.7 seconds. The native log recorded allocation and close warnings for buffers 2 and 8. The PCSX2 IOP console showed none. The 45-second native playback sample that includes these warnings contained no fully silent 50 ms window. The mix comparison leaves the contribution of each stream unresolved. The same allocation and close errors for buffer 2 also occurred when starting Sprintcar qualifying. Local evidence includes `native-replay-spu2.wav`, `pcsx2-reference-spu2.wav`, `native-replay-audio-parity.log`, `local/pcsx2-audio-replay/logs/emulog.txt`, and `sprintcar-practice-to-qualifying.log`.

The same replay reproduced seven stream-buffer warnings at identical guest frames in separate ISO and DVD CHD runs with a fixed guest clock and matching card copies. The warning sequence is independent of the choice of input container in this test. Both runs reached frame 6750, with no changes to either memory card. The generic SIF command completion and DMA interrupt tests also passed. See `local/chd-dvd/iso-replay.log` and `local/chd-dvd/chd-replay.log`.

In a diagnostic build, the plain SPU2 DMA completion delay used 24 IOP cycles per 16-bit word, the rate used by PCSX2 2.8.2. The experiment kept the existing memory copy and automatic DMA paths. A separate switch exposed the busy status during the transfer. Each run used the same ISO, guest clock, and saved replay on a fresh card copy. [PCSX2 2.8.2 SPU2 DMA source](https://github.com/PCSX2/pcsx2/blob/v2.8.2/pcsx2/SPU2/Dma.cpp)

| Diagnostic setting | Guest frame limit | Stream-buffer warnings | First warning |
| --- | ---: | ---: | --- |
| Baseline | 6750 | 7 | Allocation at 5104 |
| Busy status only | 6750 | 7 | Allocation at 5101 |
| Completion delay only | 6750 | 3 | Allocation at 5120 |
| Completion delay and busy status | 6750 | 3 | Allocation at 5123 |
| Baseline with IOP probes | 8400 | 4 | Allocation at 6246 |
| Completion delay with IOP probes | 8400 | 4 | Allocation at 5114 |

The longer runs produced 139.80 seconds of 48 kHz stereo PCM each. Neither had a fully silent 50 ms window from seconds 87 through 117. Both IOP traces show the same conflicting allocation pair for slot 2. The second request arrived with a different buffer address and with no intervening close for that slot. In all 223 allocation calls captured at the dispatcher, the slot argument matched the low halfword of the decoded command on the IOP stack. The change in warning counts in the shorter runs did not persist in the longer runs. The regular runner retains the original DMA timing.

A repeat in PCSX2 2.8.2 reached the input recording's endpoint at frame 10800 in saved-race playback. The IOP console again recorded no allocation or close warnings. The final IOP snapshot located `SOUND.IRX` at `0x54030` and showed slots 2 and 8 allocated. The native traces, PCM, reference log, and snapshot inspection are in `local/audio-stream-qa/`.

Two more passes used non-pausing IOP logpoints in a separate PCSX2 v2.9.172 copy. Both reached frame 10800 on the track and logged 57 allocation calls and 57 close calls during the capture window. Every allocation received an empty slot, and every close received an occupied slot. From the first 64 KiB allocation for slot 2, the two reference runs matched for the first 33 calls before the ordering varied. The extended native baseline matched the first 18 calls by operation, slot number, and allocation source address. In both native timing variants a conflicting request called for slot 2 and source `0x1B1990`. At the corresponding early allocation, both reference passes used free slot 8 for that source address. See `local/audio-stream-qa/pcsx2-instrumented-replay-1.log` and `local/audio-stream-qa/pcsx2-instrumented-replay-2.log`. [PCSX2 debugger logpoints](https://github.com/PCSX2/pcsx2/pull/14557)

The local `SOUND.IRX` dispatcher copies each command's halfword arguments from the incoming batch to its stack. The allocation command uses opcode `0x73` and passes its first argument as the slot number. In the reference EE executable, the call at `0x00278120` passes the slot in `a0`, and `0x00266678` writes it into the command under construction. The call at `0x00267A54` submits the batch from `0x005C4980` for the 2048-byte RPC. These are the EE points for comparing the selected slot and the outgoing packet with the IOP trace.

#### Trace the replay slot before SIF transfer

A third PCSX2 v2.9.172 pass logged allocations at both ends of the same recording. All 57 EE requests matched the IOP calls by slot, buffer address, size, and source address. Every IOP allocation saw an empty slot. For source `0x1B1990` the four requests used slots `8, 8, 4, 4`. The pass reached frame 10800 and the reference card's SHA-256 stayed unchanged. The paired log is `local/audio-command-origin/pcsx2-ee-iop.log`.

The native state watch loaded the local frame-6595 replay confirmation checkpoint and pressed Cross at frame 6690 for 12 frames. It ran to frame 7350 using the original ISO and a disposable card copy. The EE sound RPC callback cleared slot 2's byte at `0x005C668A` at frame 6968. There was no intervening IOP close for that slot before the EE registered a new allocation at frame 7092. The IOP received slot 2 for source `0x1B1990` and reported it was still occupied. A separate watch of the EE command arguments at `0x005C5180` recorded the same slot, buffer, size, and source before that command went to the IOP. The card copy's SHA-256 stayed unchanged. See `local/audio-command-origin/native-repro-state/trace.log` and `local/audio-command-origin/native-repro/trace.log`.

The EE selection routine at `0x0026BB78` reads the table at `0x005C6688` and accepts state `0` or `3` for a new request. The callback at `0x00266E58` clears active entries and rebuilds them from the sound RPC response. A watch of the reply buffer at `0x005C5980` captured slot 2 in the frame-6966 response. The complete frame-6968 reply contains only slots 6 and 7, which explains why the callback left slot 2 clear. Its buffer was still allocated on the IOP. When the same checkpoint confirmed at frame 6660, the corresponding reply two frames after reallocation still included slot 2. That control reached frame 7550 without a stream-buffer warning. See `local/audio-command-origin/native-rpc-reply/trace.log`, `local/audio-command-origin/native-rpc-control/trace.log`, and `local/audio-command-origin/native-slot-state/trace.log`.

A fourth PCSX2 pass logged 10,383 replies directly from the IOP before SIF transmission and reached frame 10800. All 1,504 complete replies taken while slot 2's buffer was allocated included the voice. The native IOP watch found that the reply builder's active-voice byte at `0x0004AA78` was cleared by a voice retirement path, separate from the buffer allocation state. In matched native runs through frame 7140, the 6690 confirmation reproduced that retirement and the warning at frame 7092. The 6660 confirmation retained the active flag through the matching early reply and used slot 8 for the next allocation. See `local/audio-command-origin/pcsx2-iop-replies.log`, `local/audio-command-origin/iop-voice-failure/trace.log`, and `local/audio-command-origin/iop-voice-control/trace.log`.

The retirement path checked the envelope of SPU2 core 0 voice 0 at `0x1F90000A`. In the failing run it read `ENVX = 0` about 0.4 ms after key-on, while the voice was still in its attack phase. The control returned `0x7FFF` at the corresponding read. The native SPU2 processes 32 samples every 0.667 ms at 48 kHz. An isolated runner that processed eight samples per update returned `0x7FFF` on both input timings. Both runs reached frame 7350 with no allocation or close warnings, and the previously conflicting source `0x1B1990` used slot 8. The regular runner retains its existing update interval. See `local/audio-command-origin/spu-env-failure/trace.log`, `local/audio-command-origin/spu-env-control/trace.log`, and the `batch-8-*` diagnostic folders. [PS2SDK SPU2 envelope parameter](https://github.com/ps2dev/ps2sdk/blob/master/common/include/libsd-common.h)

A paired run extended the 6690 confirmation through frame 8100. The regular runner logged an allocation error at 7092 and a close error at 7732. The eight-sample runner logged neither. Both runs dumped 25.084 seconds of 16-bit stereo PCM at 48 kHz. Neither had a fully silent 50 ms window from seconds 9 to 25, and both card copies retained their initial hash. A fresh process with the eight-sample runner and timed VU1 EFU path entered the Oschersleben World Tour race directly from the ISO and reached frame 3720 without sound stream-buffer warnings. Its in-race PCM had no fully silent 50 ms window from seconds 56 to 61. These checks cover the warnings and gross dropouts. Mix parity with PCSX2 still needs verification. See `local/audio-command-origin/extended-baseline/`, `extended-batch8/`, and `batch-8-cold-oschersleben/`.

#### Verify the eight-sample SPU2 candidate

The cold replay test booted the same ISO on both runners, loaded separate copies of the same memory card, and opened the World Sprintcar Series Stage 2 recording via **Simulation Modes → Load Replay**. There was no runner checkpoint. Both reached frame 8200 with the cars visible in playback and the memory cards unchanged. The regular runner logged a slot 2 allocation error at frame 4373 and a close error at frame 5013. The eight-sample runner logged zero stream-buffer errors. Repeating the same inputs with PCM and frame capture reproduced the result. Both PCM captures contain 6,550,272 stereo sample frames at 48 kHz, with no fully silent 50 ms window during seconds 76–106. Moving the final confirmation from frame 3970 to 4147 yielded one allocation error at 4549 on the regular runner and zero errors on the candidate through frame 7450. See `local/audio-command-origin/cold-sprintcar-alt-*` for the alternate timing.

A separate qualifying test started with the local frame-8940 `practice-stage2-advance.state` checkpoint, selected **Continue**, and entered the timed session at National Dirt Raceway Stage 2. The regular runner logged a slot 2 allocation error at frame 9291 and a close error at frame 9956. The eight-sample runner logged zero stream-buffer errors through frame 10620. Both produced approximately 28 seconds of PCM and the card copies retained their initial hash.

A broad offset search on 50 ms stereo RMS windows did not establish a common replay position. A second comparison aligned the return of sustained engine audio after the loading gap. The onset was 126.58 seconds into the previous PCSX2 2.8.2 capture, 70.56 seconds into the regular-runner capture, and 70.58 seconds into the candidate capture. Over the next 25 seconds, the mean of the 10 ms stereo RMS windows was 9% below PCSX2 for the regular runner and 5% below for the candidate. The RMS correlations were 0.610 and 0.600 respectively. From seconds 2 to 7 after onset, near the original allocation error, the correlation rose from 0.288 to 0.544. These comparisons use an audio cue for alignment. The reference mix still needs a frame-synchronized comparison of the audible effects, including engines, tires, impacts, and crowd sound. See `local/audio-command-origin/pcm-comparison.txt`, `replay-onset-comparison.txt`, and the `cold-sprintcar-capture-*` and `qualifying-sprintcar-*` folders.

Two runs per build alternated in baseline, candidate, candidate, baseline order on the Windows 11 test machine (Core i7-12700, RTX 4070, Direct3D 12). Each ran the same checkpoint from frame 6595 to 8100 without PCM or frame capture. With `PS2_IOP_LOAD=1`, the average time spent in SPU2 for frames 7201–8100 was 0.205–0.207 ms per frame for the regular runner and 0.251–0.254 ms for the candidate. Scheduled SPU2 updates increased from 25 to 100 per frame. Total runtimes, including startup, overlapped at 26.062–26.256 seconds and 25.754–26.478 seconds respectively. See `local/audio-command-origin/benchmark-result.txt` and the four `bench-*` folders.

Both windowed runners also reached frame 8700 from the same checkpoint and delivered 35.08 seconds of stereo audio to WASAPI at 48 kHz, with zero queue underruns and zero dropped samples. The candidate logged zero stream-buffer errors. The regular runner logged allocation errors at frames 7154 and 8445 and a close error at frame 7794. The candidate stretched 0.21 seconds of game audio during the run, and the regular runner reported zero stretch. This covers short playback on the test machine. Sustained presentation and host audio across multiple events remain open. See `local/audio-command-origin/host-audio-batch8/trace.log` and `host-audio-baseline/trace.log`.

To build the candidate in a separate backend checkout, apply the timing patch after the reflection patch in the [ISO build procedure](#rebuild-from-your-own-iso). Use a fresh build directory. This changes the SPU2 update interval for all voices, input DMA, and reverb. Keep the regular build available for matched tests until the audio and performance checks pass.

```powershell
git apply --no-index ..\..\patches\ps2-native-recomp-v0.0.5-spu2-envelope-timing.patch
```

For the cold replay case, attach a copied card with the saved Sprintcar Stage 2 replay and pass `--rtc 1763726400 --frames 8200 --no-record`. From the prepared backend, use the following guest inputs with `--disc`, `--game-dir`, and `--memcard`. Set `PS2_GPU_BACKEND=dx12`, `PS2_TOCA_EFU_TIMING=1`, and `PS2_TTY_FRAME=1` for the same diagnostic configuration. Set `PS2_DUMP_AUDIO` to a new WAV path to capture the chip's stereo output.

```powershell
$inputs = @(
    '--press','300:start:15', '--press','600:start:15',
    '--press','900:start:15', '--press','1200:start:15',
    '--press','1590:cross:12', '--press','1900:cross:12',
    '--axis','2210:lx:255:12', '--axis','2320:lx:255:12', '--press','2480:cross:12',
    '--axis','2660:lx:255:12', '--axis','2780:lx:255:12', '--axis','2900:lx:255:12',
    '--axis','3020:lx:255:12', '--axis','3140:lx:255:12',
    '--press','3320:cross:12', '--press','3520:cross:12',
    '--press','3730:cross:12', '--press','3970:cross:12'
)
```

For the local qualifying checkpoint, load `practice-stage2-advance.state`, set `--frames 10620 --no-record`, and use `--axis 9000:lx:0:12 --axis 9100:lx:0:12 --press 9230:cross:12`. Use a copy of the corresponding card for this checkpoint.

#### Compare synchronized replay audio and longer races

An isolated PCSX2 2.9.172 run used the same Sprintcar replay card and reached input frame 10800 with zero guest stream-buffer errors. The reference captured 9,988 video frames at 59.94 Hz and 166.617 seconds of 48 kHz stereo PCM in the same AVI file. Capture started after emulation resumed, using FFV1 at 192 × 144 and `pcm_s16le`. An earlier capture started while emulation was paused and stalled at frame 0. The card hash was unchanged after the successful run. See `local/audio-continuity-qa/pcsx2-av-reference/` and `reference-capture-metadata.txt`. [PCSX2 capture implementation](https://github.com/PCSX2/pcsx2/blob/master/pcsx2/GS/GSCapture.cpp)

The two native cold runs replayed the same card and inputs through frame 6500 with SPU2 PCM and periodic frame captures. Visual matching located three trackside anchors independently of the sound. The table reports the original mean stereo RMS over 10 ms windows following those anchors, as a fraction of the PCSX2 mean. A later image sequence showed that the inside-wall windows diverged after a camera cut. Use the shorter same-camera comparison below for that segment. See `local/audio-continuity-qa/paired-frames.png` and `verified-anchor-audio.txt`.

| Replay location | Native frame | PCSX2 time | Window | Regular runner | Eight-sample candidate |
| --- | ---: | ---: | ---: | ---: | ---: |
| Start straight | 4379 | 115.065 s | 2.5 s | 82% | 102% |
| Grandstand turn | 4901 | 123.92 s | 3.0 s | 88% | 94% |
| Low camera at the inside wall | 5597 | 135.74 s | 2.5 s | 74% | 74% |

The native mixer sums the two core outputs after their separate master volumes. PCSX2 feeds the first core into the second core's external input and routes it through the second core's dry and wet gates. A register capture stopped at native frame 5597 and matched its image byte for byte. Core 1 had `MMIX=0x0FFC`, with the external signal routed through both dry channels at near-unity external gain (`0x7FFF`). The external wet gates were clear and both master volumes were near unity (`0x3FFF` per channel). This rules out a muted or attenuated external input at the captured frame. See `local/audio-continuity-qa/wall-routing-summary.txt`. [PCSX2 SPU2 mixer](https://github.com/PCSX2/pcsx2/blob/master/pcsx2/SPU2/Mixer.cpp) · [PCSX2 mixer gate register handling](https://github.com/PCSX2/pcsx2/blob/master/pcsx2/SPU2/spu2sys.cpp)

Repeating the eight-sample capture with `PS2_SPU2_REVERB=0` produced byte-identical frames at all three alignment points. Over the original 2.5-second native window after frame 5597, disabling native reverb lowered the stereo difference signal by only 0.13 dB. This is a comparison between the two native runs, which used the same camera cuts. See `local/audio-continuity-qa/reverb-ab-summary.txt` and `sprintcar-no-reverb/`.

A single follow-up run recorded the native mix and three diagnostic outputs from the same voice samples: limiting each core's dry voice sum before input mixing, passing core 0 through core 1's external dry input with the reference saturation order, and applying both operations. The live PCM matched the earlier eight-sample capture byte for byte, and the three alignment frames were identical. The largest shift in native stereo difference level was less than 0.002 dB in the tested windows. See `local/audio-state-qa/mix-clip-order/comparison.txt`. [PCSX2 core mixing order](https://github.com/PCSX2/pcsx2/blob/master/pcsx2/SPU2/Mixer.cpp)

At the inside wall, the native replay switched away from the low camera between frames 5626 and 5655. The PCSX2 capture kept the low camera for at least 2.90 seconds after its corresponding anchor. In the first 0.45 seconds after the anchor, both runs kept that viewpoint. The native stereo difference signal `(left - right) / 2` was 6.58 dB below PCSX2 in that shorter window, with a 6.20–6.63 dB range across offsets of two reference frames in either direction. In the other same-view windows the native side signal was 1.19 dB higher over 2.35 seconds at the start straight and 0.60 dB higher over 0.45 seconds at the grandstand. Further comparison needs closer control of the replay camera and per-voice levels. See `local/audio-state-qa/late-side-pairs.png`, `start-angle-pairs.png`, `grandstand-angle-pairs.png`, and `same-camera-mix.txt`.

A local diagnostic replaced linear voice interpolation with the four-tap coefficient table from PCSX2 2.9.172 while retaining the same decoded samples and pitch advance. The cold Sprintcar replay reached frame 6500 with zero stream-buffer warnings, matching card hashes, and byte-identical images at all three audio anchors. The largest change in the native side level across the same-camera windows was 0.11 dB. At the inside wall the level remained 6.69 dB below PCSX2. The result leaves per-voice volume, routing into the individual cores, and replay listener position as variables to compare. See `local/clio-window-qa/interpolation-comparison.txt` and `sprintcar-gaussian/`. The licensed reference table is kept in the local diagnostic directory. [PCSX2 2.9.172 interpolation table](https://github.com/PCSX2/pcsx2/blob/v2.9.172/pcsx2/SPU2/interpolate_table.h)

For the 0.45-second inside-wall clip, moving the reference audio window in 10 ms steps up to 200 ms either side of the anchor left the native side signal 4.42–7.48 dB below the reference. The inspected PCSX2 frames across this interval retain the same camera. See `local/clio-window-qa/wall-offset-range.txt` and `wall-offset-frames.png`.

Four first-order filter bands on the same clips localize most of the side difference to the low frequencies at the inside wall. The native side level was 8.47 dB lower in the lowest band with a 200 Hz edge and 2.32 dB lower in the highest band with a 4 kHz edge. In the matched start-straight and grandstand clips, the side level was higher in each of the four bands. The wall clip contained 1,850 clipped channel samples in the PCSX2 capture and 139 in the native capture. Only one matched 10 ms block avoided clipping in both captures. Applying about 1.50 times gain followed by 16-bit clipping to the native clip matched the reference clipping count to one sample and the mid level to 0.02 dB. The side level was still 3.51 dB lower. Adding the reference DC filter to that model put the side level 3.84 dB lower. See `local/audio-state-qa/same-camera-bands.txt`.

PCSX2 2.9.172 applies `clamp_mix` and DC filtering before it sends the audio to its capture. Its standard volume setting applies to the playback stream. Capture the core 1 mix before its master-volume clamp in an instrumented reference build to observe the levels with headroom. [PCSX2 2.9.172 mixer](https://github.com/PCSX2/pcsx2/blob/v2.9.172/pcsx2/SPU2/Mixer.cpp#L521-L541) · [Audio output and capture](https://github.com/PCSX2/pcsx2/blob/v2.9.172/pcsx2/SPU2/spu2.cpp#L469-L506)

A local native diagnostic recorded both SPU2 core outputs after their master volumes and before the final clamp. Summing and clipping the logged outputs reproduced all 5,190,272 stereo frames of the native WAV. The unmodified prepared runner produced the same WAV and the same images at the three camera anchors. At the inside wall, core 1 carried most of the native side energy at −21.03 dBFS, compared with −38.60 dBFS for core 0. The final native clamp changed the side level by 0.03 dB in that window. The reference still needs matching per-core samples. See `local/audio-state-qa/core-dump-summary.txt`, `cold-core-dump/`, and `cold-core-control/`.

The eight-sample candidate removed all seven stream-buffer warnings across the matched Brands Hatch Short and Silverstone National Clio Cup runs. The two runs captured about 145 and 180 seconds of chip audio. The regular runner matched all 580 and 720 recorded input checkpoints and reached both finishes. The first mismatches were at frames 4560 and 3150, within one second of loading each race checkpoint. Playback continued with the recorded inputs. The eight-sample run ended on lap 1 at Brands Hatch. Both runners reached the post-race replay at Silverstone. The Brands Hatch divergence prevents adopting the global eight-sample interval as the default. See the `brands-clio-*` and `silverstone-clio-*` folders under `local/audio-continuity-qa/`.

#### Test an early envelope read with the original mixer cadence

The first `spu2-envx-preview` experiment retained the 32-sample mixer tick and projected `ENVX` from the key-on time until the mixer took over. Its key-on timestamps reset when loading a checkpoint. The current patch keeps a separate register-visible envelope during that interval. Before a parameter write, it advances the envelope using the previous parameters so the write applies to subsequent samples. It serializes the transient envelope and time in version 10 checkpoints. The runner still loads versions 4–9, initializing their transient envelope to empty. Version 10 checkpoints require a runner that supports the new format. The patch is experimental. Apply it to the original SPU2 source from the pinned backend, alongside the reflection patch.

```powershell
git apply --no-index ..\..\patches\ps2-native-recomp-v0.0.5-spu2-envx-preview.patch
```

The narrow experiment loaded the Sprintcar replay from a copied card without stream-buffer warnings through frame 7300. Both Clio rounds reached their finishes with the recorded inputs and zero stream-buffer warnings over about 325 seconds of captured emulated audio. Frames 5000, 8200, and 10600 at Brands Hatch and frames 3460, 7300, and 10600 at Silverstone were byte-identical to the corresponding regular-runner captures. The chained input checkpoints first differed at 10260 and 6150 respectively, near the regular runner's first stream allocation warnings at 10277 and 6187. Later captures differed while showing the same progression to the finish. The card hashes in the narrow runs matched their baseline copies and both card checks passed. See the `*-clio-envx/` logs and frames under `local/audio-continuity-qa/`.

A windowed cold run of the narrow experiment opened the Sprintcar replay and continued through frame 11200. WASAPI reported zero underruns and zero dropped samples with 186.46 seconds of game audio. Audio stretching was active for part of the run, which also performed background VU1 compilation, so the device output alone does not establish frame pacing. The replay card retained its hash. See `local/audio-continuity-qa/sprintcar-envx-wasapi/trace.log` and `heard.wav`.

#### Verify the version 10 envelope checkpoint

The `ps2envxstatetest` target exercises the real IOP clock and SPU2 register API without a game disc. It saves a voice between key-on and the first mixer tick, restores it before the first register read, and verifies the retained fractional sample timing. It also covers a mid-attack register write, key-off, a direct `ENVX` write, an older version 9 checkpoint, and independent voices on both cores. All 15 checks passed with the patch. The pinned regular runner failed 10 of these checks.

The updated runner booted the Sprintcar replay from the ISO and a copied card through frame 7300 with no stream-buffer warnings. It also loaded the existing frame-6595 version 9 checkpoint and wrote a version 10 checkpoint at frame 7050. A fresh runner loaded that checkpoint and ran to frame 8080. It matched all four selected frames and all 824,000 stereo samples from the uninterrupted run's corresponding tail byte for byte. Both paths logged zero stream-buffer warnings. See `local/audio-state-qa/cold-replay/`, `loaded-replay/`, and `reloaded-v10/`.

Repeating the recorded Brands Hatch Short and Silverstone National rounds with the updated runner reached the same finishes as the first narrow experiment. All five captured frames per race, the full PCM captures, and both card hashes matched that experiment byte for byte. Neither race logged a stream-buffer warning. See `local/audio-state-qa/brands-clio-state/`, `silverstone-clio-state/`, and `envx-comparison.txt`.

#### Measure windowed replay pacing with cached vector programs

The version 10 runner cold-loaded the Sprintcar replay on the Windows 11 test machine and reached frame 10500 in windowed Direct3D 12 mode. The run reused the existing vector program cache. It logged one new VU1 compilation rounded to 0.0 seconds. `PS2_FRAME_LOG` recorded 60.00 emulated frames per second in the menu sample at frames 2500–3800. The on-track sample at frames 4450–10500 averaged 56.70 frames per second, with a 20.86 ms 95th-percentile frame interval and a 31.47 ms maximum. Frame capture selects the single-threaded window path for the entire run, so this measures that path. WASAPI reported no underruns or dropped samples. The runner stretched 52.07 seconds of game audio during the full run. The card hash was unchanged. See `local/audio-state-qa/warmed-window-pacing/summary.txt` and `trace.log`.

A paired check used the normal multithreaded window path with frame capture disabled, the same frame-6595 checkpoint, fixed Cross input, and cached vector programs. Both the regular and patched runners averaged 59.94 emulated frames per second over frames 7200–8450. Both had a 16.74 ms 95th-percentile frame interval over that range. The regular runner logged two stream-buffer warnings and the patched runner logged zero. Both delivered 30.92 seconds of audio to WASAPI with zero underruns and dropped samples. See `local/audio-state-qa/windowed-pair-summary.txt`.

A fresh process repeated the full cold run with the normal multithreaded window path and the warmed cache. It averaged 59.98 emulated frames per second from frames 4450–10500, with a 16.72 ms 95th-percentile interval and a 16.96 ms maximum in that on-track range. WASAPI received 174.80 seconds of audio with zero underruns or dropped samples. The runner stretched 0.28 seconds of game audio. The trace logged zero stream-buffer warnings and the copy of the replay card retained its initial hash. See `local/audio-state-qa/threaded-window-pacing/summary.txt` and `trace.log`.

#### Measure both Clio Cup rounds in the normal window mode

The Windows 11 runner with the version 10 SPU2 change replayed the recorded inputs for Brands Hatch Short and Silverstone National in separate processes from their grid checkpoints. Both used the normal multithreaded Direct3D 12 window path, a warmed vector program cache, and a disposable copy of the corresponding card. A version 10 snapshot near each finish was reopened in a separate headless process for frame capture. Brands Hatch showed the finish menu at 2:18.16 and 20th place. Silverstone showed the post-race replay, as in the prior verified finish run. The copied cards retained their initial hashes. See `local/clio-window-qa/brands-finish/finish.png` and `silverstone-finish/finish.png`.

| Track | Measured in-race frames | Mean emulated fps | P95 frame interval | Maximum frame interval | Observed peak working set |
| --- | ---: | ---: | ---: | ---: | ---: |
| Brands Hatch Short | 5000–13050 | 59.99 | 16.71 ms | 16.77 ms | 489.4 MiB |
| Silverstone National | 3460–13000 | 59.96 | 16.76 ms | 28.39 ms | 520.9 MiB |

The measured intervals exclude initial checkpoint restore and the requested finish snapshot. Both runs logged zero stream-buffer warnings and zero dropped WASAPI samples. Brands Hatch delivered 144.93 seconds of game audio with zero underruns. Silverstone delivered 180.18 seconds with one underrun at frame 3094, just after restoring the grid. That frame took 126.47 ms, including 116.51 ms waiting for the renderer. The queue log recorded about 0.14 seconds of silence. See `local/clio-window-qa/race-pacing.txt` and the `brands/` and `silverstone/` log directories.

Short repeats from the Silverstone grid showed renderer waits in both runners. The regular runner waited up to 59.72 ms and logged zero underruns in its repeat. The `ENVX` runner waited up to 64.07 ms and logged one underrun and about 0.07 seconds of silence. Two later repeats with the ordinary 50 ms first-play buffer completed without an underrun. This establishes an intermittent startup issue at checkpoint restore. See `local/clio-window-qa/silverstone-start-*` and `silverstone-audio-base*/`.

A local test runner paused the emulation thread for 145 ms at frame 3094 while WASAPI continued consuming audio. The ordinary 50 ms buffer reproduced one underrun in each of two trials. A 120 ms first-play threshold prevented the underrun in both paired trials, and delayed first playback from roughly 51 ms to 296 ms after the first PCM push. The threshold remains an experiment. The tests leave renderer startup and audio responsiveness to verify together. See `local/clio-window-qa/silverstone-stall-*` and `startup-buffer-fixture.txt`.

The updated runner also cold-booted the original ISO with the saved inter-round Clio card and ordinary playback buffering. The test loaded the profile, selected **Continue** for Silverstone National, and reached the track. It used no checkpoint before entering the race. The frame captured from the later verification snapshot shows 21.46 seconds of race time at frame 4491. The process reached frame 4520 with zero guest stream-buffer warnings, 75.13 seconds of audio delivered to WASAPI, zero underruns, zero dropped samples, and an unchanged card hash. The test used `--rtc 1763726400`, Start at frames 300, 600, 900, and 1200 for 15 frames, and Cross at 1590, 1860, 2080, 2300, 2670, and 3020 for 12 frames. See `local/clio-window-qa/silverstone-cold-race/trace.log` and `silverstone-cold-race-capture/on-track.png`.

#### Diagnose the Silverstone checkpoint hitch

Two short Direct3D 12 repeats per runner from the Silverstone grid checkpoint showed render-queue stalls. Almost all of the time was spent processing GIF messages for the GS. Surface acquisition, submission of the final picture, and presentation normally took less than 1 ms combined on the affected pictures. The standard runner had zero WASAPI underruns in these repeats. Both runs with the version 10 SPU2 change recorded one underrun and about 0.09 seconds of silence. The cold card boot above uses a different startup path.

A local timing build attributed most of the stall to 29 GIF Path 3 messages totaling 3,577,216 bytes per picture. The upload cache's ring eviction treated entries ending before the proposed write as overlapping it. When such an entry was in use by the current batch, the renderer submitted the batch early and retried the insertion. It made 556 early submissions per picture across four pictures. In two Direct3D 12 runs, those early submissions took about 38–47 ms per picture. Vulkan processed the same Path 3 messages more quickly and also stalled during cache population.

The [upload cache patch](../patches/ps2-native-recomp-v0.0.5-gs-upload-cache-overlap.patch) checks both ends of each range. It retains the existing wait and retry when the new range really overlaps an entry in use. After the correction, two instrumented Direct3D 12 runs and one Vulkan run made zero early submissions on those four pictures and logged zero WASAPI underruns. The first post-restore picture took 13.18–14.91 ms in Direct3D 12, compared with 60.91–62.61 ms in the paired controls. An isolated test of the actual cache code with a 128-word ring failed on its second disjoint insert in the regular build. The corrected build processed 16,000 randomized operations, including 752 wraps, 7,482 blocked writes against in-flight entries, and 8,068 successful cache lookups, with no overlapping live ranges or changed cached bytes.

The [Windows rebuild instructions](#rebuild-from-your-own-iso) apply the patch to the pinned backend before compiling. It can be combined with the reflection and SPU2 patches.

Local timings and fixture code are under `local/clio-window-qa/`. See `silverstone-hitch-{envx,stock}-*/`, `silverstone-hitch-cache-control-*/`, `silverstone-hitch-overlap-*/`, and `check-cache-ring.py`.

The version 10 SPU2 runner was tested with and without the upload cache correction, using the same checkpoints, controller inputs, and Direct3D 12 settings. Four frames each at Brands Hatch Short, Silverstone National, and Dirt Raceway 2 matched byte for byte. The corresponding WAV files also matched, totaling 1,072,000 stereo sample frames. See `local/clio-window-qa/cache-visual-*/`.

The Dirt Raceway 2 pair was repeated through the results and autosave with a fixed RTC. Five frames, the audio capture, and the newly written memory card matched byte for byte with and without the upload cache correction. See `local/clio-window-qa/cache-fixed-rtc-sprintcar-*/`.

Both complete Clio Cup replays were then run in the normal Direct3D 12 window mode with the production patch and ordinary audio settings. The first 12 Silverstone frames peaked at 16.56 ms with zero measured wait on the window thread. That interval previously peaked at 126.47 ms with 116.51 ms of renderer wait. Both runs averaged 60.00 fps over the same on-track intervals as above. Brands Hatch delivered 144.93 seconds of sound to WASAPI and Silverstone delivered 180.18 seconds, both with zero underruns or dropped samples. Neither logged guest stream-buffer warnings. Peak working sets were 463.7 MiB at Brands Hatch and 469.2 MiB at Silverstone. The finish captures matched the earlier finish captures byte for byte, and both card hashes were unchanged. The first recorded EE checkpoint differences remained at frames 10260 and 6150, respectively. See `local/clio-window-qa/upload-cache-rounds.txt`, `cache-window-brands/`, `cache-window-silverstone/`, and `cache-window-*-finish-proof/`.

The existing PowerShell launcher started a prepared copy of the patched runner with the embedded compiler path removed. It ran from the repository's parent directory with a system-only `PATH`. The windowed session attached the portable card and stopped at 720 guest frames. The subsequent fullscreen session with `-NoSave` stopped at 330 frames with no card attached. Both live translators reported no compiler, both sessions logged zero WASAPI underruns, and the saved card's hash remained unchanged. See `local/clio-window-qa/Prepared cache overlap/logs/`.

#### World Tour and championship coverage

The World Tour intro advanced to Tier 1. An isolated run of Autosport Clio Cup finished the first round at Brands Hatch Short in `2:18.16`, in 20th place. The next cold boot restored the championship from the card and started round two at Silverstone National, where the run finished 20th in `2:42.67`. Race Results reported that the top-four championship objective was no longer achievable and offered Retry. The run used scripted virtual-pad input and diagnostic checkpoints within races. Restarts between races booted from the card.

##### Verify Clio Cup qualifying across a cold start

The prepared Windows runner booted the Tier 1 profile from the reference ISO with no detected compiler. World Tour offered Normal and Hard. On Normal, Championship Details set the advancement objective at 4th place or above in the two-round Clio Cup. The test enabled the game's Qualifying setting and entered the Brands Hatch Short session.

A local driving fixture recorded a valid qualifying lap of `1:14.36` through ordinary pad input. The prepared runner replayed the input from the qualifying checkpoint. All 10 shared captured frames matched, and the replay logged no checkpoint divergence through frame 11001. The test used **Retire From Qualifying** after the valid lap. Qualifying Results placed Player One 20th, `28.23` seconds behind the prepared run's pole time of `0:46.13`. The game wrote the card through its normal autosave. The card passed `mcformat.py check`.

A cold process loaded only that card, skipped the qualifying screen, and placed the Clio in 20th on the Brands Hatch grid. Throttle input moved the car, and the card hash remained unchanged. See `local/world-tour-qa/brands-menu-options/`, `clio-prepared-qualifying/`, `clio-prepared-q-save/`, and `clio-qualified-cold/`.

A separate run reached the **Out of Fuel** menu after the timed lap. Selecting **Retire from Qualifying** preserved the `1:14.36` lap in 20th, `28.25` seconds behind the `0:46.11` pole time in that run. The game wrote a new autosave. The card passed `mcformat.py check`. A cold launch loaded the 20th-place grid with zero card writes, and the card hash stayed the same. See `local/world-tour-qa/clio-qualified-out-of-fuel-save/` and `clio-out-of-fuel-cold-grid/`.

The full ten-minute session also completed. The timer reached zero while the Clio was stationary after its opening timed lap. The game kept the car on track at `0:00.00` until it completed the current lap. Crossing the finish line opened **Qualifying Results** and wrote a new autosave with the original `1:14.36` lap in 20th place, `28.25` seconds behind pole. The prepared runner matched all 334 checkpoints and 11 shared images from the final pad recording and wrote an identical card. A cold launch from a copy of that card restored 20th on the grid with zero card writes. See `local/world-tour-qa/clio-qualifying-neutral/`, `clio-qualifying-prepared-timed-finish/`, `clio-timed-finish-result-table/`, and `clio-timed-finish-cold-grid/`.

##### Resume and finish both Clio Cup rounds

The test continued from that grid and finished Brands Hatch Short in 20th place at `1:51.09`. The uninstrumented prepared runner reproduced the first race and the newly written card from the recorded pad input. A cold launch using only that card offered qualifying for Silverstone National, confirming both the round advance and the saved qualifying setting. The test selected **Skip Session** and started the race in 20th place.

The Silverstone National race finished in 17th place at `2:12.16`. The prepared runner matched all 653 input-replay checkpoints and all 14 shared frame captures. After leaving the replay and continuing, the game wrote the card and displayed the failed championship objective. The prepared runner wrote the same card as the driving fixture. A cold launch using that card opened **Restart Points** and restored both results, with 0 points from each race. Selecting Silverstone from that menu returned to qualifying for the same round. The card passed the filesystem and ECC checks and remained byte-identical after the cold launch.

See `local/world-tour-qa/brands-qualified-prepared/`, `brands-qualified-table-verified/`, `silverstone-qualified-cold-grid/`, `silverstone-qualified-prepared/`, `silverstone-prepared-final/`, `clio-after-failed-championship/`, and `clio-cold-retry-silverstone/`.

Independent pace checks reached 14th at Brands Hatch in `1:49.42` and 9th at Silverstone in `2:12.90`. Brands Hatch fourth place was `1:44.81` in that run. The two pace checks started from different card states and belong to separate attempts. See `local/world-tour-qa/brands-room-table-verified/` and `silverstone-race-hold/`.

##### Clio Cup progression on Normal

The follow-up used the game's Normal difficulty with qualifying disabled. The local driving fixture smoothed short steering excursions in the sampled path and used nearby car positions to choose a passing line. It sent steering and throttle through the controller interface. The prepared runner later replayed the recorded pad input with the fixture absent.

Player One started 13th at Brands Hatch Short and won in `1:39.85`, with a fastest lap of `0:46.32`. Race Results awarded 24 points. The prepared runner reproduced all 12 shared images through the finish screen with no replay checkpoint divergence. Continuing to Race Results wrote the first-round autosave. A new process loaded an exact copy of that card, offered Silverstone National as the next session, and placed the Clio 14th on the grid. The cold launch recorded zero card writes. See `local/world-tour-qa/brands-pace-traffic/`, `brands-winning-replay/`, `brands-winning-result-save/`, and `silverstone-official-cold-grid/`.

The championship test carried the 24-point Brands Hatch result across a cold launch. At Silverstone National, Player One finished 9th in `2:09.39` for 4 points. **Championship Results** placed Player One tied for 2nd with 28 points, behind Briggs with 38. **Championship Completed** confirmed that the fourth-place-or-better objective had passed. Continuing opened Tier 2 at 3% World Tour progress, with **Class B 4WD Track Challenge** and **MG Team Rally Shield** available. A fresh process loaded the completed card by itself and restored both offers and the 3% progress. The game wrote zero card pages on the cold launch. The card hash was unchanged and `mcformat.py check` passed. See `local/world-tour-qa/brands-winner-early-continue/`, `silverstone-winning-grid-early/`, `silverstone-clio-cup-continuation/`, `silverstone-cup-results-first-pass/`, `clio-completed-next-tier/`, and `world-tour-tier-two-cold/`.

The prepared runner reproduced the Silverstone drive through all 652 replay checkpoints and all 18 sampled frames. Continuing through Race Results and Championship Completed reproduced a further 11 sampled frames and wrote a byte-identical completed card. The Tier 2 test then started Class B 4WD Track Challenge at Laguna GP Circuit in the Mitsubishi Lancer Evolution IV. Throttle input accelerated the car from rest to 53 mph, and the HUD advanced to lap one. See `local/world-tour-qa/silverstone-cup-prepared-replay/`, `silverstone-cup-results-verified/`, `world-tour-tier-two-first-race/`, and `tier-two-laguna-throttle/`.

The successful Silverstone route also reproduced `SOUND_SetStreamBuffer` for an occupied slot 4 and `SOUND_CloseStreamBuffer` for the same slot. Both the local driving run and its prepared replay logged the pair. A repeat with `PS2_TTY_FRAME=1` placed the messages at guest frames 4766 and 5739. The game continued through the finish and wrote the championship save. See `local/world-tour-qa/silverstone-clio-cup-continuation/trace.log`, `silverstone-cup-prepared-replay/trace.log`, and `silverstone-clio-slot-four-timing/trace.log`.

##### Trace the Silverstone stream-buffer warnings

The IOP polled core 0, voice 18 at `0xBF90012A`. At IOP cycle 2928282694 the envelope register still read `0x7FFF`. The voice reached ADPCM block `0x60CD8`, whose header had the end bit set and the repeat bit clear. A later read at cycle 2928775407 returned zero, and the guest retired the voice from slot 4. At cycle 2930005675, two guest frames later, the guest requested slot 4 for source `0x001B8950` with length `0x10000`. The allocation handler still found status 2 and rejected the request. Slot 4 was used again between the two warnings. Its close at IOP cycle 3526629435 found status 2 and ran the close path. A second close approximately 33 ms later at frame 5739 found status 0 and reported the warning. See `local/world-tour-qa/silverstone-slot-four-iop-probes/trace.log` and `silverstone-slot-four-voice-32/trace.log`.

An instrumented run from the original grid tracked the same block through DMA and voice decoding. The first two transfers to SPU2 address `0x60688` supplied flags `0x00` at `0x60CD8`. Before the third transfer, the guest's audio code at IOP PC `0x0003E254` stored `0x01` at IOP address `0x001128A1`. DMA copied `0x660` halfwords from IOP address `0x00111C00`. The decoder read the stored header and both warnings followed at their original frames. See `local/world-tour-qa/silverstone-slot-four-dma/trace.log` and `silverstone-slot-four-header-origin/trace.log`.

Two local instrumented runs used the same frame-4650 checkpoint and controller inputs. Both the 32-sample mixer and the eight-sample diagnostic ended voice 18 before the same IOP poll and logged the same warning pair at frames 4766 and 5739. The voice had been keyed on about 3.1 seconds earlier. The shortened checkpoint replay differed from the original drive's checkpoint hash from frame 4665, so the full grid-to-warning replay is the reference for the warning frames. PCSX2 2.9.172 also stops a voice when it reaches an end block with repeat clear. Keep the existing runtime behavior pending a comparison of the ADPCM data and voice position during equivalent live race inputs. [PCSX2 ADPCM block handling](https://github.com/PCSX2/pcsx2/blob/v2.9.172/pcsx2/SPU2/Mixer.cpp#L160-L217)

The game's **Save Replay** produced a Silverstone replay on a separate card. The prepared Windows runner and PCSX2 2.9.172 cold-loaded the same replay from byte-identical copies. Neither IOP log contained a stream-buffer warning during the observed playback. Both card hashes stayed unchanged. Replay cameras and sound requests can differ from the interactive race, which still reproduces the warnings. See `local/world-tour-qa/silverstone-stage-replay-slot/`, `silverstone-saved-replay-native/`, and `pcsx2-silverstone-reference/logs/emulog.txt`.

The controller recording was also translated to the PCSX2 input format and run with the same championship autosave. The observed reference drive hit the barrier on the opening lap, diverging from the original native route. The IOP log recorded zero stream-buffer warnings in this run. Compare car position and the streamed sound data before using a live attempt to draw a parity conclusion. See `local/world-tour-qa/pcsx2-silverstone-live/logs/emulog.txt`. [PCSX2 controller recording format](https://github.com/PCSX2/pcsx2/blob/master/pcsx2/Recording/InputRecordingFile.cpp#L170-L198)

The prepared runner captured 2,552,000 stereo sample frames from the live-race inputs, starting at the grid checkpoint. Each two-second window centered on one of the warning frames contained zero fully silent 50 ms intervals. This measures continuity of the combined chip output. Individual streams still need comparison. See `local/world-tour-qa/silverstone-slot-four-mix/`.

The unmodified prepared runner reproduced the warning sequence on **UK Rally 3** with its recorded driving inputs. Slot 2 entered the same retirement routine about 15 ms before its allocation hit status 2 at frame 13506. A successful close of that slot was followed about 66 ms later by the close warning at frame 13615 with status 0. The rally trace confirms the same state transitions for another slot and car. See `local/world-tour-qa/rally-tier-two-slot-two-replay/trace.log`.

##### Verify the World Tour Tier 2 finishes and inter-round save

Player One completed both Laguna GP Circuit laps in the Mitsubishi Lancer Evolution IV. The Class B 4WD Track Challenge results posted 5th in class in `3:46.15` and 13 points. The prepared Windows runner advanced from the finish to Race Results and wrote the normal card autosave. A fresh process loaded a copy of the completed card without a runner checkpoint. It offered **Nürburgring Short · Sunny** as the next race and placed the Mitsubishi 7th in class on the grid. The cold launch reported zero card writes. The card hash matched the autosave and `mcformat.py check` passed. See `local/world-tour-qa/laguna-tier-two-pace/`, `laguna-race-results/`, and `nurburgring-tier-two-cold/`.

The same Class B run finished Nürburgring Short in `3:58.45` on the HUD. A five-second penalty moved Player One to 8th in the posted Race Results with `4:03.45` and six points. The game saved the result and opened **Restart Points**. After a full restart from that card, **Restart Points** still showed fifth place and 13 points for Laguna GP Circuit and eighth place and six points for Nürburgring Short. The card hash stayed unchanged on the cold launch, which logged zero writes and passed `mcformat.py check`. See `local/world-tour-qa/nurburgring-tier-two-pace/frames/frame_18200.png`, `nurburgring-tier-two-results-menu/frames/frame_23400.png`, and `class-b-tier-two-final-cold/frames/frame_03620.png`.

The prepared runner repeated both grid-to-finish recordings with the driving fixture absent. All 943 Laguna checkpoints and 1,044 Nürburgring checkpoints matched, along with four sampled images per race. Neither run logged stream-buffer warnings. See `local/world-tour-qa/laguna-tier-two-prepared-replay/` and `nurburgring-tier-two-prepared-replay/`.

A separate Nürburgring retry from the same inter-round card finished penalty-free in `3:59.49`. The prepared runner posted 7th in class with nine points, and a cold launch restored those points alongside Laguna's 13. The cold launch wrote zero card pages and preserved the card hash. That run still missed the top-four championship objective. See `local/world-tour-qa/nurburgring-tier-two-narrow-results/frames/frame_20600.png` and `class-b-tier-two-narrow-cold/frames/frame_03620.png`.

The alternate MG Team Rally Shield offer loaded the MG ZR Super 1600 at **UK Rally 3 · Sunny**. The prepared runner reached Race Results, wrote the normal card save, and offered **Retry**. The better run placed Player One 10th in `3:35.75` against the fourth-place time of `3:17.21`. A fresh process loaded the card and showed 10th with zero points in **Restart Points**. The card hash stayed unchanged during the cold launch and `mcformat.py check` passed. The two stage runs logged allocation and close warnings on slots 2 and 6 respectively. This confirms stage finish and result handling. The top-four objective remains open. The circuit and rally driving fixtures used virtual pad input. See `local/world-tour-qa/rally-tier-two-route-run/`, `rally-tier-two-results-row/frames/frame_25800.png`, `rally-tier-two-cold/frames/frame_03620.png`, and `rally-tier-two-faster/trace.log`.

##### Verify Global GT Lights qualifying and restart

The alternate Global GT Lights event reached Oulton Park Fosters in the GT Light. The pause menu accepted Restart after confirmation, reset the timer, and returned the car to the rolling start. **Retire from Championship** returned to the main menu after confirmation. In a separate boot, enabling Qualifying in Championship Details changed the next session to Qualifying and launched the three-lap timed session. One completed lap posted a best of `2:38.42`. **Retire from Qualifying** preserved that time in Qualifying Results, which showed Player One 20th at `+1:39.73`. Continuing placed the car 20th on the rolling grid. Starting a new runner process from that card resumed the race in 20th without repeating qualifying. Retiring before setting a time placed Player One 20th with an empty time and also started the race from 20th. With qualifying disabled the earlier run started 13th.

The timed lap used an automated virtual controller driven by the car's position and heading. The regular runner replayed the recorded controller inputs and matched all 820 checkpoint hashes. Completing all three laps and testing starts from additional qualifying positions remain open. Captures are in `world-tour-gt-lights-frames.png`, `gt-lights-restart-confirm-frames.png`, `gt-lights-qualifying-on-frames.png`, `oulton-qualified-grid-frames.png`, and `oulton-unqualified-grid-frames.png` in the same test folder. See frame 2860 in `oulton-cold-grid-start-frames.png` for 20th place at zero race time on the cold boot. See `oulton-qualification-replay-verified.log` for the input replay.

The automated car incurred terminal damage on lap two in a longer qualifying attempt. Retiring from the Terminal Damage menu still showed the first lap's `+1:39.73` delta in Qualifying Results. Restarting from the same terminal-damage checkpoint began a new three-lap qualifying session with its best time cleared. The local captures are `oulton-terminal-retire-frames.png` and `oulton-terminal-new-session-frames.png`.

##### Verify Sprintcar practice and the qualifying grid

In World Sprintcar Series, a cold start from the inter-round card entered the five-lap practice session at Dirt Raceway 2 · Sunny. Restarting from the pause menu cleared the timer and returned the car to the rolling start. After a crash, the guest displayed a yellow-flag caution, a wrong-way warning, and the message to resume at race speed. End Session returned to the championship menu with Practice still selected as the next session. Skip Session advanced to the 15-minute qualifying session. Retire from Qualifying then autosaved and displayed Qualifying Results. The scripted runs used disposable card copies and matching runtime checkpoints for the menu and driving branches. See `practice-stage2-start-frames.png`, `practice-stage2-restart-frames.png`, `practice-paired-inputs-frames.png`, `practice-stage2-transition-frames.png`, `sprintcar-practice-to-qualifying-frames.png`, and `sprintcar-qualifying-results-frames.png`.

Continuing from Qualifying Results launched Stage 2 from 10th place after a qualifying run with no posted player time. A new compiler-free runner process booted from the autosaved card, restored the race and 10th place, and recorded zero card writes through the opening seconds of the race. The before and after card digests matched, and `mcformat.py check` passed. The scripted practice attempts did not post a lap time. See frames 13180 in `sprintcar-qualifying-to-race-frames.png` and 3320 in `sprintcar-qualified-cold-grid-frames.png`.

#### Prepared launcher and disc input coverage

The prepared-directory launcher was tested from the parent of the repository with a path containing spaces and a system-only `PATH`. Both a windowed launch with a portable card and a fullscreen launch with `-NoSave` exited at their requested frame limits. The runner reported zero detected C++ compilers in both runs. Launcher error checks returned exit code 2 for a missing prepared directory and 3 for a directory without a runner. The default developer launch also reached its frame limit. Logs for the prepared runs are under `local/native-toca/Windows prepared launcher test/logs/`.

The disc check rejected a short fixture and a separate fixture with the reference byte count and a different SHA-256. Both returned exit code 2 before the launcher created a temporary directory, logs, states, key settings, or a memory card. The approved ISO passed validation and reached the prepared runner's 240-frame limit. A separate fixture confirmed that SHA-256 hashing leaves the read handle open, a concurrent read succeeds, and a write request is rejected until the handle closes. The upstream `ps2discinputtest` suite also passed all 61 synthetic disc and executable checks on this Windows build.

The DVD CHD made from the reference ISO was 2,602,205,252 bytes. The launcher validated its decoded SHA-256 and reached the 300-frame limit when started from the parent directory with `-PreparedDirectory -NoSave`. A malformed CHD, a valid CHD with different contents, and a copy of the reference CHD with a damaged compressed block all returned exit code 2 before any runtime files were created. A scripted Oschersleben race check reached frame 3720 on both inputs. Frames 3230, 3310, 3390, 3490, and 3590 matched byte for byte across two ISO and two CHD runs. Frame 3700 varied between repeats within each format.

A second prepared runner used the same code with the embedded compiler hint removed. With a system-only `PATH`, both live recompilers reported that they found no C++ compiler. The launcher reached its 300-frame target and a separate CHD run reached the Oschersleben race at the 3720-frame target. Both checks used the existing Windows installation and the prepared caches. See `local/chd-dvd/chd-no-compiler-race.log` and `local/chd-dvd/Windows no compiler/logs/`.

A new build with the separate name `toca-slus-21182-chd-setup` used the CHD as its only game input. Setup verified the decoded SHA-256 and extracted the reference ELF. The 67 file entries and sector extents matched the ISO listing. The new build extracted two disc files and produced 224 C++ units. Its first launch started with empty runtime caches, used the portable C++ compiler for live VU translation, and reached the Oschersleben race at frame 3700. Both a malformed CHD and a deliberately mismatched digest aborted setup with exit code 2 before the game, generated code, or native build directory was created. The logs and captures are under `local/chd-setup/`.

A prepared copy of the new runner launched from the repository's parent directory through `Play-RecompiledToca.ps1 -Disc ... -PreparedDirectory ... -NoSave -FrameLimit 300` and exited at the frame limit. No ISO was created in the game, generated code, build or prepared runner directory. The `disc.py` synthetic ISO input, BIN/CUE, and second-layer parser tests also passed on Windows.

An independent process using the prepared runner and a copy of the existing Sprintcar autosave restored the Stage 2 race in 10th place. The run stopped at frame 4200 after 341 memory-card reads and zero writes. The card hash matched before and after. See `local/chd-setup/cold-sprintcar.log` and frame 3320 in `local/chd-setup/cold-sprintcar-frames/`.

The separate `toca-slus-21182-folder-setup` build verified and compiled from a local copy of the extracted files. The reference ELF matched, and only `SYSTEM.CNF` and the ELF were copied into the build's disc directory. Its first boot with empty caches reached the Oschersleben race at frame 3700. The Windows launcher also reached its 300-frame limit directly from `F:\`. Setup and the launcher rejected a folder with a missing file and another with a same-length edit to `SYSTEM.CNF` before creating game or runtime output. A read-only handle test on a writable fixture confirmed that writes were denied while the directory reader held it open. The updated launcher still booted the reference ISO and CHD. See `local/folder-setup/`.

A prepared directory built with `PS2_EMBED_COMPILER_PATH=OFF` was launched from the repository's parent directory. Its system-only `PATH` exposed no C++ compiler. A cold run from the extracted files restored Sprintcar Stage 2 and 10th place from a copy of the existing autosave. In a separate test, a matching card backup and the frame-8780 finish-line checkpoint produced a new autosave. The game displayed second in Stage 2, shared fourth overall with 125 points, and the Bonus 1960's Grand Prix notification. A subsequent cold process loaded the new card and displayed one cup in Pro Career. The card passed `mcformat.py check` and its digest stayed stable through the cold check. See `local/folder-setup/cold-sprintcar.log`, `local/folder-setup/cup-autosave.log`, and `local/folder-setup/cup-cold-frames/`.

Captures and logs for cold starts and mode checks are stored under `local/native-toca/portable acceptance/`. Look for `ghost-player-one-load-frames.png`, `backup-profile-recovery-frames.png`, `multiplayer-pad-two-only-frames.png`, `race-replay-cold-final-frames.png`, `world-tour-clio-cold-resume-frames.png`, and `silverstone-replay-exit-results-frames.png`. The Silverstone finish is frame 13090 in the `clio-silverstone-round-two-frames` directory under `local/native-toca/championship-cup-test/`.

### Memory cards and runtime checkpoints

Use a disposable copy of the memory-card image that belongs to a runtime checkpoint when continuing a scripted test. A checkpoint restores guest memory, which includes memory-card filesystem state, while the runner uses the card image currently attached. In one Time Trial test, a checkpoint taken before the first ghost save was combined with the updated card. The next save corrupted the ghost directory chain, and a later autosave made the scratch card unreadable to the game. Cold runs creating the first and second entries passed the card check. Repeating the lap and save with a matching card and checkpoint also passed.

## Rendering comparison

The unpatched native runtime rendered parts of the player car white at Oschersleben. At the same race time, `3:12.79`, the PCSX2 2.8.2 reference preserved the orange bumper and dark rear panel. The issue also appeared in the native software renderer and with interpreted vector programs.

### Why the rear panel turns white

Both runtimes saturate the same part of the 128 by 128 reflection target. In the native trace at frame 3309, the sprite with `ALPHA.FIX = 0xCB` changed texel `(64, 58)` to white. The PCSX2 2.8.2 software replay of the Oschersleben GS dump produced the same white texel at draw 1428. The next sprite left that texel white in both traces.

The runtimes send different vertex colors for the car's additive reflection pass. At panel pixel `(255, 336)`, the captured PCSX2 GIF packets specify RGB `(15, 15, 15)` and alpha `127` on the three vertices, across four successive fields. In the unpatched native trace for the same scene, frame 3228 and primitive 40585 use RGB `(128, 128, 128)` and alpha `127` on the corresponding panel. The large vertex color makes the white reflection texture contribute enough light to saturate the panel. The unpatched native VU1 interpreter reproduced the same vertex color as the compiled path.

In the PCSX2 software replay, draw 3007 changed the panel pixel from RGB `#3B3B56` to `#575772`. With the three captured vertex colors raised from `15` to `128`, the same draw changed the same starting pixel to `#FFFFFF`. The replay kept the texture, alpha, depth state, and the preceding draw identical. The unmodified dump also produced a dark panel at Basic and Maximum blending accuracy on Direct3D 12. These checks locate the brightness difference in the incoming vertex data for this draw. [PCSX2 GS dump replay source](https://github.com/PCSX2/pcsx2/blob/v2.8.2/pcsx2/GSDumpReplayer.cpp)

### VU1 timing fix

The car lighting program alternates two `ESUM` operations on the Elementary Function Unit (EFU). After issuing the second `ESUM` at microprogram byte address `0x2208`, it reads P with `MFP` at `0x2210`. The new sum is still in flight. The original runtime made the new result visible immediately. For one rear-panel vertex, `MFP` read about `-0.220427` instead of the preceding sum of `7.556373`. The reciprocal square root used for normalization became `2.129941` instead of `0.363784`, and the lighting computation clipped the vertex RGB to `128`. [PCSX2 EFU latency and register writeback](https://github.com/PCSX2/pcsx2/blob/v2.8.2/pcsx2/VUops.cpp), [PCSX2 ESUM latency](https://github.com/PCSX2/pcsx2/blob/v2.8.2/pcsx2/x86/microVU_Lower.inl#L531-L558)

The [runtime and recompiler patch](../patches/ps2-native-recomp-v0.0.5-toca-reflections.patch) delays P writeback in both the compiled and interpreted paths for the matching lighting program. It checks two entry addresses and three instruction pairs. Its VU1 compiler emits EFU waits and reads of the committed P value for those entries. The timed interpreter can run the program while the background compiler builds it. The new generator stamp invalidates live VU1 libraries built with the previous generator. Subsequent launches reuse the compatible libraries. The Windows launcher enables the fix. Set `PS2_TOCA_EFU_TIMING=0` before launching to compare with stock timing.

The fixed runtime emits RGB `(15, 15, 15)` at the traced rear-panel primitive. The same draw changes the native pixel from `0x804D3435` to `0x7F695051`. Both original GS reflection passes still run. The earlier experiment that skipped the gain sprite was useful for isolating the effect and has been removed from the build.

### Track and vehicle coverage

Each comparison starts from the same checkpoint with the same controller inputs. The stage and camera remain the same across the stock and fixed captures.

| Track and conditions | Car | Observed difference |
| --- | --- | --- |
| National Dirt Raceway Stage 1, sunny | WSC Sprintcar | The blue nose and wing retain their shading on the main straight. |
| National Dirt Raceway Stage 2, sunny | WSC Sprintcar | The reflection on the nose keeps its blue gradient beside the barrier. |
| Donington National, sunny | GT Light | The green and yellow body panels retain color and detail under direct light. |
| UK Rally 1, rain | Alpine A110 1600 S Group 4 | The blue rear deck, stripes, and lettering remain visible in wet conditions. |

All 15 frames on Direct3D 12 and all 15 frames on Vulkan matched their timed interpreter references byte for byte. Fourteen of the 15 fixed frames matched across APIs. One Donington frame differed by a single pixel outside the car and its shadow. A separate software-rendered trace confirmed that the two compiled lighting entries ran and that primitive 40585 still emitted RGB `(15, 15, 15)`. The direct PCSX2 packet comparison covers Oschersleben. Other tracks and materials still need verification against the original hardware or a PCSX2 replay.

Two unpaced Direct3D 12 runs per configuration used the same 413-frame Oschersleben segment, controller inputs, and warm VU1 caches. With process startup included, the timed compiled path took 4.51 to 4.52 seconds, the previous timed interpreter path took 8.04 to 8.60 seconds, and stock timing took 4.53 to 5.25 seconds. These timings measure the selected checkpoint on the Windows 11 test machine. Logs and raw timings are in `local/native-toca/reflection-validation/efu-compiled/`.

Local draw dumps and logs are in `local/native-toca/reflection-validation/`. `oescher-efu-timing-comparison.png` shows the matched Oschersleben frames, and `efu-timing-comparison.png` covers the four additional cases. Both show stock timing on the left and the fix on the right. The original pass-suppression experiment remains in `local/native-toca/reflection-pass-comparison.png`. [ps2-native-recomp v0.0.5 source](https://github.com/exoteric33/ps2-native-recomp/releases/tag/v0.0.5)
