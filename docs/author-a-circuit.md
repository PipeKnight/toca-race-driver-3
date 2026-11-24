# Build an original PS2 circuit

The authored Tsukuba Circuit example is a 2,045 m recreation of the Course 2000 layout. Its centerline, road, markings, run-off, pit ribbon, collision, and race route are generated from source in this repository. The example is a flat approximation, not a surveyed replica. It does not include buildings, kerbs, elevation, barriers, or a custom loading screen. It does not include geometry, textures, or map images from a third-party game.

The authoring tool uses a local Foundry Oval pack as a base. It retains the original runtime's sunny material, weather, and loading resources from that workflow. It does not put either game's files in Git. Build the pack on your machine using your own supported discs.

## Build and run Tsukuba

Use Python 3.10 or later, Race Driver 2 `SLES-52638` v1.02, and TOCA Race Driver 3 `SLUS-21182` v1.02. Rebuild the Windows launcher from the current source manifest: earlier released previews only know the first four extra slots. See [Windows preview build instructions](windows-preview.md). A prepared developer runner with the fifth-slot patch can also launch the pack with the same `--road-america` option.

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
python scripts/BuildAuthoredCircuit.py build tracks/tsukuba.json "$work\four-courses" "$work\tsukuba-pack"
& $launcher --disc $rd3Iso --road-america "$work\tsukuba-pack" --data-dir "$work\player"
```

The output adds `tqa5/TRACK.JPK`, `tqa5/DMA1.JPK`, the `tqa5` track record (index 54), and one sunny round to the Autosport Clio Cup event list. The four other tracks and Road America Rain, if present, keep their existing packages. Select **Simulation Modes → Free Race → Touring Car → Autosport Clio Cup**, then **Tsukuba Circuit** in the track carousel. Select the same series in **Time Trial** for lap and ghost checks. Use an unlocked profile if the event does not appear, and keep the same isolated data directory for subsequent launches.

## Design your own layout

1. Copy `tracks/tsukuba.json` to a new file. Use a printable ASCII `name` of up to 48 characters. Use `centerline` as a list of 8–256 `[x, z]` pairs in driving order (Y is height in the game). Prefer metres. The first anchor is start/finish; the tool closes the loop, so do not repeat the first point. A default flat height of 12 m can be changed with `height_m`.
2. Leave at least 90 m of nearly straight road before and after the first point for the grid and generated pit lane. Add closer anchors in corners and leave clear space between nonadjacent parts of the track, including on the side where the pit lane runs. Avoid doubling back at one anchor, creating crossings, or putting a hairpin radius close to half the road width. The smoothing step changes the curve between anchors. The builder checks the sampled centerline and both road edges and rejects folded road or pit-lane segments, reporting the station near the issue. It does not check clearance for obstacles or verify AI behavior.
3. Choose `road_width_m` in the range 8–24. For a sketch in arbitrary units, set `length_m` to scale the smoothed curve to a target lap length of 600–4,000 m; omitting it keeps the measured length in metres. `sectors` sets the two split positions as fractions along the lap; keep them in ascending driving order and outside the start/finish area. The default splits are one-third and two-thirds.
4. Export a preview and inspect the road, flats, pit merge, and timing placement before packaging. `road.obj`, `ground.obj`, and `markings.obj` can be opened together in a 3D editor. `route.ail` and `drive-line.txt` are for timing inspection and game QA, respectively.

   ```powershell
   python scripts/BuildAuthoredCircuit.py preview my-circuit.json "$work\my-preview"
   python scripts/ModAssets.py route-export "$work\my-preview\route.ail" "$work\my-stations.csv"
   python scripts/BuildAuthoredCircuit.py build my-circuit.json "$work\four-courses" "$work\my-pack"
   ```

5. Keep the JSON as the source of truth for the high-level tool. Editing an exported OBJ alone does not change the next build. To make a more detailed scene, use the [scene and collision authoring commands](modding.md#tracks) on a separate development copy and update collision and route whenever a driving surface moves. Rebuild the course against the original local templates; do not distribute the generated archives.

This first tool authors **one** extra circuit per pack in `tqa5`; it does not dynamically add unbounded slots or place multiple authored layouts side by side. The flat proof of concept uses one physical collision surface for the road and run-off. The game still applies its route-based lap rules. Surfaced run-off, kerbs, barriers, and a banked or graded road need explicit collision work. The catalog declares the generated pit lane on the right, as seen from a car traveling in race direction. The generated pit markers are not a substitute for validating pit entry, exit, and stops in a race.

## Test the track in game

The Windows 11 Direct3D 12 test loaded slot `tqa5` in both modes. Time Trial completed a **1:29.77** Racing Clio lap and displayed its ghost on the next lap. Ending the session saved the `tqa5` lap record. A cold launch with the current track loaded and played that ghost through sample 54 of 449, with the memory card unchanged.

Free Race initially sent opponents down the pit route because its entry gate still crossed the racing surface. Moving the pit gates to the separated lane and adding a main-route approach marker fixed the false pit entries in the subsequent test. With the normal race rules enabled, a 20-car one-lap race reached Race Results. Player One finished in **1:32.06** without a time penalty; the leading opponent finished in **1:10.97**. A cold replay on the normal runner matched all **901 checkpoints** and wrote the race autosave. Pit-stop operation and weather other than Sunny are outside this test.

On the local combined Windows build with the DB5 pack also enabled, a separate 20-car Free Race classified Player One 19th in **1:32.38** and the fastest opponent first in **1:11.63**. The unmodified runner matched all **913** retained checkpoints through the lap and wrote the race autosave after continuing to Race Results. A cold launch loaded that profile without rewriting the card. This was also a Sunny test; the authored pack does not advertise wet weather.

A two-lap Free Race on the earlier route drove through the separate pit lane, counted the lap, and merged back onto the main road, but did not enter the game's pit mode. The current builder aligns the route's two pit boundaries with the 6.8 m paved lane and adds route switches and paired stall markers. With **Pit Stops: Mandatory** in a 12-lap Free Race, the driver entered pit mode on lap two, saw the **Pit Stop** screen, and regained control on lap three. The normal runner matched all **833** retained checkpoints from the grid through this sequence. The ordinary one-lap race with the new route reproduced the previous classification images and autosave byte for byte, and the saved ghost still cold-loaded without changing its card. Whether the game credits the stop at the end of a longer race is a separate check.

- Start with a one-lap sunny Free Race. Check the grid orientation and that opponents move through each bend and complete a lap without leaving the road or getting stuck. Look for clipping, wrong-way warnings, and unexpected course-cut penalties. Record the classification screen and confirm that the game autosaves.
- In Time Trial, cross the start and both sector markers in order and finish a clean flying lap. A lap in the profile records does not by itself prove that the ghost was recorded. Choose **Pause → End Session**, accept the prompt, and let the autosave finish before quitting. Start again with the same data directory and load the ghost for Tsukuba. Check that it drives through the actual corners and does not appear under another track.
- Repeat with a stock course and, if using the combined pack, a previously installed add-on course. Confirm no old track or saved ghost has changed. Keep the exact build, configuration, and recorded input with any verification report. Test only the revisions and platforms you intend to list as supported.

## How the tool fits the formats

The centerline is smoothed, then sampled by arc length about every 8 m. Adjacent offsets become the visible road and paint. A separate tiled mesh is used for flat collision. The `AILD` v9 file contains main, pit, and start/finish auxiliary sections; the main section includes start/finish code `6` and the two code-`2` timing splits with arguments `0` and `1`. The existing scene writer supplies the platform-specific VIF draw commands; the collision writer rebuilds the spatial grid and checks its cache capacity. The pack builder rejects payloads that exceed the reference package extents.

Use this arrangement for flat, closed circuits. A road-course loop with intersections, a rally stage, or a multi-layout venue needs additional data and runtime tests. See [Foundry Oval timing and ghost verification](ps2-disc-and-archives.md#foundry-oval-time-trial-sectors) for the development test that established the split sequence.
