# Import from Race Driver 2 on PS2

Use your own PS2 discs. The verified donor is Race Driver 2 `SLES-52638` v1.02 and the target is TOCA Race Driver 3 `SLUS-21182` v1.02. The automatic circuit and development vehicle importers can locate compatible packages on other RD2 revisions with the same archive formats. Verify each new revision in game. The playable DB5 preset still uses the verified donor revision.

## Convert Road America and A1-Ring

Use Windows preview 6 or later and Python 3.10 or later. Run the commands from the repository root. Set `$rd2` to the mounted or extracted Race Driver 2 disc directory containing `RD2.DIR` and the numbered `RD2_*.HUG` archives. Set `$rd3` to the mounted or extracted TOCA Race Driver 3 disc directory containing `RDH.DIR` and `RDH_1.HUG`. The launcher can use the RD3 ISO directly. The builder needs a new output directory under an existing parent. It checks the RD3 directory hash and discovers RD2 packages by their indexed members and format.

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

In **Free Race**, choose **Autosport Clio Cup**. Select **Road America** in Sunny or Rain when available, or choose **A1-Ring GP** or **A1-Ring Short** in Sunny. The same imports can be used in Time Trial. To build the Road America pack on its own, omit `--include-a1-ring`. Use the same data directory on a second launch to reload the add-on memory card.

