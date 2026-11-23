# Import from Race Driver 2 on PS2

Use your own PS2 copies of Race Driver 2 `SLES-52638` v1.02 and TOCA Race Driver 3 `SLUS-21182` v1.02. This guide covers Road America and both A1-Ring layouts through a verified circuit importer. The playable car example fits a DB5 roof strip and copies the donor's body texture pages onto the QA Touring test variant. The model converter also prepares all five DB5 detail levels for development builds.

## Convert Road America and A1-Ring

Use Windows preview 6 or later and Python 3.10 or later. Run the commands from the repository root. Set `$rd2` to the mounted or extracted Race Driver 2 disc directory containing `RD2.DIR` and `RD2_1.HUG`. Set `$rd3` to the mounted or extracted TOCA Race Driver 3 disc directory containing `RDH.DIR` and `RDH_1.HUG`. The launcher can use the RD3 ISO directly. The builder needs a new output directory under an existing parent and verifies both disc-directory hashes.

```powershell
$rd2 = 'F:\'
$rd3 = 'D:\Discs\TOCA Race Driver 3'
$rd3Iso = 'D:\Discs\TOCA Race Driver 3.iso'
$launcher = 'D:\Games\TocaRecomp.exe'
$work = 'local\rd2-port'
New-Item -ItemType Directory -Path $work -Force | Out-Null
$pack = Join-Path $work 'RD2 Circuits'
python scripts/BuildRoadAmericaMod.py $rd3 $rd2 $pack --include-a1-ring
& $launcher --disc $rd3Iso --road-america $pack --data-dir "$work\player"
```

In **Free Race**, choose **Autosport Clio Cup**. Select **Road America** in Sunny or Rain, or choose **A1-Ring GP** or **A1-Ring Short** in Sunny. The same imports can be used in Time Trial. To build the Road America pack on its own, omit `--include-a1-ring`. Use the same data directory on a second launch to reload the add-on memory card.

| Circuit | Donor ID | Add-on resources |
| --- | --- | --- |
| Road America | `roa` | Pack root for Sunny and `rain` for Rain |
| A1-Ring GP | `a11` | `tqa2` |
| A1-Ring Short | `a12` | `tqa3` |

