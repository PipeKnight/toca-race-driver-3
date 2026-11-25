# TOCA Race Driver 3 (PS2) Project Rules

These rules apply throughout the repository. The launch, packaging, and verification requirements apply as their respective components are introduced.

## Project language

Write and maintain all project documentation in English, including plans, research notes, build instructions, and release notes. Use English for code comments and docstrings.

## Commit identity

Use `PipeKnight <34810566+PipeKnight@users.noreply.github.com>` as the author and committer for automated commits made on behalf of this repository's owner.

## Windows release downloads

Ship future Windows releases as a single portable `.exe` with its setup files bundled. Players should be able to launch it directly without extracting a ZIP or installing it system-wide. Preserve the existing portable data and setup directory options.

## Import acceptance

Keep an individual Windows test record for every imported car, livery, circuit layout, and offered weather option. Run both the asset audit and the applicable in-game checks before marking an import verified. Record defects, untested cases, and the exact pack used for evidence. Apply the [import acceptance checklist](docs/acceptance-checklist.md#import-acceptance-by-asset) when reviewing a new import or changing shared conversion code.

## Six recommendations from the open letter

1. **One entry point.** Ship one user-facing executable per platform and architecture. Have it handle first-run setup when needed and launch the game directly once setup is complete. Players and third-party launchers use the same executable. Internal helper processes and separate developer builds are permitted.
2. **Portable by default.** Keep settings, saves, caches, logs, extracted assets, setup output, updates, and temporary files inside the selected game directory. Default to the directory containing the executable, regardless of the current working directory. For AppImage builds, accept an explicit data directory, including one on another drive or SD card. Use AppData, Documents, the system temporary directory, or XDG directories only in an explicitly selected system mode, such as a package-manager installation.
3. **Two Linux release formats.** Release an AppImage and a ready-to-run `.tar.gz` for the same version. The archive must work after extraction, including when installed by a launcher running inside Flatpak. Verify that it contains the executable and its required dependencies.
4. **CLI settings and launch options.** Provide stable flags for fullscreen and windowed modes, the path to a disc image or extracted files, data and setup directories, direct launch, and other user settings. Document the flags in `--help`. Provide clear messages and exit codes so automation can run without mandatory windows or dialogs.
5. **Native Linux support.** Keep the Linux build working from the first changes that introduce platform dependencies. Test Windows and Linux in CI and verify release startup on SteamOS or Bazzite. If a native Linux build is temporarily unavailable, test and document how to run the game with Proton.
6. **Community collaboration.** Before starting the project or a major subsystem, check whether similar work already exists. Propose collaboration when there is a suitable project. Consult the maintainers of relevant tools early on open packaging or integration questions, for example in the RecompLauncher developer channel. Keep a public roadmap and update the project status as work progresses.

## Additional recommendations from the discussion

7. **Clear disc requirements.** Accept disc images and directories of extracted files. Document supported regions, serial numbers, revisions, and checksums. Explain whether the original disc is needed on every launch or only for setup, what setup produces, and how much disk space it needs. Open the original read-only and reuse prepared data on subsequent launches. Support reading compressed images such as CHD without requiring a second full disc image. Account for the languages available in PAL releases when expanding regional support.
8. **Ready to run without development tools.** Include required dependencies or perform setup automatically using the player's legally obtained copy. Make the SteamOS release runnable without installing a compiler or CMake. Keep Git and release contents limited to materials the project has permission to distribute. Extract the original ELF and game assets locally from the user's disc. For PCSX2 verification, use a BIOS dumped from your own console.
9. **User-controlled updates.** Provide in-app updates and allow users to skip or disable them when using an external launcher. Preserve settings and saves during updates and remove obsolete application files. Verify the update flow in SteamOS Gaming Mode and under Proton when supported. Document the stable entry point, data paths, and a way for external launchers to check the installed version.
10. **Controls and exit.** Support launching, navigating the main menus, and exiting with a controller. On PC, support mouse and keyboard input, remappable controls, prompts for the current input device, and a borderless window by default with a way to switch modes. Store progress in ordinary local files and make saving and quitting available from within the game.
11. **Performance and compatibility.** Prioritize stable races, reliable saves, and predictable performance before adding advanced mods and effects. If shader compilation causes stutter, offer user-initiated precompilation and reuse the cache. Consider devices without Vulkan when choosing a graphics API and provide OpenGL support if the chosen stack permits it. Consider optional CRT effects and `.slang` presets once basic rendering is stable.
12. **Verifiable release status.** For each release, publish the tested platforms and disc revisions, known limitations, and current level of completion. Document clean installation, first launch, subsequent launches, updates, and removal of a portable copy. Start verification with `SLUS-21182` version `1.02`. Verify every additional revision individually before listing it as supported.

[Open letter and discussion on r/decomps](https://www.reddit.com/r/decomps/comments/1xyz4xo/an_open_letter_to_recompdecomp_devs_can_we_agree/)