The two verified Road America sky assets identify the sunny and wet scenes even when their sector order changes. For other variants, run `python scripts/ImportRd2Track.py catalog --rd2-disc $rd2` and use the printed one-based scene numbers with `--road-america-sunny-scene` and `--road-america-rain-scene`. A pack without a selected or recognized wet scene offers Sunny. If a layout has several incompatible or ambiguous variants, use the [standalone builder](#discover-and-build-a-standalone-rd2-layout) to choose one scene and audit its route.

| Circuit | Donor ID | Add-on resources |
| --- | --- | --- |
| Road America | `roa` | Pack root for Sunny and `rain` for Rain |
| A1-Ring GP | `a11` | `tqa2` |
| A1-Ring Short | `a12` | `tqa3` |

The importer puts the donor `col.col` and the converted `AILD` v9 route into `TRACK.JPK`. It rebuilds the donor's PS2 scene-node tree into the RD3 layout and writes it to `DMA1.JPK`. Keep both packages together with the pack's `tracks.big` and `events.big`. The imports use some companion resources from Oschersleben, including the A1-Ring loading screens. The Windows tests finished races and restored separate Time Trial records for the three circuits. [Circuit conversion and verification](ps2-disc-and-archives.md#add-a1-ring-gp-and-short)

For another RD2 circuit, use the [standalone builder](#discover-and-build-a-standalone-rd2-layout). It identifies the scene, collision, and `.aid` route, then checks their formats and whether the converted data fits the target slots. [Track authoring and validation](modding.md#tracks)

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

A later matched traffic test sampled all four DB5 wheel matrices from VU memory. Relative to the chassis, the wheel translations changed by 0.8–1.3 mm across adjacent frames at the LOD 1 → 2 transition, and by 1.2–2.2 mm over the twelve sampled frames spanning LOD 2 → 3. This checks for a visible attachment jump in the undamaged AI car; it does not cover wheel damage, player steering through the same transitions, or the combined LOD 4 silhouette.

A separate player LOD 0 test followed a barrier impact at Oschersleben. All four tire draws were found in 921 consecutive frames for the DB5 and for a stock Mercedes using the same controller sequence. Both cars showed tire spin and vertical motion relative to the chassis; the front wheels steered and the rear wheels did not. The largest adjacent-frame tire position change in those samples was **5.87 mm** for the DB5 and **7.20 mm** for the Mercedes. The cars hit the barrier at different speeds, so this is an attachment and geometry check, not a claim that their handling matches. Four sampled images from each instrumented run were byte-identical to that car's normal-runner images.

In a stock Audi DTM race with an AI DB5, the normal detail selection submitted the DB5 body at LOD 1, 2, 3, and then 4 as it moved away. The far mesh uses 25 strips; its combined geometry includes the four tire silhouettes without separate wheel draw nodes. This confirms the combined mesh was submitted, not that the far silhouette matches every damaged pose.

The exterior renderer draws a group of DB5 door strips that originally used an interior trim page. The converter rebinds that group and projects UVs and normalized outward normals from the same door. The class mesh uses a separate painted panel page at `0x349c`. Its `0x341c` group largely covers the window frame and uses different UVs. The converter uses the class panel page for LODs 1–3. [Door verification](#test-the-bonnet-camera)

### Find the donor mechanics

The `vc_2` mechanics package is at `RD2_1.HUG` sector 790877 and occupies six sectors. Its `num.ini` identifies the variant. Both mechanics CSVs identify the Aston Martin DB5 and the damage file identifies `db5`. Extract these to inspect independent copies of the standard and simulation settings.

```powershell
$mechanics = Join-Path $work 'DB5 mechanics'
New-Item -ItemType Directory -Path $mechanics | Out-Null
foreach ($member in 'Mech.csv', 'SimMech.csv', 'dmg.ini', 'int.ini', 'num.ini') {
    python scripts/ModAssets.py extract --rd2-disc $rd2 --range 1 790877 12288 $member "$mechanics\$member"
}
```

Each RD2 mechanics row has 130 columns. The RD3 QA Touring rows each have 200 columns. Copying the overlapping driving fields into the RD3 rows changed the car's speed at the same frame of a scripted Oschersleben run. The two RD3 tire radius fields use the mean of the corresponding donor tire model heights divided by two. For the DB5 this gives 0.322218 metres on both axles. The remaining RD3-only driving fields retain the template values. The full exterior still needs verification when the AI drives the DB5, including the door materials, wheel motion, and suspension through LOD transitions.

### Build the experimental pack from both discs

Use Windows `v0.1.0-preview.8` or a launcher built from the current source manifest. These builds include the converted model and variant type patches.

```powershell
$pack = Join-Path $work 'DB5 drive test'
python scripts/BuildRd2Db5Variant.py --rd2-disc $rd2 --disc $rd3 --output $pack
& $launcher --disc $rd3Iso --dtm-mod $pack --data-dir "$work\db5-drive-test-player"
```

Start the introductory race from a fresh data directory. The builder installs the exterior, both texture sets, the part map, the overlapping driving fields, and the RD2 damage configuration in the additional DTM entry. The default build uses the Mercedes cockpit and sound. The sound option below enables the donor audio.

The builder adds `DB5` to the 82-entry `Cartype.big` from `RDH_1.HUG` sector 66833. The new record uses the game's existing Aston Martin manufacturer ID `AST` and a separate car record index, 110. It copies the 1450 kg weight from the DB5 mechanics row. The power and acceleration figures still need source data. The car type file, the introductory car offer, and the added DTM roster entry all use `DB5` as the type. The original Mercedes keeps `CKL`. The Free Race variant still requires the DTM event to be unlocked.

The selector requests a separate shadow file using the type ID. The builder generates `db5.shd`, a low-poly body, roof, and four wheel casters sized from the DB5 model. A source-built runner with the DB5 shadow patch loads this file for `Cars\Shadows\DB5.shd` and retains the Mercedes shadow fallback for earlier packs. A matched Windows 11 check showed the different shadow under the DB5 in the introductory race. A separate selector test showed the DB5 model, its name and 1450 kg in an isolated event fixture. The Mercedes team label remains visible because the added driver shares the original event's team registration.

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
python scripts/Ps2CarModel.py mesh-preview "$cockpit\int_db5.msh" "$cockpit\int_db5_lod0.obj" --model "$cockpit\int_db5.mdl" --lod 0 --combined-lods
python scripts/Ps2CockpitModel.py "$cockpit\int_dtm.px" "$cockpit\int_dtm.obj"
```

The donor `int.ini` identifies exterior part 2 for the cockpit view and provides the camera, steering, and driver coordinates. The builder copies the donor's exterior binding into the variant's interior configuration. The Mercedes configuration referred to part 115, which the DB5 lacks. It produced horizontal rendering corruption when switching cameras. On Windows 11, using the donor binding restored an intact view when entering and leaving the cockpit camera. The default build uses the Mercedes interior model and camera coordinates.

The RD2 OBJ preview exported 2,074 triangles at LOD 0 and 424 at each of LODs 1–4. Change `--lod` and the output filename to inspect the lower levels. The preview includes all cockpit parts at that level; the current importer transfers only the main shell.

The 12 stock RD3 `.px` cockpit models tested share a little-endian offset at file position `0x20` to a block containing the scene names. At offset `0x24` within that block is the byte length of the null-separated name table, which starts at `0x28`. For `int_dtm.px`, the block starts at `0xf3a0` and the table has 388 bytes. Its names include `int_main_body` and `r_door`. The table also names lights and targets. Match materials and drawable objects separately when mapping the donor cockpit.

The RD3 preview command recognizes the stock triangle strips in all 12 models. It exports local positions and UVs grouped by draw section and file offset, and lists the corresponding scene node names in OBJ comments. The DTM model has 20 draw sections with 398 strips and 2,189 non-degenerate triangles, including the first strip of each section. For example, section 0 belongs to `int_main_body`, and sections 1–4 contain the right wiper and its positions. The OBJ preview omits the scene transforms, attachment animation, and material state needed to import a working cockpit.

In the stock files, each draw section has a 40-byte header followed by a VIF payload. The word immediately before the payload gives its length, a multiple of 16 bytes. The following word belongs to the next section header, or is the final zero word at the end of the file. The first strip sets the GS material state and starts at VU buffer `0x100`; subsequent strips cycle through `0x200`, `0x300`, and `0x100`. The converter replaces the whole shell section, including its first strip, while preserving the section's GS setup and leaving the stock scene graph intact.

### Test the imported cockpit shell

Use a launcher built with the variant cockpit patch from the source manifest. Create a separate development pack with `--donor-cockpit`. The sound option can be used in the same pack.

```powershell
$cockpitPack = Join-Path $work 'DB5 cockpit test'
python scripts/BuildRd2Db5Variant.py --rd2-disc $rd2 --disc $rd3 --output $cockpitPack --donor-cockpit --donor-sound
& $launcher --disc $rd3Iso --dtm-mod $cockpitPack --data-dir "$work\db5-cockpit-test-player"
```

This adds a separate `int_db5.px` and `int_db5.big` inside the DTM package. The builder splits the 64 strips of RD2 part 119 into the main shell and rear mirror assembly. The camera stays on the right-hand seat. Its position, downward pitch, and zoom frame more of the steering rim while keeping the road and both dials visible. A Windows Direct3D 12 replay checked full left, full right, and return to center at Oschersleben. The steering hub region matched the initial neutral frame after releasing the stick. A second replay with the rebuilt pack showed the lane and both dials during steering corrections and at 72 mph. The local comparison is `local/modding-preview-combined/db5-cockpit-framing-final.png` and the moving frames are in `db5-cockpit-steering-at-speed.png` in the same directory.

The running game uploads the atlas from the `PS2M` model itself. Changing the companion TIM2 archive alone did not affect matching cockpit captures. The first two embedded GS transfers in the stock DTM model upload the index data and palette at `0x3180` and `0x38bc` in GS blocks. The builder samples the donor's 256 × 256 indexed atlas at 128 × 128, reshuffles the indices for the existing 64 × 64 RGBA32 upload, and copies the palette into the second transfer. Increasing the first upload at its existing address would overwrite the texture at `0x31c0`. The companion archive keeps a matching TIM2 copy in the existing pack layout.

On Windows 11 with Direct3D 12, a matched-input Oschersleben test found the exact converted image and palette bytes in guest RAM. The cockpit frame changed after replacing the embedded uploads; all six sampled menu and non-cockpit frames stayed byte-identical, including the views after switching back out of the cockpit.

With `--donor-cockpit` and `--donor-sound` together, a Windows run drove the scripted final part of the introductory Oschersleben race from a frame-3250 checkpoint made with that same pack. The run reached the post-race cutscene by frame 11000. A separate run repeated the finish with the new shadow. A later 21-car Free Race in the unlocked-event fixture reached Race Results with the donor sound, shadow, wipers, and corrected door paint. Its recorded replay matched 683 checkpoints. This test did not cover cold reloading a DB5 autosave or the normal DTM unlock.

On the combined Windows build from `c1fac4b`, a later power-on replay used an isolated profile with autosave enabled and the current DB5 and circuit packs. The normal Direct3D 12 runner matched all **840** recorded checkpoints through the Oschersleben finish and post-race cutscene. It wrote the autosave and reached the World Tour difficulty prompt. A separate cold launch reported “Load Successful” on that card and did not change it.

On that profile, **Simulation Modes → Free Race → Touring Car → DTM** was locked before the introduction and marked **New** after the introduction autosave. In DTM, choose **Aston Martin DB5** at the end of the car carousel. The standard event let the DB5 start a 21-car Oschersleben race. The earlier Clio event substitution does not reproduce the stock unlock or car availability checks; do not use it to test progression.

The standard Free Race classified the DB5 **21st in 2:54.74**. The replay from the grid matched **824** recorded checkpoints on the normal runner. A separate power-on repetition matched the sampled race and standings images byte for byte and wrote the same autosave bytes. The card passed filesystem and ECC checks and loaded from power-on without further writes. This did not establish a separate `DB5` Time Trial record.

The DB5 is also selectable in DTM Time Trial. Ending the test session wrote an autosave, but the `LapRecords` block still held the existing Oschersleben benchmark and no `DB5` row. The stock writer at `0x0014e1e8` chooses a championship's group, matches the four-byte track ID, then stores the best time and its car type. `DB5` has its own type ID and `HOFIndex`, but those do not give it an independent personal best in the same DTM event. A faster lap can update that event's shared entry; a separate event or record handling change is needed to keep independent entries for DB5 and Mercedes.

The converter retargets the two wipers from donor parts 79–81 and 83–85. Their geometry and pivot matrices replace the DTM wiper and add a separate left wiper to its scene graph. The third RD3 pose repeats the donor's end pose. A Windows rain fixture showed both blades sweeping; the matching sunny test parked them at the base of the windshield.

The donor trim from cockpit parts 12 and 13 replaces the DTM door panels. The wheel sprite from exterior part 11 supplies the radius and steering-column tilt. The authored three-spoke rim lies in the local XY plane so it rotates around the `steering_wheel` node's tilted Z axis. On Windows 11 with Direct3D 12, cold-start Oschersleben captures showed the road ahead on the grid and during the race. At full left and right input, the rim retained its projected bounds and the hub centroid moved by less than one tenth of a pixel. The rear mirror uses an authored reflective face sized from the donor glass and placed on the donor mount. The side-mirror housings retain the RD3 geometry and reflection state, fitted to the donor door pivots.

In `SLUS-21182` v1.02, the `RearviewMirror` HUD resource defines a screen-space rectangle, separate from the cockpit's named mirror nodes. A diagnostic run showed both at once: the HUD rectangle showed moving scenery while the relocated physical rear glass stayed dark. In a DTM Free Race, cycling away from the cockpit and back restored the live overlay without illuminating the physical glass. The stock Mercedes control also showed the moving HUD rectangle, but its stock cockpit framing did not show a physical mirror. The cockpit's mode-dependent setup has a branch to a no-op in this revision, so displaying the live HUD is not evidence that the cockpit mirror receives a live texture. Keep live physical reflections listed as unverified.

The cockpit build adds a speedometer and tachometer. Its `db5-dials.ini` enables the reference runner's instrument update path. On `SLUS-21182` v1.02 the code reads the active speed in metres per second and the normalized engine rev signal, then rotates the marked needle strips. The speedometer spans 160 mph. The tachometer shows the game's rev range without claiming a physical DB5 redline calibration. Matched Windows captures showed both needles move with the live signals; with the update disabled the same meshes stayed at their zero positions. The instrument validation covers single-player only.

### Test the bonnet camera

The playable DB5 pack adds forward and rear-facing bonnet positions to `carcam.ini` in `globfil1.jpk`. Build the Windows runner with the DB5 camera patch, then launch with the rebuilt pack. The forward pose shows the road above the bonnet. Looking back temporarily moves the eye ahead of and above the car, with traffic visible behind it. This avoids the near-plane clipping that produced malformed VU1 draw packets in the original look-back position.

An Oschersleben run from a cold start on Windows 11 with Direct3D 12 checked the bonnet look-back at rest and at 56 mph, then returned to a clear forward view at 69 mph. It also checked the chase look-back at 90 mph. The DB5's exterior windshield keeps its tinted pass. Its additive reflection packet uses a vertex update without a triangle draw, so it still satisfies the two-pass VU packet layout. Other cars continue to use their own windshield materials.

The simplified left and right doors now take their paint page, UVs, normals, and lighting constants from the class mesh's outer door skin. The overlapping trim keeps its paint without drawing a second additive reflection over the skin. A cold Oschersleben run showed the red left door and its light roundel on the passing AI DB5. A separate TV replay showed the corrected right door.

### Test the legacy DB5 sound banks

Build the Windows launcher with the variant sound patch from the source manifest, then create a separate pack with `--donor-sound`.

```powershell
$soundPack = Join-Path $work 'DB5 sound test'
python scripts/BuildRd2Db5Variant.py --rd2-disc $rd2 --disc $rd3 --output $soundPack --donor-sound
& $launcher --disc $rd3Iso --dtm-mod $soundPack --data-dir "$work\db5-sound-test-player"
```

The builder reads the 11,115,173-byte RD2 sound archive at `RD2_1.HUG` sector 1000174. It appends four members to a local copy of RD3's 211-entry `Sound\Cars.big` at `RDH_2.HUG` sector 369392. The stock payload moves only by whole sectors to make room for the expanded directory. Its member offsets relative to the data base and their positions within sectors are preserved. The player and AI INIs get the `DB5` variant prefix. Their `<ELOOPS>` values keep the original sample filenames. The existing `grup_db5.msc` gear-change bank in RD3 matches the donor bytes. The optional `cars.big` and `system.icz` files must be installed together.

Both mechanics CSVs set column 57, counting from zero, to `DB5` only for the added variant. The separate `Sound\System.icz` index at `RDH_2.HUG` sector 371022 maps that name to bank 37 for the game's file existence check. Without a mapping the game tries `Unknown.big` and falls back to `Puma.big`. That path halted the Windows runner during the introductory race load. For a player using the DB5 sound pack, the runner keeps the legacy loop table and skips the streaming engine initializer. Stock engines still use their normal initialization.

On Windows 11, the DB5 ran through frame 3900 of the introductory Oschersleben race with the streaming initializer skipped. Its legacy player loop bank and shift sample were found in guest RAM. Two SPU2 captures matched before the race and differed after load when the player sound configuration was changed. In a separate Free Race with the player in the stock Vectra, the donor AI loop bank was found in guest RAM after 12000 frames. A byte comparison of the current combined pack confirmed that all 211 original RD3 bank entries were unchanged and that the added player and AI files and shared gear-shift bank matched RD2. This checks the packaged data, not the in-game mix or loop transitions.

The earlier compact `Cars.big` repack split stock entries across different sectors. In a matched stock Mercedes Time Trial at Oschersleben it changed the sound chip output, even though the stock bank payloads and sampled images matched. The sector-aligned rebuild reproduced the stock read counts and grouping for all 21 observed `Cars.big` reads and matched all **1,280,000** stereo sample frames byte for byte. The DB5 introduction also booted with the revised bank. A power-on replay of the full DTM Free Race reproduced the previous standings screen and autosave byte for byte with this archive. The audio comparison covers that stock car and session; fidelity of the DB5's own mix and loop transitions to RD2 remains open.

The optional `--donor-effects` flag adds three private player banks for ignition, engine damage, and detonation, because the stock RD3 banks of the same names differ from the RD2 originals. It leaves the stock names and assets untouched. An introductory-race test found sample data from all three private banks in IOP memory, with matching video frames. A separate race with a stock Mercedes player and an AI DB5 found the donor AI loop and shared gear-shift banks, but none of the private player banks. A power-on DTM Free Race with this option reproduced the default DB5 standings screen and autosave byte for byte.

Do not enable this option when checking stock audio parity. The matched stock Mercedes Time Trial with the three private entries had identical sampled images and a PCM difference about 44 dB below the full signal over seconds 8–26. A size-matched padding control without the extra entries reproduced the original PCM exactly, so archive size alone does not explain the difference. The default preset keeps the sector-aligned four-member archive.
## Discover and build a standalone RD2 layout

The catalog scans sector-aligned PS2 BIGF directories and validates member names, offsets, and lengths. It lists model classes and circuit IDs with their collision scenes and candidate race routes. Its JSON report includes the RD2 directory hash for identification, along with whether it matches the reference. On `SLES-52638` v1.02, 67 scenes across 54 IDs passed route pairing and structural conversion. With another revision, save the catalog output and the `BOOT2` and `VER` lines from `SYSTEM.CNF` when reporting a compatibility result.

A local regression used reference RD2 packages relocated to a different HUG, a changed directory checksum, and reversed Sunny and Rain scene order. The multi-course builder reproduced all ten original output files byte for byte. Automatic `vc_2` discovery reproduced all six DB5 development-bundle files. The relocated fixture checks archive placement. Additional regional PS2 discs still need separate in-game coverage.

```powershell
python scripts/Rd2AssetCatalog.py F:\
python scripts/ImportRd2Track.py catalog --rd2-disc F:\
python scripts/ImportRd2Track.py build ade --rd2-disc F:\ --disc G:\ `
    --name "Adelaide (RD2)" --output local\adelaide-pack
python scripts/ImportRd2Track.py audit local\adelaide-pack
& $launcher --disc $rd3Iso --road-america local\adelaide-pack --data-dir local\adelaide-player
```

The track builder pairs the selected scene with a matching AID route, checks the section lengths, and creates one `tqa1` entry with a free record ID. It generates the map icon, collision and route archive, and the scene archive. Use **Autosport Clio Cup** in Free Race or Time Trial. Choose `--scene` using the numbered catalog entries when a layout has multiple scenes. Each generated pack registers one weather choice for its selected scene. Give each standalone pack a separate `--data-dir` so its lap records cannot collide with those of another layout using the same slot.

When the selected scene contains its own `<layout>cam.ini`, the importer writes those trackside cameras and activation zones to `replay-cameras.ini` beside the generated `TRACK.JPK`. It supplies zero pitch offset and disabled blackout when a donor camera omits those RD3 fields. Rebuild older packs and use a runner with the replay-camera patch. Verify the cameras through **View Replay** after a finish.

RD3 looks up camera data in `TRACK.BIG`. Imported slots request a name such as `tqa3Cam.ini`, while the Oschersleben reference archive has only `osc1Cam.ini`. The Windows runner supplies the imported layout's camera file to the original replay parser. Road America Rain uses the camera file in the `rain` subfolder when present.

On Windows 11 with Direct3D 12, A1-Ring Short loaded all 13 donor camera positions from `replay-cameras.ini`. After the one-lap race, **View Replay** showed the field from a fixed camera by the fence and then from another camera along the pits. The comparison run without the camera file used the chase view. Captures are in `local/modding-preview-combined/qa-a1-short-tv-sidecar-verified-replay/`.

The AID converter builds the RD3 pit driving line between the donor's two corridor edges and keeps the donor's stall path in the separate RD3 stall lane. It places sixteen numbered stall intervals along service areas with room for them. The Clio Cup assigns team stalls by index, including index 15 for the player in the mandatory-pit fixture. Shorter service areas keep their donor stalls and the audit shows the unassigned RD3 indices. The importer measures pit lane distances along the driving line and puts the lap wrap at the physical pit finish gate. Rebuild existing imports to update their `TRACK.JPK` routes.

`audit` lists the timing splits, pit entry gates, and stall marker pairs. It checks the main and pit driving lines, both pit corridor edges, the grid lanes, and marked stall intervals for upward-facing collision. Segment indices identify the starting station. `pit_first_gate_station` identifies the first pit entry gate. `pit_approach_widths_m` gives the distance between the corridor edges at each station up to and including that gate. Compare those widths with the car's position when investigating a return to the racing line before service. Use in-game tests to verify surface heights, shortcuts, pit service, race timing, and saves. For multi-course packs, pass a slot such as `--slot tqa5` for the authored Tsukuba example. Pass `--weather rain` with the Road America slot to audit the separate wet archive.

The automatic path built and reached the grid at Adelaide (`ade`) and `a13` from a cold Windows start. The initial Adelaide run cut a corner and received a 20-second penalty. A second run followed the center of the racing surface and reached the checkered flag in 19th with a valid **3:12.71** lap. The standard Direct3D 12 replay matched 747 checkpoints through Race Results and wrote 772 pages to the test card. A cold start reported a successful profile load and preserved the card's SHA-256. With the portable launcher's EFU timing enabled, the exaggerated body reflection from the diagnostic driver no longer appeared in the matched finish frames.

The standalone `a13` pack also finished a one-lap Free Race, showed Race Results, and autosaved. Its continuation replay matched all 747 checkpoints. The saved card passed filesystem and ECC checks and cold-loaded without any change to its SHA-256.

The corrected route passed the structural check on all 67 indexed donor scenes. In rebuilt packs, the Road America Sunny and Rain, A1-Ring GP and Short, Adelaide, and standalone `a13` routes have sixteen paired stalls and upward-facing collision under every sampled main, pit, and grid station and between stations. Every marked stop interval in these six variants also passed. The earlier Road America and GP exit gaps and Adelaide approach gap were on the stall line that the importer had used as the driving line. Follow the checklist for mandatory pit races and cold-load verification. [Per-circuit checklist](acceptance-checklist.md#circuits)

The audit also found upward-facing collision along both pit corridor edges on these six variants. The narrowest approach station before or at the first gate measured 0.88 m on both Road America variants, 1.68 m on A1-Ring GP and standalone `a13`, 1.50 m on A1-Ring Short, and 1.63 m on Adelaide. Review actual car positions and service telemetry before changing the corridor or moving a gate.

On A1-Ring Short, an earlier import sent the player below the terrain during the mandatory stop. Changing only the numeric distance at the pit finish line could also lock race progression at that point. With the rebuilt distance axis and sixteen assignments, the Windows test reached the pit service countdown, completed it, returned to the racing surface, and gave the player control on lap three. The tested route matched the archive's lane coordinates and its pit distances within 0.2 mm. The continuation finished all five laps and placed Player One 14th in **6:52.98** after penalties were applied. Race Results disqualified Steve Makowski. His telemetry shows a return to the main route at pit station 5 on lap five, followed by another approach. The autosave passed the memory-card filesystem and ECC check and cold-loaded byte-for-byte.

#### Verify A1-Ring pit service and classification

The first five-lap A1-Ring Short test classified the player 14th in **6:52.98** and disqualified Steve Makowski. A replay of his first pit attempt confirmed that he reached his assigned slot 3 just after the timing line, received a stall assignment, and drove through without service. Moving the markers slightly and bringing the stall line closer to the pit driving line reproduced the failure. Swapping the start and end tags for slots 2 and 3 put his stall ahead of the timing line. From the same checkpoint, Makowski decelerated, completed service, and left the stall. Both import commands apply the tag swap to the verified Short route signature. It changes four marker bytes in the route and preserves the timing line and all lane coordinates.

The GP and Short packs both pass the floor audit for the main line, pit line, corridor edges, start grid, and all sixteen paired pit stalls. The tested archives have SHA-256 `dd28c9f59787288017e2383130f8ac45ca012a98a6a33331f77be98081aa3464` (GP) and `89bbf204600954de78a9f8470275cdae8f4abe19c921eda2b7261cbda9a26ec2` (Short).

On Windows with Direct3D 12, GP completed a five-lap Autosport Clio Cup Free Race with mandatory stops. Player One entered the pits on lap two and finished 20th in **12:40.33**. All 19 opponents completed service and all 20 drivers received a finish time. The continuation reached Race Results and wrote 772 autosave pages. A separate cold launch showed **Load Successful**, read 341 pages, and left the save byte-identical. Its filesystem and ECC checks passed. Local evidence is in `qa-a1-gp-mandatory-baseline/` and `qa-a1-gp-full-classification-cold/` under `local/modding-preview-combined/`.

The rebuilt Short layout repeated the five-lap mandatory-stop race from power-on. Player One pitted on lap two and finished 20th in **7:08.30**. Makowski completed service and placed third in **6:34.45**. The telemetry showed service completion for all 19 opponents, and Race Results gave all 20 drivers finish times. The game wrote 772 autosave pages, the card passed filesystem and ECC verification, and a separate cold launch showed **Load Successful** with 341 reads and zero writes. Local evidence is in `qa-a1-short-mandatory-final-grid/`, `qa-a1-short-mandatory-final/`, and `qa-a1-short-classification-early/` under `local/modding-preview-combined/`.

#### Verify Road America Sunny pit service and classification

The Windows 11 Direct3D 12 test used the rebuilt Road America Sunny archive with sixteen paired stalls. The archive SHA-256 was `abc689e96400ba6e96491d3e24c1ca0e82e355664087374937cb5119f6e437b0`. The test cold-started a five-lap Clio Cup Free Race with mandatory stops and used a checkpoint to continue the automated drive after the player's pit visit. The player entered service on lap two, returned to the road, and finished 20th in **17:09.13**. All 19 opponents completed service. The last opponent stopped on lap five. Race Results showed a finish time for every driver.

The game wrote 772 autosave pages. The card passed the filesystem and ECC checks. A separate launch showed **Load Successful**, read 341 pages, and preserved the saved card byte for byte. The traces and captures are in `local/modding-preview-combined/qa-road-america-sunny-rebuilt-service/`, `qa-road-america-sunny-mandatory-finish/`, and `qa-road-america-sunny-road-classification-cold/`. The Rain test remains open.

#### Verify Adelaide pit service and classification

The baseline Adelaide test drove through the pit lane on lap one without being serviced. The second-lap entry reached the service countdown and returned control to the player on the racing surface on lap three. The continuation drove through lap five on the same rebuilt pit-distance and sixteen-stall pack. Race Results classified Player One 19th in **12:22.68** and disqualified Adam Murphy. Matching the route trace with the driver data in the test checkpoint identified Murphy as car 13. He entered the pit route on lap three at frame 33,431. On frame 33,721 the game evaluated him at station 9, roughly 20 m beyond the line of the outer corridor edge between stations 8 and 9. It switched him back to the racing line before service.

The autosave passed the memory-card filesystem and ECC check. A cold launch of the normal runner opened the saved career, read 341 pages, and left the card byte-identical. Local captures are in `local/modding-preview-combined/qa-adelaide-distance-pit-second-lap/pit-service-and-exit.png`, `local/modding-preview-combined/qa-adelaide-mandatory-results/classification.png`, and `local/modding-preview-combined/qa-adelaide-mandatory-cold/profile.png`.

An 8 m minimum approach width alone reproduced Murphy's original return at the same frame and position. A second test kept the wider approach and moved the first pit gate and speed-limit gate up to stations 5 and 6. The continuation from the lap-two checkpoint classified all 20 cars. The standalone importer applies the earlier gates and the wider approach to Adelaide routes with the tested station counts and marker pattern.

The Windows Direct3D 12 test started from power-on, selected Adelaide in the Clio Cup with mandatory stops, and drove all five laps with recorded menu inputs and the local controller driver. The player entered the pit stop on lap two. The controller driver touched the exit barrier and recovered. All 19 opponents reached the completed-service state, and Race Results classified all 20 drivers. Player One finished tenth in **11:58.81** and Murphy finished 14th in **12:52.25**.

The rebuilt `TRACK.JPK` matched the race pack byte for byte (SHA-256 `7e6e1319443bfe66a5ca26d5f98c62db19cc65dbb2257225599bda34c43a8dd3`). The rebuilt pack passed collision sampling on the route, both pit edges, and all 16 stalls. The game wrote 772 autosave pages. The card passed filesystem and ECC verification. A separate cold launch reported **Load Successful**, read 341 pages, and left the card byte-identical. See `local/modding-preview-combined/qa-adelaide-early-gate-power-on-race/`, `qa-adelaide-early-gate-power-on-results/`, and `qa-adelaide-early-gate-power-on-reload/`.

The builder reports incompatible route sections, ambiguous scene pairings, missing scene members, or converted scenes that exceed the reference extent. The multi-course builder also supports the verified Road America Rain scene.
