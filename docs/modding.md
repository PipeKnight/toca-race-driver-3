# Modding the PS2 version of TOCA Race Driver 3

This guide uses the North American PS2 disc `SLUS-21182` v1.02 and the portable recompilation. Start with your own disc files. A track and a car each load several related resources, so keep the extracted package and its companion files together until you know which member you want to change. [Reference disc](ps2-disc-and-archives.md#reference-disc)

## Inspect and extract files

Run these PowerShell examples from the repository root with Python 3.10 or later. Set `$disc` to a mounted or extracted RD3 DVD directory containing `RDH.DIR` and `RDH_*.HUG`. The tool verifies the directory fingerprint before reading any of the known disc ranges. You can also open an extracted `BIGF` or `JPAK` file read-only through `--file`.

```powershell
$disc = 'D:\Discs\TOCA Race Driver 3'
$work = 'local\my-mod'
New-Item -ItemType Directory -Path $work -Force | Out-Null
python scripts/ModAssets.py list --disc $disc --package oschersleben-track
python scripts/ModAssets.py list --disc $disc --package dtm-cars --inside dtmx_00.big
```

Each listing shows the member's package-relative offset, disk size, decoded size, and encoding. `extract` returns the decoded file and prints its SHA-256. Use `--inside` once for each container between the outer package and the file. `replace` writes a new copy of the outer package with the same total length. A nested JPAK can grow when its enclosing member or outer JPAK has room. The tool updates offsets and lengths when it repacks the entries. A BIGF edit must fit the original member slot. Use a new output filename for every command.

| Container | What to look for |
| --- | --- |
| `RDH.DIR` and `RDH_*.HUG` | The DVD's file lookup table and the three sector-addressed archives. Named `--package` options cover the verified ranges for this revision. |
| Indexed PS2 `BIGF` | Named entries with lengths and offsets relative to a common data base. Members can themselves be packages. |
| PS2 `JPAK` | Named entries with package-relative offsets and stored and expanded lengths. Members of equal stored and expanded length are raw, even where the LZSS flag is present. |

The generic archive commands cover these observed PS2 layouts. For offsets and directory fields, see the [archive research](ps2-disc-and-archives.md).

To work with a newly traced package, substitute `--range HUG SECTOR BYTES` for `--package`. Use decimal values for the HUG index, the sector relative to that HUG, and the requested byte count. For example, `--range 2 187552 5145344` resolves to the same range as `--package dtm-cars`.

## Tracks

| File or package | Role in the verified PS2 track path |
| --- | --- |
| `tracks.big` | Track catalog. An entry supplies a `TrackID`, names, `LengthInKm`, and an `HOFIndex`. Use a free record index for an additional track. |
| `events.big` | Event calendars. A `TrackID` must appear in a compatible event to be selectable. The Road America experiment uses Autosport Clio Cup Free Race and Time Trial. |
| `TRACK.JPK` | Collision, track-prop data, and a nested package with AI and lap data. On Oschersleben, `osc1.big` contains `osc1.ail` and class-specific `.aib` files. |
| `DMA1.JPK` | PS2 rendering packages. Geometry members contain VIF/DMA data, scene nodes, and relocation records. RD2 scene nodes require conversion for RD3. |
| `TRACK.BIG` | Track metadata and environment settings. A track JPAK is available in the observed Oschersleben load, so the loader uses it for object members. The ELF also has a fallback to `TrackObj.big`. |

### Review collisions and routes

```powershell
python scripts/ModAssets.py extract --disc $disc --package oschersleben-track col.col "$work\col.col"
python scripts/ModAssets.py collision-info "$work\col.col"
python scripts/ModAssets.py extract --disc $disc --package oschersleben-track --inside osc1.big osc1.ail "$work\osc1.ail"
```

`collision-info` checks the mesh bounds, array lengths, and triangle indices, and lists the existing surface types with a sample triangle for each type. `collision-surface` copies a triangle's surface type using zero-based indices. Use `collision-export` to inspect the physical track mesh in an OBJ editor and `collision-append` to add new triangles and their cell data. [PS2 collision research](ps2-disc-and-archives.md#authoring-ps2-collision)

To visualize the route in an editor with an OBJ importer, run `route-obj` on the converted Road America `AILD` v9 member. The OBJ contains three groups of polylines for the main, pit, and auxiliary sections. It has the game's X/Z coordinates and sets Y to zero. Compare the shape to the donor scene before testing checkpoints, pit entry, or AI.

```powershell
$addon = 'D:\Mods\Road America'
python scripts/ModAssets.py extract --file "$addon\TRACK.JPK" --inside osc1.big osc1.ail "$work\roa.ail"
python scripts/ModAssets.py route-obj "$work\roa.ail" "$work\roa-route.obj"
```

### Edit route lanes and checkpoints

`route-export` writes one CSV row per station for the main, pit, and auxiliary sections. The `xN` and `zN` columns hold metre coordinates for lane bit `N`. Leave a lane blank when it is absent from that section. The four event bytes are `code`, `tag`, `argument`, and `reserved`. On the verified circuits, main-route code `10` marks a checkpoint and its tag identifies it. To move a checkpoint to a nearby unused station, move all four event bytes together and copy the unused station's event bytes into the vacated row. Keep the order of the checkpoints as encountered by the car.

Main-route codes `12` and `13` delimit the span represented by the auxiliary route. The importer checks the number of stations across that span, including both endpoints and any wrap across the start line. It retains the template's lane mask and loop flag for every section. Keep the distances and normals consistent with the edited lane positions. Small lateral edits can reuse the template distances. A new route shape needs its own distances, normals, and matching collision.

For Time Trial ghosts, keep the main-route sector splits in driving order. Foundry Oval uses code `2` with arguments `0` and `1` for the two splits in a three-sector lap. A lap can reach the profile's lap records while the ghost recorder is still waiting for its sector sequence. Check the ghost itself in **Load** after a cold launch. [Foundry Oval sector verification](ps2-disc-and-archives.md#foundry-oval-time-trial-sectors)

Set `$addon` to the [expanded add-on](ps2-disc-and-archives.md#add-a1-ring-gp-and-short) with A1-Ring Short in `tqa3`.

```powershell
$trial = 'D:\Mods\Short Route Test'
Copy-Item -LiteralPath $addon -Destination $trial -Recurse
python scripts/ModAssets.py extract --file "$trial\tqa3\TRACK.JPK" --inside osc1.big osc1.ail "$work\short.ail"
python scripts/ModAssets.py route-export "$work\short.ail" "$work\short.csv"
# Save the edited table as short-edited.csv without changing station IDs or columns.
python scripts/ModAssets.py route-import "$work\short.ail" "$work\short-edited.ail" --csv "$work\short-edited.csv"
python scripts/ModAssets.py replace --file "$trial\tqa3\TRACK.JPK" --inside osc1.big osc1.ail "$work\short-edited.ail" "$work\TRACK.JPK"
Copy-Item -LiteralPath "$work\TRACK.JPK" -Destination "$trial\tqa3\TRACK.JPK"
```

Test the edited route in both Time Trial and a race with opponents. [PS2 route format](ps2-disc-and-archives.md#editing-ps2-track-routes)

#### Add or remove route stations

Use `route-import --resize` when the table has a different number of rows. Keep the three sections in order and number each one consecutively from zero. On a straight, insert an ordinary station between two stations with code `0`. Interpolate the X/Z pair for each present lane and its distance, and use a unit X/Z normal. Keep event bytes on their intended stations. An edit between code `12` and `13` also needs a corresponding row change in the auxiliary section. Those rows describe the same span through the start line, with their own lane positions.

```powershell
python scripts/ModAssets.py route-import "$work\short.ail" "$work\short-resized.ail" --csv "$work\short-resized.csv" --resize
```

Then replace `osc1.ail` in the trial package with `short-resized.ail` as above. If the outer `TRACK.JPK` runs out of room, reduce the route or use a compatible package with sufficient space. Check the grid placement, both sides of the start line, AI traffic, and a timed finish after resizing a route.

### Test a track change on Windows

1. Build the [Road America add-on](ps2-disc-and-archives.md#play-road-america-from-your-own-discs) from your two disc copies. Keep that directory as the control. Put successive experiments in new directories.
2. Edit a single decoded member first. The example below copies Road America's surface type from triangle 49 to triangle 1134. It creates a new add-on directory and copies `tracks.big`, `events.big`, and `DMA1.JPK`. It repacks `TRACK.JPK` with the edited collision. Use the values from `collision-info` when selecting triangles in a different package.
3. Open your candidate with `TocaRecomp.exe --disc <RD3 ISO> --road-america <add-on directory>`. Select **Free Race → Autosport Clio Cup → Road America → Sunny**. Check the start straight, two or more corners, collision surfaces, AI, lap count, and the race result. End a Time Trial session and cold-launch from the same data directory to check saved times. Select stock Oschersleben with the add-on still active to check that its course is unchanged. Use a separate `--data-dir` when you need independent test saves.

```powershell
$trial = 'D:\Mods\Road America Test'
New-Item -ItemType Directory -Path $trial | Out-Null
'tracks.big', 'events.big', 'DMA1.JPK' | ForEach-Object { Copy-Item -LiteralPath "$addon\$_" -Destination $trial }
python scripts/ModAssets.py extract --file "$addon\TRACK.JPK" col.col "$work\roa.col"
python scripts/ModAssets.py collision-surface "$work\roa.col" "$work\roa-edited.col" --triangle 1134 --from-triangle 49
python scripts/ModAssets.py replace --file "$addon\TRACK.JPK" col.col "$work\roa-edited.col" "$trial\TRACK.JPK"
```

On Windows 11 Direct3D 12 the experimental course reached frame 8350 from power-on. The guest collision data contained surface type `2` for triangle 1134 where the control package had `0`. The vertex stream matched the control. A separate race opened a repacked `TRACK.JPK` containing an edited `lights.ini`. The captured light resource matched the original copy in the stock companion package. Confirm which resource the loader uses before attributing a visual effect to an archive edit.

The importer can build a [three-course pack](ps2-disc-and-archives.md#add-a1-ring-gp-and-short) with Road America, A1-Ring GP, and A1-Ring Short in separate slots. To edit an A1-Ring member, copy the entire expanded pack and edit the files under `tqa2` or `tqa3`. Keep the two catalogs and all three resource pairs in the candidate. Both A1-Ring layouts have passed Free Race and Time Trial with autosave. The [local lap records](ps2-disc-and-archives.md#local-lap-records) for all three imports coexist in one profile.

For a Road America edit that applies in both weather settings, edit the corresponding package member at the root and under `rain`. The root files supply Sunny, and the extra pair supplies Rain. Use a separate pack directory for the experiment. [Road America in Rain](ps2-disc-and-archives.md#road-america-in-rain)

### Add a new collision shape

Use the exported template as a placement reference in your OBJ editor. Author the new surface as its own mesh and export just that mesh as triangulated OBJ. Use the game's XYZ coordinates in metres, with Y up. Keep the new vertices within the exported mesh's collision bounds and point drivable faces upward. The new triangles use the surface type of the zero-based triangle you select with `--surface-from`. Choose an asphalt example from `collision-info` for a ramp or speed hump.

```powershell
$trial = 'D:\Mods\Road America Hump'
Copy-Item -LiteralPath $addon -Destination $trial -Recurse
python scripts/ModAssets.py extract --file "$addon\TRACK.JPK" col.col "$work\source.col"
python scripts/ModAssets.py collision-export "$work\source.col" "$work\placement.obj"
python scripts/ModAssets.py collision-info "$work\source.col"
# Save your triangulated ramp as ramp.obj in the work folder.
python scripts/ModAssets.py collision-append "$work\source.col" "$work\with-ramp.col" --obj "$work\ramp.obj" --surface-from 1598
python scripts/ModAssets.py replace --file "$addon\TRACK.JPK" col.col "$work\with-ramp.col" "$work\TRACK.JPK"
Copy-Item -LiteralPath "$work\TRACK.JPK" -Destination "$trial\TRACK.JPK"
.\TocaRecomp.exe --disc 'D:\Games\TOCA Race Driver 3.iso' --road-america $trial --data-dir "$work\test-player"
```

Triangle 1598 supplies asphalt on the reference Road America pack. Test the Sunny course in a separate profile. The physical shape is independent of road rendering, which still comes from `DMA1.JPK`. The importer retains the template's terrain and edge flags, reindexes the existing cell references, and checks the PS2 cache limit for the affected cells. Replacing the entire course still requires a compatible visual scene, route, and event entry.

### Add matching visible geometry

Use the same OBJ and coordinate system for the visual and collision parts of the shape. The visual tool uses a material from the locally extracted scene and projects the X/Z footprint to the texture. `scene-info` reports a compatible material leaf from each root close to the supplied X/Z position. The offsets below apply to the Sunny Road America `trk.dma` from the importer. Use the offsets reported for your actual file when editing another scene.

```powershell
python scripts/ModAssets.py extract --file "$trial\DMA1.JPK" trk.dma "$work\trk.dma"
python scripts/ModAssets.py scene-info "$work\trk.dma" --near -20 -500
python scripts/ModAssets.py scene-append "$work\trk.dma" "$work\trk-authored.dma" --obj "$work\ramp.obj" --root 0x2284 --leaf 0x95910 --rgb 190 146 66 --offset-y 0.015
python scripts/ModAssets.py replace --file "$trial\DMA1.JPK" trk.dma "$work\trk-authored.dma" "$work\DMA1.JPK"
Copy-Item -LiteralPath "$work\DMA1.JPK" -Destination "$trial\DMA1.JPK"
.\TocaRecomp.exe --disc 'D:\Games\TOCA Race Driver 3.iso' --road-america $trial --data-dir "$work\test-player"
```

The 1.5 cm visual offset keeps near-coplanar ramp edges visible against the underlying road. The optional RGB values tint the reused material and retain its original alpha. Launch the Sunny Road America session to test this pair. Additional material layouts, author-supplied textures, and standalone track scenes need their own verification. [PS2 scene authoring](ps2-disc-and-archives.md#authoring-ps2-visible-track-geometry)

### Build and play Foundry Oval

Foundry Oval is a 702 m demonstration circuit with its own race route, road mesh, and collision. It occupies `tqa4` in Windows preview 6 alongside the three imported circuits. Start with the unmodified expanded pack built from both of your PS2 disc copies. The builder puts the new pack in its own directory.

```powershell
python scripts/BuildFoundryOval.py 'D:\Mods\Road America and A1-Ring' 'D:\Mods\Foundry Pack'
.\TocaRecomp.exe --disc 'D:\Games\TOCA Race Driver 3.iso' --road-america 'D:\Mods\Foundry Pack' --data-dir 'D:\Mods\Foundry Player'
```

In **Free Race**, choose **Autosport Clio Cup**, then **Foundry Oval**. The same circuit is available in Time Trial. It uses the reference loading screen and a material from your Road America pack. The flat collision surface extends into the run-off area, and the demonstration has no barriers.

To enable ghost saving on a previously generated Foundry pack, run the current builder with a new output directory. Launch that pack with the same Windows preview 6 executable. In Time Trial, choose **New** in the ghost menu, select a slot, and acknowledge the confirmation. Drive an opening pass at a lower pace, then complete a faster full lap with both sector splits. End the session to save the recording. [Time Trial verification](ps2-disc-and-archives.md#foundry-oval-time-trial-sectors)

For another circuit, work on a copy of this pack and edit its `tqa4` resources. `collision-build` generates a new `col.col` from the supplied triangulated OBJ, taking a surface type from the template. `scene-replace` substitutes the root of `trk.dma` with the supplied OBJ mesh and the selected local material. Use `scene-append` for a second surface or mesh. Supply a matching `AILD` route in `osc1.big/osc1.ail`. See `scripts/BuildFoundryOval.py` for an example that generates all three assets. [Route editing](#edit-route-lanes-and-checkpoints) · [Foundry Oval verification](ps2-disc-and-archives.md#foundry-oval)

## Cars

Start with a DTM car. The verified PS2 archive for the class is `CARDATA\DTMX\DTMX.JPK`. Its directory includes the Audi A4 `.mdl` and `.msh` pair, textures, `CarParts.big`, and variant packages such as `dtmx_00.big`. The two model files are a paired PS2 format. The [RD3_BD7sTools](https://github.com/BuilderDemo7/RD3_BD7sTools) project targets conversion from PSP track `.p3d` to PC `.px` and is still under development. The ZModeler Race Driver filter documents the desktop mesh workflow and the shared part map layout. [PS2 comparison](ps2-disc-and-archives.md#stock-ps2-dtm-models-and-oschersleben-collision)

### Inspect a car part map

```powershell
python scripts/ModAssets.py extract --disc $disc --package dtm-cars DTM_A4.mdl "$work\DTM_A4.mdl"
python scripts/ModAssets.py extract --disc $disc --package dtm-cars DTM_A4.msh "$work\DTM_A4.msh"
python scripts/ModAssets.py extract --disc $disc --package dtm-cars --inside dtmx_00.big part.map "$work\part.map"
python scripts/ModAssets.py part-map-export "$work\part.map" "$work\part-map.json"
```

`part.map` starts with three little-endian 32-bit words for the version, number of LOD rows, and entries per row. The reference DTM variants use version 1, five rows, and 320 entries per row. JSON lists the raw unsigned 32-bit values in order and preserves the original bit patterns. Keep the dimensions unchanged when editing the same car. Use the model's part counts to match the variant, and keep `0xffffffff` for absent parts. [DTM variant mapping](ps2-dtm-models.md#match-a-variants-part-map-to-its-model)

```powershell
python scripts/ModAssets.py part-map-import "$work\part-map.json" "$work\part-rebuilt.map"
python scripts/ModAssets.py replace --disc $disc --package dtm-cars --inside dtmx_00.big part.map "$work\part-rebuilt.map" "$work\DTMX-test.JPK"
```

Run an unedited JSON round trip first. The rebuilt map should have the same SHA-256 as the extracted file. After an edit, run `model-info` with `--part-map` to verify the referenced indices. Extract the member again from `DTMX-test.JPK` and compare it to the intended bytes. A one-entry test changed the nested map, preserved the 5,145,344-byte outer extent, and matched every other decoded member at both levels. To load the rebuilt package, give it the name `DTMX.JPK` in a `--dtm-mod` directory. [DTM model and overlay guide](ps2-dtm-models.md)

The DTM model and overlay guide covers the `.mdl`/`.msh` structure, OBJ exports by detail level, and two ways to edit a mesh. Before replacing a complete model, match the textures, part identifiers, and damage attachments. Test wheel and suspension movement, body panels, cockpit views, sound, and LODs before creating a permanent car slot. [DTM model and overlay guide](ps2-dtm-models.md)