The importer puts the donor `col.col` and the converted `AILD` v9 route into `TRACK.JPK`. It rebuilds the donor's PS2 scene-node tree into the RD3 layout and writes it to `DMA1.JPK`. Keep both packages together with the pack's `tracks.big` and `events.big`. The imports use some companion resources from Oschersleben, including the A1-Ring loading screens. The Windows tests finished races and restored separate Time Trial records for the three circuits. [Circuit conversion and verification](ps2-disc-and-archives.md#add-a1-ring-gp-and-short)

For another RD2 circuit, start by locating the donor scene and collision package and the matching `.aid` route package. Read the `Course` entries in `scripts/BuildRoadAmericaMod.py` for the required inputs. Record the sector, entry count, and byte size of each selected member, then verify its route section counts and check that its converted scene and track fit the target slots. Give the circuit its own track ID, record index, and event-calendar entry. The current command targets the three circuits listed above. [Track authoring and validation](modding.md#tracks)

## Extract and preview the Aston Martin DB5

The RD2 Vintage class `BIGF` in `RD2_1.HUG` starts at sector 787442 and uses 7,009,268 bytes through the end of its last member. Its `lookup.ini` maps both `vc_2` and `vc_3` to `db5`. The example uses `vc_2` and exports the highest detail level with positions, UVs, and normals as OBJ. The OBJ contains geometry. Keep the extracted texture containers if you intend to work on the livery.

```powershell
$car = Join-Path $work 'DB5'
New-Item -ItemType Directory -Path $car | Out-Null
$range = @(1, 787442, 7009268)
python scripts/ModAssets.py list --rd2-disc $rd2 --range @range
foreach ($member in 'lookup.ini', 'db5.mdl', 'db5.msh', 'vc_2.tex', 'vc_2_hi.tex') {
    python scripts/ModAssets.py extract --rd2-disc $rd2 --range @range $member "$car\$member"
}
python scripts/Ps2CarModel.py mesh-preview "$car\db5.msh" "$car\db5-lod0.obj" --model "$car\db5.mdl" --combined-lods --lod 0
```

Open the OBJ in an editor. With the reference disc, LOD 0 contains 574 mesh packets and 4,938 exported triangles. Use `--lod 1` through `--lod 4` and distinct filenames for the lower detail levels. This class stores all five levels in one `.msh`. The supported RD3 Mercedes template supplies the highest level separately. Some RD2 archives contain a separate `car.p3d`; this example uses the PS2 class model pair. [RD3 model pair and packet layout](ps2-dtm-models.md#find-packets-by-detail-level)

## Build the DB5 roof and livery sample

The following commands use the DB5 files extracted above and the stock PS2 Mercedes DTM model as a target. `mesh-copy-strip` takes a donor strip in its original order, fits it in the target packet, and writes the positions, UVs, and normals. The example places DB5 packet 126 over the centre of the QA Touring roof using high-detail packet 135. This placement makes the transferred strip easy to identify in the selector and on track.

```powershell
python scripts/ModAssets.py extract-resource --disc $rd3 --package dtm-mercedes-hi "$work\mercedes-hi.msh"
python scripts/ModAssets.py extract --disc $rd3 --package dtm-cars DTM_C_Klasse.msh "$work\mercedes-class.msh"
python scripts/Ps2CarModel.py mesh-copy-strip "$car\db5.msh" "$work\mercedes-hi.msh" "$work\db5-roof-hi.msh" `
    --from-packet 126 --to-packet 135 --scale 2.1 1 2 --offset 0 0.03 0.38
$carPack = Join-Path $work 'DB5 Roof Test'
python scripts/BuildDtmVariant.py --disc $rd3 --mesh "$work\mercedes-class.msh" --hi-mesh "$work\db5-roof-hi.msh" `
    --livery-class "$car\vc_2.tex" --livery-hi "$car\vc_2_hi.tex" --output $carPack
& $launcher --disc $rd3Iso --dtm-mod $carPack --data-dir "$work\db5-test-player"
```

Take the introductory race for immediate access to the sample. On an add-on profile with DTM unlocked, select **QA Touring** in **Simulation Modes → Free Race → Touring Car → DTM**. Use a new folder for each build. Omit both livery options to keep the Mercedes livery and compare the roof on its own.

The livery options copy four indexed body images and their palettes by the names' `_01` through `_04` suffixes. The builder checks that both pixel and palette uploads have matching dimensions, then preserves the RD3 layout and upload commands. Class and high-detail files must be supplied as a pair. The Mercedes still supplies the texture bindings, material effects, and all class mesh geometry. The DB5 graphics therefore follow the Mercedes UVs on the rest of the car. In a cold Windows run, all three edited roof streams and all 16 copied pixel and palette payloads matched the data found in guest RAM.

The `preview.7` Direct3D 12 runner showed the sample in the Free Race selector using an isolated profile with DTM data assigned to an unlocked event. The sample completed the final lap of the introductory Oschersleben race. A replay on the standard runner matched all 484 checkpoints from frame 3250 through the post-race cutscene at frame 10500. Six matching race and cutscene captures were byte-identical.

## Adapt the sample to another part

Export the RD3 Mercedes template and choose a visible body surface. Match a strip by inspecting its `packet_N` group in the RD2 OBJ. `mesh-copy-strip` works when the source strip fits the target packet's vertex capacity. For changes that need to split or retriangulate a strip, align the donor OBJ to the target in local coordinates, keep a UV on every corner, and export the edited faces in the target Mercedes `packet_N` groups. Use `mesh-replace` and test the high-detail and class meshes separately. [Mesh replacement commands](ps2-dtm-models.md#replace-selected-mesh-packets-from-obj) · [Build the RD3 variant](modding.md#test-an-additional-dtm-variant)

## Convert the full DB5 model pair

Run this after extracting the DB5 above. The RD3 template provides the three reference addresses used by the destination model. The donor provides the model hierarchy, vertex streams, UVs, normals, and texture data. The output directory must be new.

```powershell
$template = Join-Path $work 'RD3 model template'
$converted = Join-Path $work 'DB5 converted model'
New-Item -ItemType Directory -Path $template | Out-Null
python scripts/ModAssets.py extract --disc $rd3 --package dtm-cars DTM_C_Klasse.mdl "$template\car.mdl"
python scripts/ModAssets.py extract --disc $rd3 --package dtm-cars dtmx_13.tex "$template\car.tex"
python scripts/ModAssets.py extract-resource --disc $rd3 --range 2 185648 381204 "$template\car_hi.tex"
python scripts/ConvertRd2CarModel.py --model "$car\db5.mdl" --mesh "$car\db5.msh" `
    --class-textures "$car\vc_2.tex" --high-textures "$car\vc_2_hi.tex" `
    --target-model "$template\car.mdl" --target-class-textures "$template\car.tex" `
    --target-high-textures "$template\car_hi.tex" --output $converted
python scripts/Ps2CarModel.py model-info "$converted\car.mdl" "$converted\car.msh" `
    --hi-mesh "$converted\car_hi.msh" `
    --part-map "$converted\part.map"
```

The conversion splits the RD2 mesh into LOD 0 and LODs 1–4, recalculates the DMA lengths and relocation offsets, and removes the separate RD2 color uploads where RD3's mesh walker expects positions. It compacts both the part and binding tables. The part map preserves the logical slot numbers and points each active slot to its new compact index. RD3 uses a different starting index for the draw matrices and emits a local matrix in each LOD. The converter shifts the matrix index, writes inline chains, and points composite parts at matrices in their own LOD. RD2 texture descriptors store an image byte count in the field RD3 uses for the mip upload count. The converter emits one upload per descriptor, including the embedded far-detail texture for LOD 4.

| LOD | Drawable parts | Mesh packets |
| --- | ---: | ---: |
| 0 | 71 | 574 |
| 1 | 56 | 376 |
| 2 | 52 | 189 |
| 3 | 45 | 117 |
| 4 | 4 | 25 |

The converter also rebuilt all five LODs of the RD2 Ford Falcon against the RD3 Falcon pair. This checks the model layout on a second donor. Slot numbers for a few matching Falcon parts were confirmed against both games. The mapping still needs in-race validation for moving DB5 parts and damage.

### In-game status

These outputs are development inputs. A Windows Direct3D 12 diagnostic runner displayed the converted exterior and donor livery in the selector and in the introductory Oschersleben race. Correcting the draw matrix index restored the exterior on track. The DB5 with the converted driving data finished the introductory race in 20th place and advanced to the next cutscene. It completed a separate one-lap Oschersleben Free Race in 3:08.12 in 21st place using scripted controller input. Replaying that race with the patched Windows runner matched all 779 recorded checkpoints and reached Race Results. A barrier impact in the introductory race deformed the bonnet. The one-lap completion fixture used the earlier QA Touring registration.

An Oschersleben traffic check with the player in a stock Vectra showed the AI driving the DB5. DMA captures identified the converted LOD 1–4 meshes as it pulled away. Converting the embedded texture fixed the out-of-range reads at the transition to LOD 4.

### Find the donor mechanics

The `vc_2` mechanics package is at `RD2_1.HUG` sector 790877 and occupies six sectors. Its `num.ini` identifies the variant. Both mechanics CSVs identify the Aston Martin DB5 and the damage file identifies `db5`. Extract these to inspect independent copies of the standard and simulation settings.

```powershell
$mechanics = Join-Path $work 'DB5 mechanics'
New-Item -ItemType Directory -Path $mechanics | Out-Null
foreach ($member in 'Mech.csv', 'SimMech.csv', 'dmg.ini', 'int.ini', 'num.ini') {
    python scripts/ModAssets.py extract --rd2-disc $rd2 --range 1 790877 12288 $member "$mechanics\$member"
}
```

Each RD2 mechanics row has 130 columns. The RD3 QA Touring rows each have 200 columns. Copying the overlapping driving fields into the RD3 rows changed the car's speed at the same frame of a scripted Oschersleben run. The two RD3 tire radius fields use the mean of the corresponding donor tire model heights divided by two. For the DB5 this gives 0.322218 metres on both axles. The full exterior still needs verification when the AI drives the DB5, including the door materials, wheel motion, and suspension through LOD transitions. The remaining RD3 driving fields, sound, and cockpit also need conversion or validation.

### Build the experimental pack from both discs

Use a local Windows launcher built with the converted model and variant type patches from the source manifest. The released Windows preview 7 expects the older fixed-size variant files.

```powershell
$pack = Join-Path $work 'DB5 drive test'
python scripts/BuildRd2Db5Variant.py --rd2-disc $rd2 --disc $rd3 --output $pack
& $launcher --disc $rd3Iso --dtm-mod $pack --data-dir "$work\db5-drive-test-player"
```

Start the introductory race from a fresh data directory. The builder installs the exterior, both texture sets, the part map, the overlapping driving fields, and the RD2 damage configuration in the additional DTM entry. The default build uses the Mercedes cockpit and sound. The sound option below enables the donor audio.

The builder adds `DB5` to the 82-entry `Cartype.big` from `RDH_1.HUG` sector 66833. The new record uses the game's existing Aston Martin manufacturer ID `AST` and a separate car record index, 110. It copies the 1450 kg weight from the DB5 mechanics row. The power and acceleration figures still need source data. The car type file, the introductory car offer, and the added DTM roster entry all use `DB5` as the type. The original Mercedes keeps `CKL`. The Free Race variant still requires the DTM event to be unlocked.

The selector requests a separate shadow file using the type ID. The runner redirects `Cars\Shadows\DB5.shd` to the Mercedes template's shadow until the port has a DB5 shadow mesh. A Windows 11 Direct3D 12 selector test showed the DB5 model, its name and 1450 kg in an isolated event fixture. The Mercedes team label remains visible because the added driver shares the original event's team registration.

### Extract the cockpit inputs

The RD2 interior archive has 128 entries. Extract the DB5 mesh pair and both texture containers from that archive. The RD3 interior archive has 24 entries. Its DTM cockpit contains a version 3 `PS2M` model and four TIM2 textures. The DTM class package carries the same cockpit files alongside the exterior models.

```powershell
$cockpit = Join-Path $work 'DB5 cockpit'
New-Item -ItemType Directory -Path $cockpit | Out-Null
foreach ($member in 'int_db5.mdl', 'int_db5.msh', 'int_db5.tex', 'int_db5_hi.tex') {
    python scripts/ModAssets.py extract --rd2-disc $rd2 --range 1 797863 10001732 $member "$cockpit\$member"
}
foreach ($member in 'int_dtm.px', 'int_dtm.big') {
    python scripts/ModAssets.py extract --disc $rd3 --package cockpits $member "$cockpit\$member"
}
python scripts/ModAssets.py list --file "$cockpit\int_dtm.big"
```

The donor `int.ini` identifies exterior part 2 for the cockpit view and provides the camera, steering, and driver coordinates. Importing the cockpit still requires converting the RD2 mesh pair and texture container, then verifying the part binding on the added variant.

The 12 stock RD3 `.px` cockpit models tested share a little-endian offset at file position `0x20` to a block containing the scene names. At offset `0x24` within that block is the byte length of the null-separated name table, which starts at `0x28`. For `int_dtm.px`, the block starts at `0xf3a0` and the table has 388 bytes. Its names include `int_main_body` and `r_door`. The table also names lights and targets. Match materials and drawable objects separately when mapping the donor cockpit.

### Test the legacy DB5 sound banks

Build the Windows launcher with the variant sound patch from the source manifest, then create a separate pack with `--donor-sound`.

```powershell
$soundPack = Join-Path $work 'DB5 sound test'
python scripts/BuildRd2Db5Variant.py --rd2-disc $rd2 --disc $rd3 --output $soundPack --donor-sound
& $launcher --disc $rd3Iso --dtm-mod $soundPack --data-dir "$work\db5-sound-test-player"
```

The builder reads the 11,115,173-byte RD2 sound archive at `RD2_1.HUG` sector 1000174. It adds four members to a local copy of RD3's 211-entry `Sound\Cars.big` at `RDH_2.HUG` sector 369392. The player and AI INIs get the `DB5` variant prefix. Their `<ELOOPS>` values keep the original sample filenames. The existing `grup_db5.msc` gear-change bank in RD3 matches the donor bytes. The optional `cars.big` and `system.icz` files must be installed together.

Both mechanics CSVs set column 57, counting from zero, to `DB5` only for the added variant. The separate `Sound\System.icz` index at `RDH_2.HUG` sector 371022 maps that name to bank 37 for the game's file existence check. Without a mapping the game tries `Unknown.big` and falls back to `Puma.big`. That path halted the Windows runner during the introductory race load. For a player using the DB5 sound pack, the runner keeps the legacy loop table and skips the streaming engine initializer. Stock engines still use their normal initialization.

On Windows 11, the DB5 ran through frame 3900 of the introductory Oschersleben race with the streaming initializer skipped. Its legacy player loop bank and shift sample were found in guest RAM. Two SPU2 captures matched before the race and differed after load when the player sound configuration was changed. In a separate Free Race with the player in the stock Vectra, the donor AI loop bank was found in guest RAM after 12000 frames. Compare the mix and loop transitions with the original game before treating audio fidelity as verified.
