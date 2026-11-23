# PS2 DTM car models

The North American PS2 release `SLUS-21182` v1.02 loads DTM model files from `CARDATA\DTMX\DTMX.JPK` and can request a high-detail mesh separately. The Oschersleben World Tour race used `DTM_C_KLASSE_HI.MSH` from `RDH_2.HUG`, sector 190800. The class package starts at sector 187552 of the same HUG. [Archive research](ps2-disc-and-archives.md#stock-ps2-dtm-models-and-oschersleben-collision)

## Extract and inspect the pair

Use the same car name for the `.mdl` and `.msh`. The filename identifies the car, and the relocation bases identify allocation slots shared by these DTM models. Select the high-detail file from the actual traced disc path when editing the player's Mercedes.

```powershell
$disc = 'D:\Discs\TOCA Race Driver 3'
$work = 'local\dtm-work'
New-Item -ItemType Directory -Path $work -Force | Out-Null
python scripts/ModAssets.py extract --disc $disc --package dtm-cars DTM_C_Klasse.mdl "$work\mercedes.mdl"
python scripts/ModAssets.py extract --disc $disc --package dtm-cars DTM_C_Klasse.msh "$work\mercedes.msh"
python scripts/ModAssets.py extract-resource --disc $disc --package dtm-mercedes-hi "$work\mercedes-hi.msh"
python scripts/Ps2CarModel.py model-info "$work\mercedes.mdl" "$work\mercedes.msh" --hi-mesh "$work\mercedes-hi.msh"
```

| Structure | Observed DTM layout |
| --- | --- |
| Footer | Three little-endian 32-bit words for relocation count, payload length, and original base address. The relocation table fills the space between the payload and the footer. Each entry has a 32-bit payload offset and a 32-bit kind. |
| `.mdl` | The five words at `0x00` through `0x10` point into sections in the model payload. The reference base is `0x00bd0b40`. The model uses relocation kinds `0`, `3`, and `4`. Its words at `0x30` and `0x34` contain the base references for the high-detail and class-package meshes. |
| `.msh` | The reference meshes from the class package use base `0x02bd0b60`. The traced Mercedes high-detail mesh uses `0x0abd0be0`. Their relocation rows are kind `4` and point to VIF `MSCAL` commands. |
| Mesh packets | A `0x6c028000` VIF command starts a packet with an eight-word header. Header words 2, 3, and 4, counted from zero, supply the UV destination, vertex count, and normal destination. The position stream is V3-32 at the UV destination plus two. The corresponding V2-32 UV stream and V3-32 normal stream have the same vertex count. The packet closes with `MSCAL` or `MSCNT`. |
| Triangle-strip template | The observed packets contain a packed GIF template with `PRE` set, primitive `4`, and the registers ST, RGBAQ, and XYZ2 (`0x512`). Its loop count matches the vertex count in the packet header. The OBJ preview builds triangles from this strip order. |

| Asset | Position packets | Position records |
| --- | ---: | ---: |
| Audi A4 class mesh | 1,126 | 6,397 |
| Mercedes C-Class class mesh | 1,099 | 6,313 |
| Vectra class mesh | 1,170 | 6,451 |
| Mercedes C-Class high-detail mesh | 1,054 | 6,740 |

## Find packets by detail level

`model-info` reports each detail level's first packet and packet count. The `.mdl` has five sections. The first references LOD 0 in the high-detail mesh, and the remaining sections reference LODs 1–4 in the class mesh. Aligned DMA REF tags give the byte ranges of the mesh blocks used by each section. The tool checks that these ranges cover the corresponding mesh payload in order and that the packet counts agree with the model headers. It reports the LOD 0 packet range when given `--hi-mesh`.

| Mercedes detail level | Mesh | Packet indices | Roof packets |
| --- | --- | --- | --- |
| 0 | `DTM_C_KLASSE_HI.MSH` | 0–1053 | 135, 136 |
| 1 | `DTM_C_Klasse.msh` | 0–576 | 56, 57 |
| 2 | `DTM_C_Klasse.msh` | 577–879 | 606, 607 |
| 3 | `DTM_C_Klasse.msh` | 880–1034 | 904, 905 |
| 4 | `DTM_C_Klasse.msh` | 1035–1098 | 1065 |

Give `mesh-preview` the matching `.mdl` and a detail level to export only that level. Group names retain the packet numbers from the full mesh, so the exported OBJ can serve as a reference for `mesh-replace` without renumbering. The packet table above applies to the reference Mercedes. Run `model-info` again for another car.

```powershell
python scripts/Ps2CarModel.py mesh-preview "$work\mercedes.msh" "$work\mercedes-lod2.obj" --model "$work\mercedes.mdl" --lod 2
python scripts/Ps2CarModel.py mesh-preview "$work\mercedes-hi.msh" "$work\mercedes-lod0.obj" --model "$work\mercedes.mdl" --lod 0
```

### Match a variant's part map to its model

Compare the `lod_part_counts` in `model-info` with the matching variant's `part.map`. The `.mdl` words at section offsets `0x24` and `0x28` reference the beginning and end of a table with `0x30` bytes per part. The word at `0x30` gives the record count. Each stock DTM map row lists every model part index from zero to the count minus one, once each. `0xffffffff` marks slots with no part at that detail level. This describes the index range and leaves the function of individual slots open.

| Model | Part counts for LODs 0–4 | Matching DTM variant packages |
| --- | --- | --- |
| `DTM_A4.mdl` | 80, 76, 54, 43, 3 | `dtmx_00.big`–`dtmx_07.big` |
| `DTM_C_Klasse.mdl` | 83, 80, 57, 45, 3 | `dtmx_08.big`–`dtmx_15.big`, plus `dtmx_12b.big` and `dtmx_13b.big` |
| `DTM_Vectra.mdl` | 80, 77, 54, 43, 3 | `dtmx_16.big`–`dtmx_19.big` |

All 22 maps in the reference `DTMX.JPK` matched the corresponding model counts. [Part map export workflow](modding.md#inspect-a-car-part-map)

Pass `--part-map` to check the binary map against its model before repacking a variant. The report includes the number of assigned slots and distinct referenced parts at each detail level. An out-of-range entry stops the check and identifies the affected level, slot, and index. Review the part assignments in a mod separately, since a range check alone can accept a valid index attached to the wrong slot.

```powershell
python scripts/ModAssets.py extract --disc $disc --package dtm-cars --inside dtmx_08.big part.map "$work\mercedes-part.map"
python scripts/Ps2CarModel.py model-info "$work\mercedes.mdl" "$work\mercedes.msh" --part-map "$work\mercedes-part.map"
```

## Edit a mesh while retaining its layout

Export the positions to CSV, edit the `x`, `y`, and `z` columns, then import the result into a new copy of the same mesh. Keep the header, packet indices, vertex indices, and row order. Test an unedited export and import first. The two mesh hashes should match. A uniform scale is a useful first experiment because the stored normals retain the same directions.

Use `mesh-preview` to open the strips in an OBJ editor. The preview includes the stored positions, normals, and UVs grouped by packet. These are local mesh coordinates. Scene placement, materials, and any clipping decisions made by VU programs require additional decoding.

```powershell
python scripts/Ps2CarModel.py mesh-preview "$work\mercedes-hi.msh" "$work\mercedes-hi.obj"
python scripts/Ps2CarModel.py mesh-export "$work\mercedes-hi.msh" "$work\positions.csv"
python scripts/Ps2CarModel.py mesh-import "$work\mercedes-hi.msh" "$work\positions.csv" "$work\roundtrip.msh"
Get-FileHash "$work\mercedes-hi.msh", "$work\roundtrip.msh"

$mod = 'D:\Mods\DTM test'
New-Item -ItemType Directory -Path $mod -Force | Out-Null
python scripts/Ps2CarModel.py mesh-import "$work\mercedes-hi.msh" "$work\positions-edited.csv" "$mod\DTM_C_KLASSE_HI.MSH"
.\TocaRecomp.exe --disc 'D:\Discs\TOCA Race Driver 3.iso' --dtm-mod $mod
```

Use a Windows launcher built from a checkout that includes `--dtm-mod`. It accepts `DTM_C_KLASSE_HI.MSH`, `DTMX.JPK`, or both in the mod directory. The runner checks the original read extents and each overlay's structure before boot, and the disc stays read-only. The mod uses `dtm-mod.ps2` in the launcher's data directory. If you enable the Road America add-on in the same run, it uses `road-america-dtm.ps2`.

To replace the class mesh inside `DTMX.JPK`, export and import that mesh separately, then repack the result with the archive tool. Check the selected model and its LOD transitions in the race. Use the high-detail override for the traced player Mercedes mesh.

```powershell
python scripts/ModAssets.py replace --disc $disc --package dtm-cars DTM_C_Klasse.msh "$work\mercedes-class-edited.msh" "$mod\DTMX.JPK"
```

## Replace selected mesh packets from OBJ

Use `mesh-preview` to identify the mesh regions and their zero-based packet numbers. Work in the template's local coordinates. The Mercedes uses X across the car, Y up, and Z along its length. Export just the authored faces in groups named `packet_N`, with `N` identifying the template packet. The importer uses triangulated faces and requires a texture coordinate on every corner. It reads supplied normals or calculates a face normal. Share positions, UVs, and normals along the edges of a smooth strip to fit more triangles into the same packet.

```powershell
python scripts/Ps2CarModel.py mesh-replace "$work\mercedes-hi.msh" "$work\roof-scoop.obj" "$mod\DTM_C_KLASSE_HI.MSH"
.\TocaRecomp.exe --disc 'D:\Discs\TOCA Race Driver 3.iso' --dtm-mod $mod
```

The importer writes position, normal, and UV streams into the selected packets. It joins disconnected faces with degenerate triangles and pads the rest of the strip with repeated vertices. Each group must fit its template packet's vertex count. The file extent, relocation table, material bindings, and VU command positions keep their original layout. For a different detail level, locate and edit its own mesh packets. Part and damage mapping, custom textures, and registration as a separate car have their own acceptance items.

## Windows verification

The single-executable candidate built a fresh backend from the reference ISO. Two cold Direct3D 12 runs on the RTX 4070 entered the same Oschersleben World Tour race with identical scripted inputs. One used the stock Mercedes. The other applied a uniform factor of `0.80` to the high-detail position streams and loaded the edited `DTM_C_KLASSE_HI.MSH`. At frame 3700, the captured car body had visibly changed. The differences were confined to the car and its immediate outline in the capture. All 442 tested position packets with six or more records matched the corresponding edited bytes in EE RAM. The high-detail CSV export and import without edits reproduced the original disc file byte for byte. The OBJ preview produced 4,602 triangles for this mesh after omitting faces with duplicate positions.

A separate run enabled only a rebuilt `DTMX.JPK` with a changed vertex in the class-package Mercedes mesh. The game loaded that package and the edited vertex appeared at the original packet location in EE RAM. Both edited runs reached frame 3720. Local evidence is under `local/dtm-modding/`, including `stock/frames/frame_03700.png`, `hi-edit/frames/frame_03700.png`, and `low-edit/trace.log`.

A combined Direct3D 12 run reached the Road America Clio Cup race with the DTM overlay also enabled. Its frame 8347 capture matched the previous Road America candidate byte for byte. Direct launcher checks selected the stock, DTM, and combined cards as expected. The launcher rejected an empty DTM mod directory and a truncated high-detail file before starting the game.

### Authored roof intake

Replaced high-detail Mercedes packets 135 and 136 with an original two-sided, 16-triangle roof intake. The new triangles used 10 strip vertices per side within the template capacities of 12 and 11. All six replacement position, normal, and UV streams matched EE RAM. The 369,788-byte mesh differed from the template in 570 attribute bytes. The matched Windows Direct3D 12 captures at frame 3700 differed by 566 pixels within a 39 × 28 region around the roof. The local OBJ and overlay are under `local/dtm-authored/`, and the captures are under `local/dtm-modding/authored-roof/`.

The standard Windows runner replayed the final lap at Oschersleben from frame 3250 through the post-race cutscene at frame 9300. All 404 replay checkpoints matched. The intake remained visible on the final straight as the race faded out. The replay trace and captures are under `local/dtm-authored/replay/`.

### Roof geometry at other detail levels

The class-package edit adjusted the roof in LODs 1–4. It raised centreline vertices in LODs 1 and 2. The two coarsest levels used a raised roof silhouette with the adjacent shared vertices moved by the same amount. The edits fit the original streams and the rebuilt package retained its disc extent.

Paired Direct3D 12 runs at Oschersleben cycled through the cockpit, bonnet, bumper, and chase cameras. The modified LOD 0 roof remained visible on returning to chase view. The captures also showed pixel changes on distant opponents after editing the far roof. A local VIF1 DMA probe matched the edited LOD 4 roof stream on 347 frames, from frame 3105 to 3451. The ordinary runner and the probe produced eight byte-identical images with the same overlay. Local evidence is under `local/dtm-authored/lod-test/` and `local/dtm-modding/lod-far-ordinary/`. [Intermediate-level verification](#observe-detail-levels-when-cars-pass)

Three diagnostic overlays changed the four floats at `.mdl` offset `0x18`. The recorded roof transfers still used LODs 0 and 4 at the same frames. The probe traces from those experiments are under `local/dtm-modding/lod-force-1/` through `lod-force-3/`.

### Observe detail levels when cars pass

The reference game loads `LOD.ini` from the shared package at `RDH_1.HUG` sector 67712. Function `0x001d07a8` reads separate tables for the number of cars at each level and the distances. The stock single-player table has limits of 1, 3, 5, and 7 for LODs 0–3 and distances of 15, 30, 60, and 80 for LODs 1–4. The game stores the squared distances in EE RAM at `0x00577b84`. A local read overlay changed the distance table to 1, 40, 110, and 150 while retaining the stock car limits. The resulting race loaded and the EE table contained those values squared. A separate test that raised the three intermediate car limits to 20 remained at the loading screen through the observation window.

```powershell
python scripts/ModAssets.py extract --disc $disc --range 1 67712 43008 LOD.ini "$work\LOD.ini"
```

With the stock configuration, braking on the rolling start at Oschersleben let several opponents pass the player. A local DMA probe classified transfers against the `.mdl` mesh ranges over frames 3050–3999. Each of the three DTM models submitted all four class-package detail levels in that interval.

| Model | Frames with LOD 1 transfers | LOD 2 | LOD 3 | LOD 4 |
| --- | ---: | ---: | ---: | ---: |
| Mercedes C-Class | 297 | 192 | 77 | 865 |
| Audi A4 | 591 | 285 | 161 | 876 |
| Vectra | 160 | 127 | 69 | 870 |

These counts measure frames with at least one transfer from the corresponding section. The class submission trace is under `local/dtm-modding/lod-family-traffic/`. The local configuration edits and the original read trace are under `local/dtm-authored/lod-traffic/`.

The ordinary Direct3D 12 runner repeated the same inputs with the stock configuration and captured 34 matched frames per run. In each comparison only the selected Mercedes class-mesh level changed. The player used the same high-detail roof in every run. Twenty-two LOD 1 captures, twelve LOD 2 captures, and five LOD 3 captures differed from the control. The changes were on the roofs of passing or distant cars. The independent DMA trace reported the corresponding Mercedes level on all 22 LOD 1 frames, all 12 LOD 2 frames, and four of the five LOD 3 frames. Example pairs are frame 3460 for LOD 1, frame 3380 for LOD 2, and frame 3730 for LOD 3. The paired captures are under `local/dtm-modding/lod-isolated-0/` through `lod-isolated-3/`.

## Register an additional DTM variant

The introductory race's `CareerOfferCarID` in `1st__.ini` identifies the player variant. The new assignment is `dtmx_20/CKL`. The expanded class package retains the original driver roster's assets and adds the variant's `.big`, `.tex`, and `lookup.ini` entry. The lookup maps `dtmx_20` to `QA_Touring`. This uses a separate `.mdl` and class mesh with the Mercedes model layout. The player model's high-detail mesh and livery arrive as separate reads.

The class loader at `0x00215a40` resolves model basenames for the entire field against the current class's `lookup.ini`. An early `qac1_00` experiment loaded the new player's model and got a null model handle while constructing an opponent. The separate-class package supplied only the player's lookup entry. The expanded DTM package keeps those entries together and retains the original car models.

On the reference disc, the backend's existing archive path hook supplies records for the expanded `DTMX.JPK`, `QA_TOURING_HI.MSH`, and `DTMX_20_HI.TEX`. It checks the read-only extent in `RDH_2.HUG` before using its blank sectors for the overlay. The builder edits the one introductory event assignment in a separate copy of `events.big`. It verifies both model layouts against the local templates.

The packaged Windows build loaded the additional variant from a cold start under the normal `--dtm-mod` option. A replay of the final lap from frame 3250 through the post-race cutscene at frame 9800 matched all 437 checkpoints. The authored roof was visible on the final straight. A separate barrier impact showed cracked glass in cockpit view and replayed with all 60 checkpoints matching. These tests used the Mercedes's existing physics and damage resources. The new variant currently has an introductory race assignment. Selection in other modes, a full external body and texture import, and custom damage or suspension attachments need separate verification. [Build and run the variant](modding.md#test-an-additional-dtm-variant)
