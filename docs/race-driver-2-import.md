# Import from Race Driver 2 on PS2

Use your own PS2 copies of Race Driver 2 `SLES-52638` v1.02 and TOCA Race Driver 3 `SLUS-21182` v1.02. This guide covers Road America and both A1-Ring layouts through a verified circuit importer. The car example fits a DB5 roof strip and copies the donor's body texture pages onto the QA Touring test variant. A complete DB5 conversion remains in development.

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

A complete conversion additionally needs the donor material and texture mapping, every detail level, the RD3 part map, wheel and suspension attachments, damage, and vehicle mechanics. The sample RD2 model's part table differs from the layout checked by the RD3 tool. A complete port needs in-game checks for the selector, other cars on the grid, cameras, LOD transitions, a classified finish, and damage.
