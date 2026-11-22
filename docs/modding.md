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

Each listing shows the member's package-relative offset, disk size, decoded size, and encoding. `extract` returns the decoded file and prints its SHA-256. Use `--inside` once for each container between the outer package and the file. `replace` writes a new copy of the outer package with the same total length. If a JPAK member outgrows its slot, the tool packs its entries within the original package extent and updates their offsets. A BIGF edit must fit the original member slot. Use a new output filename for every command.

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

`collision-info` checks the mesh bounds, array lengths, and triangle indices, and lists the existing surface types with a sample triangle for each type. A collision file holds a 40-byte header, eight bytes per packed vertex, four bytes of per-triangle information, three 16-bit indices per triangle, a spatial cell table, and a trailer in the reference sample. The surface type occupies the third byte of each per-triangle record. `collision-surface` copies that byte between triangles using zero-based indices. When changing collision topology, keep the surface data and cell lists consistent with the triangle indices. Generating the cell data for newly authored collision meshes remains a separate step. [Collision template](https://github.com/Nenkai/010GameTemplates/blob/main/Codemasters/Race_Driver_3/HeightData_col.col.bt) · [PS2 collision research](ps2-disc-and-archives.md#stock-ps2-dtm-models-and-oschersleben-collision)

To visualize the route in an editor with an OBJ importer, run `route-obj` on the converted Road America `AILD` v9 member. The OBJ contains three groups of polylines for the main, pit, and auxiliary sections. It has the game's X/Z coordinates and sets Y to zero. Compare the shape to the donor scene before testing checkpoints, pit entry, or AI.

```powershell
$addon = 'D:\Mods\Road America'
python scripts/ModAssets.py extract --file "$addon\TRACK.JPK" --inside osc1.big osc1.ail "$work\roa.ail"
python scripts/ModAssets.py route-obj "$work\roa.ail" "$work\roa-route.obj"
```

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

The importer can build a [three-course pack](ps2-disc-and-archives.md#add-a1-ring-gp-and-short) with Road America, A1-Ring GP, and A1-Ring Short in separate slots. To edit an A1-Ring member, copy the entire expanded pack and edit the files under `tqa2` or `tqa3`. Keep the two catalogs and all three resource pairs in the candidate. A1-Ring track record verification and a workflow for newly authored geometry remain in the [checklist](acceptance-checklist.md#separate-modding-milestone).

## Cars

Start with a DTM car. The verified PS2 archive for the class is `CARDATA\DTMX\DTMX.JPK`. Its directory includes the Audi A4 `.mdl` and `.msh` pair, textures, `CarParts.big`, and variant packages such as `dtmx_00.big`. The two model files are a paired PS2 format. The [RD3_BD7sTools](https://github.com/BuilderDemo7/RD3_BD7sTools) project targets conversion from PSP track `.p3d` to PC `.px` and is still under development. The ZModeler Race Driver filter documents the desktop mesh workflow and the shared part map layout. [PS2 comparison](ps2-disc-and-archives.md#stock-ps2-dtm-models-and-oschersleben-collision)

```powershell
python scripts/ModAssets.py extract --disc $disc --package dtm-cars DTM_A4.mdl "$work\DTM_A4.mdl"
python scripts/ModAssets.py extract --disc $disc --package dtm-cars DTM_A4.msh "$work\DTM_A4.msh"
python scripts/ModAssets.py extract --disc $disc --package dtm-cars --inside dtmx_00.big part.map "$work\part.map"
python scripts/ModAssets.py part-map-export "$work\part.map" "$work\part-map.json"
```

`part.map` starts with three little-endian 32-bit words for the version, number of LOD rows, and entries per row. The candidate DTM variant holds version 1, five rows, and 320 entries per row. JSON lists the raw unsigned 32-bit values in order and preserves the original bit patterns. Keep the dimensions unchanged for an edit of the same car. The meaning of individual indices still needs verification against the associated PS2 meshes.

```powershell
python scripts/ModAssets.py part-map-import "$work\part-map.json" "$work\part-rebuilt.map"
python scripts/ModAssets.py replace --disc $disc --package dtm-cars --inside dtmx_00.big part.map "$work\part-rebuilt.map" "$work\DTMX-test.JPK"
```

Run an unedited JSON round trip first. The rebuilt map should have the same SHA-256 as the extracted file. After a small edit, extract the member again from `DTMX-test.JPK` and compare it to the intended bytes. A one-entry test changed the nested map, preserved the 5,145,344-byte outer extent, and matched every other decoded member at both levels. To load the rebuilt package, give it the name `DTMX.JPK` in a `--dtm-mod` directory. [DTM model and overlay guide](ps2-dtm-models.md)

The [DTM model and overlay guide](ps2-dtm-models.md) covers the `.mdl`/`.msh` structure and a CSV workflow for editing vertex positions. Before replacing a complete model, match the textures, part identifiers, and damage attachments. Test wheel and suspension movement, body panels, cockpit views, sound, and LODs before creating a permanent car slot.
