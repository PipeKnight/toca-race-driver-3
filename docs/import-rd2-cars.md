# Import cars from Race Driver 2

`scripts/ImportRd2Car.py` is a front end for local PS2 disc data. It separates discovery and model conversion from the final playable preset. It uses the reference Race Driver 2 `SLES-52638` v1.02 and TOCA Race Driver 3 `SLUS-21182` v1.02 disc directories. Use Python 3.10 or later.

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

The Jaguar passes the asset audit. Translating its VU1 uploads removed the unterminated draw packets. The matched replay still recorded 26,449 invalid GS writes and showed bands. The first invalid write occurred at frame 8,306 during car selection, before the race camera became active. A diagnostic using the available Jaguar exterior bindings and its donor damage settings reached the same first invalid write.

The Lancer class and high-detail meshes remain 454,332 and 502,956 bytes, above the portable preview limits. A diagnostic runner with larger limits loaded both meshes. The car selection test reported three unknown VIF commands with the translated buffers and stayed on the selection screen. Both cars need additional rendering work before registration.

A future donor such as Colin McRae: DiRT will need its own archive reader and format converter. RD2-specific disc identification is deliberately kept separate from the RD3 packaging workflow.
