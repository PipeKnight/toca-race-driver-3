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
