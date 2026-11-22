# TOCA Race Driver 3 PS2 recompilation

An experimental project to run the original PlayStation 2 release of TOCA Race Driver 3 on modern systems. The Windows developer build translates the Emotion Engine executable from a player's own disc and reads game resources from that disc at runtime. It uses [ps2-native-recomp v0.0.5](https://github.com/exoteric33/ps2-native-recomp/releases/tag/v0.0.5).

The current test target is the North American PS2 release, `SLUS-21182` v1.02. The Windows 11 build has reached races, saved championship results, and restored progress after restarting. Full-game acceptance and additional platforms remain in progress.

- [Windows preview launcher and first-run setup](docs/windows-preview.md)
- [Developer build and verification](docs/native-recompilation.md)
- [Linux developer build](docs/linux-development.md)
- [Supported disc and archive research](docs/ps2-disc-and-archives.md)
- [Project plan](PLAN.md) and [acceptance checklist](docs/acceptance-checklist.md)

This repository contains project documentation, build tooling, and patches. Supply your own disc data when building and running the game. The [upstream license notice](patches/LICENSE) applies to upstream code in the patches.
