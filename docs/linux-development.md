# Native Linux developer build

Build the x86-64 runner from a local copy of the North American PS2 disc `SLUS-21182` v1.02. The setup below uses Ubuntu 24.04 and the patch order of the [Windows preview](windows-preview.md). It reads the original ISO in place and creates the boot ELF and translated code in the local build directory.

## Dependencies

Use Bash, Git, Clang 18 with a C++ standard library that provides `<format>`, CMake, Ninja, Python 3, curl, unzip, and the SDL2 development libraries. For a graphical run, use a Vulkan driver and the local desktop or WSLg display. On Ubuntu 24.04, the build used the following packages in addition to the existing Git, GCC 13 C++ standard library, Python 3, and Mesa Vulkan drivers.

```sh
sudo apt-get install --no-install-recommends clang-18 cmake ninja-build libsdl2-dev unzip
```

## Build from the ISO

Download the `Backend` ZIP and `Chd` tarball identified in the [source manifest](../scripts/WindowsPreviewSources.psd1). Verify both SHA-256 hashes before extraction. Put the archives in `.tools/downloads` under the project directory. Set `disc` to the absolute path to your own ISO. Compare its SHA-256 with the [disc requirements](ps2-disc-and-archives.md#reference-disc).

Run these commands from the project directory with a fresh build folder. Normalize line endings in the upstream ZIP's source files before applying the project patches. Under WSL, placing `work` in a persistent directory on the Linux filesystem avoids the slow archive and link steps observed under `/mnt/c` and keeps the runner after WSL restarts. The ISO can stay on its mounted Windows drive.

```sh
repo=$(pwd)
disc='/absolute/path/to/TOCA Race Driver 3.iso'
work="$repo/local/linux-dev"
mkdir -p "$(dirname "$work")"
mkdir "$work" || exit 1
unzip -q .tools/downloads/ps2-native-recomp-v0.0.5.zip -d "$work"
cd "$work/ps2-native-recomp-0.0.5"
find . -type f \( -name CMakeLists.txt -o -name '*.c' -o -name '*.h' -o \
    -name '*.cpp' -o -name '*.hpp' -o -name '*.inc' -o -name '*.sh' \) \
    -exec sed -i 's/\r$//' {} +
tar -xf "$repo/.tools/downloads/libchdr-v0.3.0.tar.gz"

for patch in toca-reflections gs-upload-cache-overlap spu2-envx-preview \
    spu2-checkpoint-blocks dvd-chd dvd-chd-setup dvd-folder windows-portable; do
    git apply --no-index "$repo/patches/ps2-native-recomp-v0.0.5-$patch.patch" </dev/null || exit 1
done

CXX=clang++-18 PS2_PORT_DIRECT_ISO=1 \
    PS2_LIBCHDR_DIR="$PWD/libchdr-93d8c239ff0d4e8d7722985992649fce12d2463b" \
    bash scripts/port.sh toca-slus-21182 "$disc" --native-only --no-explore
```

The upstream setup downloads and verifies the pinned Linux `wgpu-native` archive. To run the local build, keep using the same ISO and choose a writable data directory for the card, settings, and caches.

```sh
data="$work/player"
mkdir -p "$data/temp"
TMPDIR="$data/temp" PS2_TOCA_EFU_TIMING=1 PS2_VU_CXX="$(command -v clang++-18)" \
    ./build/native-toca-slus-21182/ps2run --disc "$disc" --window \
    --game-dir "$data" --memcard "$data/toca-slus-21182.ps2"
```

Run the SPU2 checkpoint tests from the native runtime build directory.

```sh
runtime=$(find build -maxdepth 1 -type d -name 'runtime-native-*' -print -quit)
ninja -C "$runtime" ps2envxstatetest
"$runtime/ps2envxstatetest"
```

## Verification

Ubuntu 24.04.5 under WSL2 built the full eight-patch series with Clang 18.1.3. The build translated 224 units and produced a native Linux x86-64 ELF. It extracted the reference boot ELF from the original ISO and created no duplicate disc image. The native runtime passed all 21 SPU2 tests.

The fully patched runner opened a WSLg window using Vulkan through llvmpipe and played audio through the WSLg PulseAudio sink. It reached 780 guest frames and exited at the requested limit. The sink received 12.80 seconds of audio with zero queue underruns and zero dropped samples.

An earlier WSLg run created Player One on a fresh memory card with the SDL virtual controller. Its extended windowed reload reached the profile confirmation before the time limit. The fully patched runner cold-loaded a copy of that card, confirmed the profile load, and reached the Oschersleben race in headless frame capture with the CPU renderer. It exited at 3,850 frames with zero card writes and the same card SHA-256.

After a rebuild, the verified ELF was copied into the project workspace. The same executable also opened the DVD CHD and the extracted disc directory in WSLg. Both runs reached 780 frames with zero audio queue underruns or dropped samples. Full-volume digest verification in WSL remains pending after the 180-second CHD streaming check timed out.

The build and launch evidence is in `local/linux-qa/`. Hardware rendering, physical input, clean SteamOS or Bazzite installation, and the AppImage and `.tar.gz` packages remain open in the [acceptance checklist](acceptance-checklist.md#3-packaging-and-platform-support).
