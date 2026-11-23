@{
    SetupRevision = 2
    Backend = @{
        File = 'ps2-native-recomp-v0.0.5.zip'
        Url = 'https://github.com/exoteric33/ps2-native-recomp/releases/download/v0.0.5/ps2-native-recomp-v0.0.5.zip'
        SHA256 = 'CC2C7478463A967A80D058FEAC9359EFCE74683AEE8805E5E8FA4AD1C8C84CD0'
        Directory = 'ps2-native-recomp-0.0.5'
    }
    Chd = @{
        File = 'libchdr-v0.3.0.tar.gz'
        Url = 'https://codeload.github.com/rtissera/libchdr/tar.gz/93d8c239ff0d4e8d7722985992649fce12d2463b'
        SHA256 = 'F38FB1B3E907C8927271A57AD6E3C02347EAA2D5803F910880B4B3C3021B3657'
        Directory = 'libchdr-93d8c239ff0d4e8d7722985992649fce12d2463b'
    }
    Patches = @(
        'ps2-native-recomp-v0.0.5-toca-reflections.patch'
        'ps2-native-recomp-v0.0.5-gs-upload-cache-overlap.patch'
        'ps2-native-recomp-v0.0.5-spu2-envx-preview.patch'
        'ps2-native-recomp-v0.0.5-spu2-checkpoint-blocks.patch'
        'ps2-native-recomp-v0.0.5-dvd-chd.patch'
        'ps2-native-recomp-v0.0.5-dvd-chd-setup.patch'
        'ps2-native-recomp-v0.0.5-dvd-folder.patch'
        'ps2-native-recomp-v0.0.5-windows-portable.patch'
        'ps2-native-recomp-v0.0.5-windows-build-paths.patch'
        'ps2-native-recomp-v0.0.5-road-america.patch'
        'ps2-native-recomp-v0.0.5-dtm-mod.patch'
        'ps2-native-recomp-v0.0.5-a1-ring.patch'
        'ps2-native-recomp-v0.0.5-road-america-rain.patch'
        'ps2-native-recomp-v0.0.5-fourth-track-slot.patch'
        'ps2-native-recomp-v0.0.5-dtm-variant.patch'
        'ps2-native-recomp-v0.0.5-dtm-free-race.patch'
        'ps2-native-recomp-v0.0.5-dtm-converted-model.patch'
        'ps2-native-recomp-v0.0.5-dtm-variant-sound.patch'
        'ps2-native-recomp-v0.0.5-dtm-variant-type.patch'
    )
    DependencyArchives = @(
        'busybox-w64u-FRP-6075-g169694ebd.exe'
        'cmake-4.4.4-windows-x86_64.zip'
        'dxc_2026_09_29.zip'
        'llvm-mingw-20260908-ucrt-x86_64.zip'
        'MinGit-2.56.0.2-64-bit.zip'
        'ninja-win.zip'
        'python-3.13.16-embed-amd64.zip'
        'SDL2-devel-2.32.10-mingw.zip'
        'wgpu-windows-x86_64-gnu-release.zip'
    )
}
