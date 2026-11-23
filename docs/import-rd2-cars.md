# Import cars from Race Driver 2

`scripts/ImportRd2Car.py` is a front end for local PS2 disc data. It separates discovery and model conversion from the final playable preset. It uses the reference Race Driver 2 `SLES-52638` v1.02 and TOCA Race Driver 3 `SLUS-21182` v1.02 disc directories. Use Python 3.10 or later.

```powershell
python scripts/ImportRd2Car.py list
python scripts/ImportRd2Car.py catalog --rd2-disc F:\ --class vintage
python scripts/ImportRd2Car.py build db5 --rd2-disc F:\ --disc G:\ --output local\db5-pack
```

`list` shows the playable presets; currently only `db5` is registered. `build` produces a `--dtm-mod` pack and enables the experimental donor sound and cockpit by default. Use `--stock-sound` or `--stock-cockpit` to keep the matching RD3 template component. Launch a current source-built launcher with `--dtm-mod local\db5-pack` and select the Aston Martin DB5 as described in the [DB5 test instructions](race-driver-2-import.md#build-the-experimental-pack-from-both-discs).

`catalog` reads the donor class's `lookup.ini` and lists livery IDs and their model IDs. For a known class range not yet named in the tool, substitute `--class-range HUG SECTOR BYTES` for `--class vintage`. `HUG` is the numbered `RD2_*.HUG`; the sector size is 2,048 bytes. Use the extent of the class archive, not the separate mechanics or sound archive.

```powershell
python scripts/ImportRd2Car.py convert vc_2 --rd2-disc F:\ --disc G:\ --output local\db5-model
python scripts/Ps2CarModel.py model-info local\db5-model\car.mdl local\db5-model\car.msh `
    --hi-mesh local\db5-model\car_hi.msh --part-map local\db5-model\part.map
```

`convert` accepts livery IDs from `catalog`. It emits a development model, split detail-level meshes, textures, and a part map for the supported RD2 geometry layout. This is not a playable pack: it does not invent a car type, assign event slots, or convert mechanics, damage, engine sounds, cockpit attachments, or shadows automatically. Check the model in game before adding a preset. In particular, verify wheel and suspension motion at all detail levels, material bindings, damage, and a separate registration.

The model-only conversion has been exercised with the DB5 (`vc_2`), Jaguar E-Type (`vc_0`), and 1968 Mustang (`vc_4`) from the Vintage class. Only the DB5 has a playable preset, with its remaining work listed in the [acceptance checklist](acceptance-checklist.md#aston-martin-db5-completion).

A future donor such as Colin McRae: DiRT will need its own archive reader and format converter. RD2-specific disc identification is deliberately kept separate from the RD3 packaging workflow.
