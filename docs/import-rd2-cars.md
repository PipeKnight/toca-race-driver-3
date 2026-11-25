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

The development DB5 and Lancer outputs also contain strips that use the split. The playable DB5 uses its separately verified layout. The Mustang and Falcon outputs matched the previous converter byte for byte. The Lancer class and high-detail meshes are 454,332 and 503,740 bytes, above the portable preview limits. A diagnostic runner with larger limits loaded the new meshes and reproduced three unknown VIF commands. The replay advanced from the selector to the Oschersleben loading screen and remained there through frame 15,500. Local evidence is under `local/modding-preview-combined/qa-rd2-evo-rebuilt-long-check/`.

A future donor such as Colin McRae: DiRT will need its own archive reader and format converter. RD2-specific disc identification is deliberately kept separate from the RD3 packaging workflow.
