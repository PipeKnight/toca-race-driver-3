# SLUS-21182 v1.02 coverage inventory

This inventory comes from the reference North American PS2 image. It provides the cases to exercise during acceptance. A configuration in the inventory records what the disc defines. The runtime evidence records what the Windows build has run.

Run the following from the project root with Python 3.11 or later. The script verifies the ISO SHA-256, opens the image read-only, and writes the inventory to standard output.

```powershell
New-Item -ItemType Directory -Force .\local | Out-Null
python .\scripts\InspectCoverage.py 'C:\path\to\your copy.iso' > .\local\coverage.json
```

The Windows developer build also provides Python at `.tools/ps2-native-recomp-0.0.5/tools/portable/python/python.exe`.

## Disc coverage

| Source | Inventory | Acceptance use |
| --- | --- | --- |
| Championship definitions | 204 configurations, including 89 Career and 115 Custom, with 993 round definitions | Use the configuration ID, track ID, car type, and any applicable objective, weather, starting procedure, or pit-stop rule to identify the test. |
| World Tour progression | Six gates, 33 levels, and 88 championship entries | The levels include choices. Verify progression through the final gate and exercise the alternate events as individual compatibility cases. |
| Pro Career progression | Classics, GT, Honda, Off Road, Open Wheel, Oval, Palmer, and Touring definitions, plus the disc's FT and Toy Slot gate files | Verify visibility, objectives, and unlocks in each discipline with its applicable entry conditions. |
| Track information | 80 records, 78 referenced by championship rounds | Track ID identifies each layout. `mon2` and `mon3` also have metadata records and need their availability verified separately. |
| Checksum catalog | 115 championships, 78 tracks, 577 roster entries, and 82 distinct vehicle type entries | Use car type IDs for vehicle coverage and compare the separate runtime roster and round definitions where they have different scope. |

The World Tour gate begins with `first`, which the inventory resolves to the intro DTM event `1st__` at `osc1`. The final gate points to the WilliamsF1 Team Challenge `forw_`. Its rounds specify grid starts and mandatory pit stops. The global round inventory also includes rolling and mid-race starts, circuit and rally disciplines, and Sunny, Rain, and Storm configurations. Verify the available conditions that each event actually exposes in the game.

The inspected ISO offsets are `0x68390800` for track information, `0x68432800` for the gate package, `0x68438000` for the championship package, and `0x669d0000` for the checksum index. Offsets and structure checks in the script apply to the exact ISO identified above.

## Runtime coverage on Windows 11

| Mode or feature | Observed coverage | Remaining verification |
| --- | --- | --- |
| World Tour | The intro DTM event advances to Tier 1. Autosport Clio Cup completed on Normal, tied for 2nd with 28 points, and restored both Tier 2 offers after a cold boot. Class B 4WD Track Challenge `secb1` finished both rounds across a cold start in the Mitsubishi Lancer Evolution IV. Cold launches restored 5th and 13 points for Laguna GP Circuit and both the penalized 8th place and the penalty-free 7th place for Nürburgring Short in separate saves. MG Team Rally Shield `mgra_` finished UK Rally 3 in the MG ZR Super 1600 and restored 10th in Restart Points. Clio qualifying restored the Brands Hatch grid after a complete ten-minute session and after separate retirement and out-of-fuel tests. Global GT Lights `gtli_` restarted from pause, retained a timed qualifying lap, and restored the Oulton Park Fosters grid after a cold start. | Meet a Tier 2 objective, verify starts from additional qualified positions, and advance World Tour to the final gate. |
| Pro Career | World Sprintcar Series `sprif` completes both rounds with autosave and inter-round resumption. A cup and the two associated unlocks survive cold boot. Stage 2 practice, restart, caution flags, and qualifying entry have runtime evidence. US SpeedTruck Challenge `ctruf` completes all four rounds, restores points between races, and returns to championship selection after the final cold boot. | Cover the other championships, disciplines, and their objectives. |
| Free Race | Bonus 1960's Grand Prix `60gpb` opens and loads the Donington GP Circuit grid with a Lotus Type 49 after the award and restart. | Verify more race formats and finish flows. |
| Time Trial | World Sprintcar Series loads both National Dirt Raceway stages. Ending the Stage 2 session saved Player One's `0:30.87` lap. A fresh launch from a byte-identical copy restored the profile and loaded the saved ghost. | Exercise more ghost and record types across other disciplines. |
| Load Replay | A World Sprintcar Series replay saved from Race Results and played back after a new launch. Stereo PCM was captured from both the native runner and PCSX2 2.8.2 using matching card copies. A saved Silverstone Clio Cup replay played on the native runner and PCSX2 2.9.172 with unchanged cards and zero stream-buffer warnings in either log. | Resolve the live-race stream-buffer warnings and verify the replay mix, playback controls, and replays across other disciplines. |
| Multiplayer | National Dirt Raceway Stage 1 renders two local split-screen views. Player 2 joins and accelerates with a separate virtual guest pad. | Exercise physical controllers and finish a split-screen race. |

See the [acceptance checklist](acceptance-checklist.md) and [Windows verification evidence](native-recompilation.md).
