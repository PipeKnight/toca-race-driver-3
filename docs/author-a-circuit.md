# Build an original PS2 circuit

The authored Tsukuba Circuit example is a 2,045 m recreation of the Course 2000 layout. Its centerline, road, markings, run-off, pit ribbon, collision, and race route are generated from source in this repository. It is a flat approximation with a simple perimeter barrier around the run-off. Buildings, kerbs, elevation, and a custom loading screen remain available for future authoring. The source includes no geometry, textures, or map images from a third-party game.

The authoring tool uses a local Foundry Oval pack as a base. It retains the original runtime's sunny material, weather, and loading resources from that workflow. It does not put either game's files in Git. Build the pack on your machine using your own supported discs.

## Build and run Tsukuba

Use Python 3.10 or later and TOCA Race Driver 3 `SLUS-21182` v1.02. The reference workflow uses Race Driver 2 `SLES-52638` v1.02. The base circuit importer can also discover compatible assets on other RD2 PS2 discs. The fifth circuit slot and generated selection icons are available in Windows `v0.1.0-preview.8`. [Windows preview instructions](windows-preview.md) · [RD2 donor selection](race-driver-2-import.md#convert-road-america-and-a1-ring)

Run these commands from the repository root. Set `$rd2` and `$rd3` to mounted or extracted disc directories containing their `.DIR` and `.HUG` files; the launcher itself can use an RD3 ISO. Use a new directory for each build output.

```powershell
$rd2 = 'F:\'
$rd3 = 'G:\'
$rd3Iso = 'D:\Discs\TOCA Race Driver 3.iso'
$launcher = 'D:\Games\TocaRecomp.exe'
$work = 'local\circuit-authoring'
New-Item -ItemType Directory -Force $work | Out-Null

python scripts/BuildRoadAmericaMod.py $rd3 $rd2 "$work\imports" --include-a1-ring
python scripts/BuildFoundryOval.py "$work\imports" "$work\four-courses"
python scripts/BuildAuthoredCircuit.py build tracks/tsukuba.json "$work\four-courses" "$work\tsukuba-pack" --disc $rd3
& $launcher --disc $rd3Iso --road-america "$work\tsukuba-pack" --data-dir "$work\player"
```

The output adds `tqa5/TRACK.JPK`, `tqa5/DMA1.JPK`, the `tqa5` track record (index 54), and one sunny round to the Autosport Clio Cup event list. With `--disc`, it also generates selector icons for all five added courses using the stock atlas. The four other tracks and Road America Rain, if present, keep their existing packages. Select **Simulation Modes → Free Race → Touring Car → Autosport Clio Cup**, then **Tsukuba Circuit** in the track carousel. Select the same series in **Time Trial** for lap and ghost checks. Use an unlocked profile if the event does not appear, and keep the same isolated data directory for subsequent launches.

## Design your own layout

1. Copy `tracks/tsukuba.json` to a new file. Use a printable ASCII `name` of up to 48 characters. Use `centerline` as a list of 8–256 `[x, z]` pairs in driving order (Y is height in the game). Prefer metres. The first anchor is start/finish; the tool closes the loop, so do not repeat the first point. A default flat height of 12 m can be changed with `height_m`.
2. Leave at least 90 m of nearly straight road before and after the first point for the generated pit lane. The grid reaches roughly 156 m upstream in a 20-car race. Provide enough paved width for the rear rows through any bends in that area. Add closer anchors in corners and leave clear space between nonadjacent parts of the track, including on the side where the pit lane runs. Avoid doubling back at one anchor, creating crossings, or putting a hairpin radius close to half the road width. The builder checks the sampled centerline and both road edges and rejects folded road or pit-lane segments, reporting the station near the issue. Inspect the full grid in the game to verify vehicle clearance and AI behavior.
3. Choose `road_width_m` in the range 8–24. For a sketch in arbitrary units, set `length_m` to scale the smoothed curve to a target lap length of 600–4,000 m. Omitting it keeps the measured length in metres. `sectors` sets the two split positions as fractions along the lap. Keep them in ascending driving order and outside the start/finish area. The default splits are one-third and two-thirds. Set `perimeter_wall_m` up to 1.9 m to place a visible collision barrier at the edge of the generated run-off.
4. Export a preview and inspect the road, flats, pit merge, and timing placement before packaging. `road.obj`, `ground.obj`, and `markings.obj` can be opened together in a 3D editor. `route.ail` and `drive-line.txt` are for timing inspection and game QA, respectively.

   ```powershell
   python scripts/BuildAuthoredCircuit.py preview my-circuit.json "$work\my-preview"
   python scripts/ModAssets.py route-export "$work\my-preview\route.ail" "$work\my-stations.csv"
   python scripts/BuildAuthoredCircuit.py build my-circuit.json "$work\four-courses" "$work\my-pack" --disc $rd3
   ```

5. Keep the JSON as the source of truth for the high-level tool. Editing an exported OBJ alone does not change the next build. To make a more detailed scene, use the [scene and collision authoring commands](modding.md#tracks) on a separate development copy and update collision and route whenever a driving surface moves. Rebuild the course against the original local templates; do not distribute the generated archives.

The builder authors one extra circuit per pack in `tqa5`. The flat road and run-off share one collision surface, and the optional perimeter uses a separate barrier material. The game applies its route-based lap rules. A run-off surface with different grip, kerbs, and a banked or graded road need additional collision authoring. The catalog declares the generated pit lane on the right, as seen from a car traveling in race direction.

## Test the track in game

The Windows 11 Direct3D 12 test loaded slot `tqa5` in both modes. On the installed combined pack with the revised pit route, Time Trial saved a new **1:29.77** Racing Clio lap and ghost on a card with no prior `tqa5` entry. The previous Dirt Raceway 1 ghost remained on the card. A cold launch played the new Tsukuba ghost through sample 95 of 449 without changing the card.

Free Race initially sent opponents down the pit route because its entry gate still crossed the racing surface. Moving the pit gates to the separated lane and adding a main-route approach marker fixed the false pit entries in the subsequent test. With the normal race rules enabled, a 20-car one-lap race reached Race Results. Player One finished in **1:32.06** without a time penalty; the leading opponent finished in **1:10.97**. A cold replay on the normal runner matched all **901 checkpoints** and wrote the race autosave. Pit-stop operation and weather other than Sunny are outside this test.

On the local combined Windows build with the DB5 pack also enabled, a separate 20-car Free Race classified Player One 19th in **1:32.38** and the fastest opponent first in **1:11.63**. The unmodified runner matched all **913** retained checkpoints through the lap and wrote the race autosave after continuing to Race Results. A cold launch loaded that profile without rewriting the card. This was also a Sunny test; the authored pack does not advertise wet weather.

A two-lap Free Race on the earlier route drove through the separate pit lane, counted the lap, and merged back onto the main road, but did not enter the game's pit mode. The first working pit layout used a 6.8 m paved lane, route switches, and paired stall markers. With **Pit Stops: Mandatory** in a 12-lap Free Race, the driver entered pit mode on lap two, saw the **Pit Stop** screen, and regained control on lap three. The normal runner matched all **833** retained checkpoints from the grid through this sequence. The ordinary one-lap race with the new route reproduced the previous classification images and autosave byte for byte, and the saved ghost still cold-loaded without changing its card.

A separate five-lap Free Race with **Pit Stops: Mandatory** confirmed that the stop counted. The player pitted on lap two, the mandatory-stop flag remained set at the finish, and Race Results classified the player 12th in **7:47.89**. The ordinary runner matched all **1,868** retained checkpoints before the post-race menu inputs and wrote the race autosave. The card passed filesystem and ECC checks, its existing ghost file stayed byte-identical, and the new profile cold-loaded without changing the card.

With the extended grid route, all 20 cars started within 2.51 m of the center of the 12 m paved ribbon and faced within one degree of its tangent. The opponents moved forward after the green flag. The one-lap race on Windows 11 reached Race Results and recorded Player One's **1:31.33** lap. The ordinary runner matched all **570** checkpoints from the grid and wrote an identical autosave.

A separate five-lap run with the extended grid route classified Player One 14th in **6:22.95** with Mandatory pit stops and wrote an autosave. Six opponents were disqualified in that run. The pit route itself and the start/finish and sector gates match the earlier validated profile.

The subsequent pit trace matched all 2,078 checkpoints and recorded six returns to the main route at the first pit gate among four AI cars. Some of those cars tried again on later laps. One reproduced return occurred 61.2 m before the finish line, while the car was still at 5.76 m from the racing centerline and outside the pit entry corridor. Widening the corridor to 6.4 m from the centerline reproduced the same return. A 140 m approach experiment moved the route switch into the preceding bend and left several cars on lap zero while the leaders pitted. The checked-in layout uses the verified 90 m approach. Its route audit found upward-facing collision at every sampled main, pit, and grid station.

The builder sets the first pit gate 55 m before the finish line and widens the inner edge of both the paved approach and the route corridor around it. In a replay from frame 16,400, the original AI driver selected the pit route from the same position on frame 16,405. With both changes applied it cleared the gate and reached the game's pit service state on frame 16,536.

The full five-lap replay with the revised gate and ten stalls matched 1,645 checkpoints. The player pitted on lap two, finished 13th in **6:22.58**, and autosaved. A cold restart preserved the card's SHA-256. The trace recorded one early gate return, down from six. Six opponents still received DSQ. The game's team assignments used stall indices 10–14 for six AI cars, beyond the ten stalls in that route. The current authoring tool generates all sixteen numbered stop zones with a four-metre start-to-end interval and six metres between starts.

A new five-lap Windows 11 race with the sixteen-stall route classified all 20 cars without a disqualification. The player completed the mandatory stop on lap two and finished 20th in **6:35.49**, with a fastest lap of **1:13.81**. Race Results followed an autosave with 772 memory card page writes. A cold restart read the card and left its SHA-256 unchanged.

The perimeter barrier addresses a separate Time Trial test in which a straight-line overshoot at the end of the run-off sent the car below the collision mesh. With the barrier installed, the same inputs hit the boundary and stopped the car on the terrain. A separate Time Trial recorded and saved a **1:29.74** ghost. A cold launch restored that best time and left every byte of the test card unchanged. The barrier build also repeated the one-lap Free Race from power-on through its autosave.

- Start with a one-lap sunny Free Race. Check the grid orientation and that opponents move through each bend and complete a lap without leaving the road or getting stuck. Look for clipping, wrong-way warnings, and unexpected course-cut penalties. Record the classification screen and confirm that the game autosaves.
- For a pit test, choose at least five laps and **Pit Stops: Mandatory** in Championship Setup. Follow the separated right-hand lane on lap two, verify the game takes over, and resume driving after it returns control. A counted lap in the pit lane is not enough: verify the final classification.
- In Time Trial, cross the start and both sector markers in order and finish a clean flying lap. A lap in the profile records does not by itself prove that the ghost was recorded. Choose **Pause → End Session**, accept the prompt, and let the autosave finish before quitting. Start again with the same data directory and load the ghost for Tsukuba. Check that it drives through the actual corners and does not appear under another track.
- Repeat with a stock course and, if using the combined pack, a previously installed add-on course. Confirm no old track or saved ghost has changed. Keep the exact build, configuration, and recorded input with any verification report. Test only the revisions and platforms you intend to list as supported.

## How the tool fits the formats

The centerline is smoothed, then sampled by arc length about every 8 m. Adjacent offsets become the visible road and paint. A separate tiled mesh is used for flat collision. The `AILD` v9 file contains main, pit, and start/finish auxiliary sections. The auxiliary placement lanes sit one-sixth of the road width to either side of the center and extend at least 176 m before the finish line. The main section includes start/finish code `6` and the two code-`2` timing splits with arguments `0` and `1`. The existing scene writer supplies the platform-specific VIF draw commands. The collision writer rebuilds the spatial grid and checks its cache capacity. The pack builder rejects payloads that exceed the reference package extents.

Use this arrangement for flat, closed circuits. A road-course loop with intersections, a rally stage, or a multi-layout venue needs additional data and runtime tests. See [Foundry Oval timing and ghost verification](ps2-disc-and-archives.md#foundry-oval-time-trial-sectors) for the development test that established the split sequence.
