# Import cars from Race Driver 2

`scripts/ImportRd2Car.py` is a front end for local PS2 disc data. Use Python 3.10 or later and TOCA Race Driver 3 `SLUS-21182` v1.02 as the conversion target. Automatic catalog and conversion look up RD2 vehicle packages by their contents and can work with other PS2 donor revisions that use the same formats. An explicit `--class-range` from the catalog is checked against the archive bounds and package layout. The named `vintage` sector range and playable DB5 preset require the reference Race Driver 2 disc `SLES-52638` v1.02.

```powershell
python scripts/ImportRd2Car.py list
python scripts/ImportRd2Car.py catalog --rd2-disc F:\
python scripts/ImportRd2Car.py build db5 --rd2-disc F:\ --disc G:\ --output local\db5-pack
```

`list` shows the playable presets; currently only `db5` is registered. `build` produces a `--dtm-mod` pack and enables the experimental donor sound and cockpit by default. Use `--stock-sound` or `--stock-cockpit` to keep the matching RD3 template component. Launch a current source-built launcher with `--dtm-mod local\db5-pack` and select the Aston Martin DB5 as described in the [DB5 test instructions](race-driver-2-import.md#build-the-experimental-pack-from-both-discs).

Use `build db5 --donor-effects` to also import the RD2 ignition, engine damage, and detonation banks. This is an opt-in audio experiment, not part of the normal preset. It cannot be combined with `--stock-sound`.

By default, `catalog` discovers class archives on the disc, reads their `lookup.ini` files, and lists liveries with the required model, class mesh, and both texture files. `convert` finds a livery by ID without a supplied archive offset. If the same ID describes different models or textures, the command reports the candidate ranges for `--class-range HUG SECTOR BYTES`. `--class vintage` still limits lookup to the original Vintage class.

```powershell
python scripts/ImportRd2Car.py convert vc_2 --rd2-disc F:\ --disc G:\ --output local\db5-model
python scripts/ImportRd2Car.py audit local\db5-model
python scripts/ImportRd2Car.py audit local\db5-pack --dtm-pack
python scripts/Ps2CarModel.py model-info local\db5-model\car.mdl local\db5-model\car.msh `
    --hi-mesh local\db5-model\car_hi.msh --part-map local\db5-model\part.map
```

`convert` accepts livery IDs from `catalog`. It emits a development model, split detail-level meshes, textures, and a part map for the supported RD2 geometry layout. This is not a playable pack: it does not invent a car type, assign event slots, or convert mechanics, damage, engine sounds, cockpit attachments, or shadows automatically. Check the model in game before adding a preset. In particular, verify wheel and suspension motion at all detail levels, material bindings, damage, and a separate registration.

The automatic path has converted the Aston Martin DB5 `vc_2`, Jaguar E-Type `vc_0`, 1968 Mustang `vc_4`, Mitsubishi Lancer Evolution VII `bs_0`, and Ford Falcon BA `v8_1`. The DB5 is the playable preset. See the [acceptance checklist](acceptance-checklist.md#aston-martin-db5-completion) for its game checks.

`audit` checks the five detail levels against their DMA ranges and part mappings, verifies the wheel pivots, and reports tire radii, indexed body pages, and files that exceed the current DTM preview loader's limits. Use `--dtm-pack` for the installed variant. Both forms report the SHA-256 of each audited asset. The Jaguar stores one of its four numbered body pages after several glass descriptors. The tool finds the pages by their shared name prefix and page number.

The exterior converter translates strip uploads and their header pointers to the RD3 VU1 buffers. This frees the low addresses that RD3 uses for clipping. The DB5 playable preset and Falcon development profile retain their separately tested layouts. Rebuild older bundles with `convert` to apply the current model and material conversions.

The 1968 Mustang previously showed horizontal bands, missing textures, and a blank view in the Oschersleben intro fixture. A matched Windows Direct3D 12 replay of the rebuilt model kept the HUD, body paint, and scenery in the bonnet view at rest and in the look-back and chase views at 57 and 90 mph. The replay reported no malformed VIF, GIF, or VU1 commands. The importer also suppresses the bright additive windshield pass. Fine lines remain visible on the glass in the chase look-back view. The fixture uses the DB5 cockpit and registration. [Per-car checklist](acceptance-checklist.md#import-acceptance-by-asset)

Ford Falcon BA `v8_1` passed the installed asset audit. With the glass correction alone, the Oschersleben replay preserved the blue livery, removed the cyan wash on the windshield, and reported no malformed VIF, GIF, or VU1 commands. Thin reflections remain on the windshield. The DB5 camera fixture still shows a large blue polygon in the forward bonnet view. A trial using the entire stock Falcon camera profile introduced rendering corruption in this fixture. A separate replay with the RD3 VU1 buffer layout and the unchanged DB5 camera recorded 16,649 invalid GS writes. The importer keeps the verified buffer layout for the Falcon.

The Jaguar passed the asset audit while a Windows replay still showed bands and 26,449 invalid GS writes. The first invalid write occurred at frame 8,306 during car selection. The matching DMA block contained a 30-vertex strip with three material passes. The third GIF vertex stream starts 195 quadwords into the bank and reaches past the RD3 bank boundary. The captured output included vertex data where a GS register address belonged.

The converter now splits oversized strips of this layout when translating to RD3 banks. Each fragment keeps the three GIF passes plus the original positions, normals, and texture coordinates. Two shared vertices at the seam preserve the triangles and their winding. The converter rebuilds DMA lengths, VIF addresses, call relocations, and per-LOD packet counts. For the Jaguar, four strips become eight and the high-detail model grows from 513 to 517 packets. The installed audit passes and the rebuilt high-detail mesh stays within the preview limit. The matched Oschersleben replay reached frame 12,640 without invalid GS writes or the previous bands. The fixture uses the DB5 cockpit and registration. Local evidence is under `local/modding-preview-combined/qa-rd2-jaguar-compact-split-check/`.

The development DB5 and Lancer outputs also contain strips that use the split. The playable DB5 uses its separately verified layout. The Mustang and Falcon outputs matched the previous strip converter byte for byte.

### Run the Lancer Evolution VII test pack

Build the Windows launcher from the updated source to get the 512 KiB limit for each external mesh. Pass the mounted or extracted PS2 disc directories from your own copies of both games.

```powershell
$pack = Join-Path $work 'Lancer Evolution VII test'
python scripts/ImportRd2Car.py build-test-pack bs_0 --rd2-disc $rd2 --disc $rd3 --output $pack
python scripts/ImportRd2Car.py audit $pack --dtm-pack
& $launcher --disc $rd3Iso --dtm-mod $pack --data-dir "$work\lancer-test-player"
```

The importer finds the model by the RD2 class lookup and matches the donor's damage and cockpit metadata through the `bs_0` sections in `num.ini`. The test pack uses the donor damage settings and exterior part binding. It offers the converted Lancer in the introductory Oschersleben DTM race, using the Mercedes registration, mechanics, and cockpit shell. The class and high-detail meshes are 454,332 and 503,740 bytes. A private test disc directory with both BIGF packages moved into a differently numbered HUG produced the same installed pack.

The earlier fixture with Mercedes damage parameters stalled on the Oschersleben loading screen. The first invalid VIF commands appeared at frame 10,444. The guest draw copy contained coordinates in a position that still held the expected UNPACK command in the source model. The VIF1 DMA channel paused after reading the invalid command. Replacing only the damage settings with the donor Lancer configuration let the same input reach the race and run through frame 15,500 without those VIF errors. The final test pack uses the Lancer binding for the exterior in cockpit view and applies the windshield converter at all five detail levels.

The first Windows rear-facing replay showed two faulty windshield bindings. The alternate texture at block `0x3300` sampled the livery and drove a glass pixel to RGB `#FFFFFF`. Reusing the neighboring glass binding at `0x3100` brought the same pixel to `#4D4B48` in the software trace. A texture dump from draw 25,913 then showed the stripes sampled from the lower half of that page. The importer now suppresses the affected extra draw group with `XYZ3` at each detail level and retains the base glass. A cold Direct3D 12 replay showed the driver through the windshield with the lettering and stripes absent in the checked view. Local captures are in `local/modding-preview-combined/evo7-final-windshield-review.png`.

The Windows 11 Direct3D 12 run on an RTX 4070 used recorded input to finish the one-lap introduction in 21st place in 2:34.30 and reached the classification screen. The game autosaved to a test memory card. A fresh process without a runtime checkpoint read the byte-identical saved card and reached the career championship menu. The result and reload captures are in `local/modding-preview-combined/evo7-finish-review.png` and `local/modding-preview-combined/evo7-autosave-reload-qa.png`.

The test pack uses the stock RD3 `PS2M` cockpit. The road remained visible up to 70 mph in the Windows replay, but only the upper edge of the steering rim was in frame. This capture is in `local/modding-preview-combined/evo7-cockpit-review.png`. The donor cockpit, steering pivot, standalone registration and mechanics still require separate verification.

In the RD2 PS2 `int_left.p3d` sample, the word after `CP3D` is `0x02060101`. A little-endian offset at byte `0x08` points to a directory at `0x1AF90`. The four material names are `gen01`, `gen02`, `clear_09`, and `badge`. The companion `int_left.big` archive supplies `gen01.tm2`, `gen02.tm2`, and `disp_num.tm2`.

At directory offset `0x20`, a count of 47 and a table pointer lead to a set of eight-byte records. The first word in each record points to a 16-byte aligned packet. In the first nine packets, the word at packet offset `0x28` points to either `gen01` or `gen02`. At directory offset `0x28`, another count and table pointer lead to 607 32-bit file offsets. This table reaches the end of the file. The ZModeler RaceDriverP3D import source expects a version word of `2`, so this sample requires its own format reader.

A future donor such as Colin McRae: DiRT will need its own archive reader and format converter. RD2-specific disc identification is deliberately kept separate from the RD3 packaging workflow.
