#!/usr/bin/env python3
"""Build the experimental DB5 exterior and driving data from two PS2 discs."""

import argparse
import csv
import io
import math
from pathlib import Path
import re
import struct

from BuildDtmVariant import append_variant, read_disc_range
from BuildRoadAmericaMod import EVENT_CATALOG_BYTES, EVENT_CATALOG_SECTOR, read_bigf, repack_bigf, repack_jpak
from BuildTrackCollisionOverlay import (
    BIGF_ENTRY, DONOR_DIRECTORY_HASH, REFERENCE_DIRECTORY_HASH, SECTOR_SIZE, read_exact, verify_directory,
)
from ConvertRd2Db5Cabin import convert_cabin
from ConvertRd2Db5Cockpit import companion_atlas, convert_shell, convert_wipers, donor_atlas, embedded_atlas
from ConvertRd2Db5Doors import paint_doors
from ConvertRd2CarGlass import convert_windshield
from ConvertRd2CarModel import convert_model, convert_textures
from ModAssets import REFERENCE_PACKAGES, find_member, read_part_map, replace_member
from Ps2CarModel import model_sections
from Ps2CarShadow import build_db5_shadow


DB5_PLAYER_EFFECTS = (
    (b"IGNITI", b"ign_old", b"db5_ign"),
    (b"DAMAGE", b"edam", b"db5d"),
    (b"DETONA", b"det_small", b"db5_deton"),
)


def member(archive, name):
    return find_member(archive, name)[0].read(archive)


def tire_radii(model, part_map):
    _, base, _, sections = model_sections(model)
    first = struct.unpack_from("<I", model, sections[0][0] + 0x24)[0] - base
    high = read_part_map(part_map)[0]
    radii = []
    for left, right in ((46, 52), (58, 64)):
        heights = []
        for slot in (left, right):
            if high[slot] == 0xffffffff:
                raise ValueError(f"Missing DB5 tire in high-detail part slot {slot}")
            part = first + high[slot] * 0x30
            minimum = struct.unpack_from("<f", model, part + 0x14)[0]
            maximum = struct.unpack_from("<f", model, part + 0x24)[0]
            heights.append(maximum - minimum)
        radius = sum(heights) / 4
        if not 0.2 < radius < 0.5:
            raise ValueError("Invalid DB5 tire radius")
        radii.append(f"{radius:.6f}")
    return radii


def verify_wheel_lods(model, part_map):
    _, base, _, sections = model_sections(model)
    mapping = read_part_map(part_map)
    mounts = (42, 48, 54, 60)
    tires = (46, 52, 58, 64)
    reference = {}
    for lod, ((start, end), row) in enumerate(zip(sections, mapping, strict=True)):
        first, last = (value - base for value in struct.unpack_from("<2I", model, start + 0x24))
        for slot in (*mounts, *tires):
            index = row[slot]
            if lod == 4:
                if index != 0xffffffff:
                    raise ValueError("Expected the DB5's combined far-detail wheels in LOD 4")
                continue
            at = first + index * 0x30
            if not first <= at <= last - 0x30 or struct.unpack_from("<I", model, at)[0] != 0:
                raise ValueError(f"Missing DB5 wheel part {slot} in LOD {lod}")
            draw = struct.unpack_from("<I", model, at + 8)[0] - base
            if not last <= draw <= end - 0x60:
                raise ValueError(f"Invalid DB5 wheel transform in LOD {lod}, part {slot}")
            x, y, z, transform = struct.unpack_from("<3fI", model, draw + 0x50)
            if transform != (3 if slot in mounts else 6):
                raise ValueError(f"Unexpected DB5 wheel matrix index in LOD {lod}, part {slot}")
            position = (x, y, z)
            if not all(map(math.isfinite, position)):
                raise ValueError(f"Non-finite DB5 wheel pivot in LOD {lod}, part {slot}")
            if not lod:
                reference[slot] = position
            elif math.dist(position, reference[slot]) > .001:
                raise ValueError(f"DB5 wheel pivot moves at LOD {lod}, part {slot}")


def driving_csv(donor, target, name, radii, donor_sound=False):
    source_rows = list(csv.reader(member(donor, name).decode("ascii").splitlines()))
    target_rows = list(csv.reader(member(target, name).decode("ascii").splitlines()))
    if (len(source_rows) != 1 or len(target_rows) != 1 or len(source_rows[0]) != 130
            or len(target_rows[0]) != 200 or source_rows[0][:3] != ["car", "Aston Martin DB5", "Standard"]):
        raise ValueError(f"Unexpected DB5 or RD3 fields in {name}")
    source, row = source_rows[0], target_rows[0]
    # Preserve RD3's extra fields.
    for start, end in ((1, 49), (50, 57), (62, 129)):
        for index in range(start, end):
            if source[index]:
                row[index] = source[index]
            elif 17 <= index < 49 or 68 <= index < 76:
                row[index] = "0"
    row[145:147] = radii
    if donor_sound:
        row[57] = "DB5"
    output = io.StringIO()
    csv.writer(output, lineterminator="\r\n").writerow(row)
    return output.getvalue().encode("ascii")


def append_sound_members(reference, count, additions):
    existing, base = read_bigf(reference, count)
    names = {name.lower() for name in existing}
    for name in additions:
        if not 0 < len(name) <= 16 or not name.isascii() or b"\0" in name:
            raise ValueError("Invalid name for a car sound archive member")
        if name.lower() in names:
            raise ValueError(f"The sound archive already contains {name.decode('ascii')}")
        names.add(name.lower())
    total = count + len(additions)
    needed = max(0, 0x24 + total * BIGF_ENTRY.size - base)
    # Keep stock sector splits: a compact repack changes the car audio read batches.
    new_base = base + (needed + SECTOR_SIZE - 1) // SECTOR_SIZE * SECTOR_SIZE
    cars = bytearray(reference[:base].ljust(new_base, b"\0"))
    cars.extend(reference[base:])
    struct.pack_into("<2I", cars, 4, total, new_base)
    for i, (name, payload) in enumerate(additions.items(), count):
        cars.extend(bytes(-len(cars) % 64))
        BIGF_ENTRY.pack_into(cars, 0x24 + i * BIGF_ENTRY.size, name, len(payload), len(cars) - new_base)
        cars.extend(payload)
    return bytes(cars)


def donor_player_effects(player, donor):
    effects = {}
    for field, original, alias in DB5_PLAYER_EFFECTS:
        prefix = b"<" + field + b">"
        choice = prefix + original + b"\r\n"
        if player.count(choice) != 1:
            raise ValueError(f"Expected one DB5 {field.decode('ascii')} sound bank setting")
        # Keep the stock RD3 effect names untouched for every other car.
        player = player.replace(choice, prefix + alias + b"\r\n")
        effects[alias + b".msc"] = member(donor, (original + b".msc").decode("ascii"))
    return player, effects


def sound_assets(rd2, rd3, *, donor_effects=False):
    with (rd2 / "RD2_1.HUG").open("rb") as stream:
        donor = read_exact(stream, 1000174 * SECTOR_SIZE, 11115173)
    reference = read_disc_range(rd3, 2, 369392, 1345212)
    sounds, _ = read_bigf(reference, 211)
    additions = {
        name: member(donor, original) for original, name in (
            ("AstonDB5.ini", b"DB5.ini"), ("AstonDB5ai.ini", b"DB5ai.ini"),
            ("AstonDB5.msc", b"AstonDB5.msc"), ("AstonDB5ai.msc", b"AstonDB5ai.msc"))
    }
    if sounds[b"grup_db5.msc"] != member(donor, "grup_db5.msc"):
        raise ValueError("The shared DB5 gear shift bank does not match")

    if donor_effects:
        additions[b"DB5.ini"], effects = donor_player_effects(additions[b"DB5.ini"], donor)
        additions.update(effects)
    cars = append_sound_members(reference, 211, additions)
    system = read_disc_range(rd3, 2, 371022, 735)
    if not system.startswith(b"[Loops]\r\n") or b"\r\nMERCDTM=37\r\n" not in system or b"DB5=" in system:
        raise ValueError("The reference sound index does not have the expected loop mappings")
    # Keep the stock archive existence check on a valid path. The runtime retains the DB5 loop table.
    return {"cars.big": cars, "system.icz": system + b"DB5=37\r\n"}


def car_type_catalog(disc, mechanics):
    original = read_disc_range(disc, 1, 66833, 17152)
    car_types, base = read_bigf(original, 82)
    record = 110
    record_pattern = re.compile(rb"(?mi)^HOFIndex[ \t]*=[ \t]*(\d+)")
    used_records = {
        int(match[1]) for data in car_types.values() if (match := record_pattern.search(data))
    }
    if record in used_records or any(b"StringID=DB5" in data for data in car_types.values()):
        raise ValueError("The DB5 vehicle type or record index is already in use")
    row = next(csv.reader(member(mechanics, "Mech.csv").decode("ascii").splitlines()))
    if len(row) != 130 or row[1] != "Aston Martin DB5" or not row[3].isdigit():
        raise ValueError("Expected a DB5 mechanics row with a vehicle weight")
    car_types[b"ASTDB5.ini"] = (
        "[info]\r\nStringID=DB5\r\nFullName=Aston Martin DB5\r\nShortName=Aston Martin DB5\r\n"
        f"Manufacturer=AST\r\nWeight={row[3]}\r\nBHP=0\r\n0To60=0\r\nHOFIndex = {record}\r\n"
    ).encode("ascii")
    base = max(base, (0x24 + BIGF_ENTRY.size * len(car_types) + 31) & ~31)
    return repack_bigf(original, car_types, base, base, len(original))


def build_exterior_camera_archive(rd3):
    original = read_disc_range(rd3, 1, 67712, 42755)
    cameras = member(original, "carcam.ini")
    if re.search(rb"(?mi)^\[DB5\]", cameras):
        raise ValueError("The RD3 camera catalog already contains a DB5 entry")
    # Use the clear forward pose and put the reverse-facing eye ahead of the
    # body so it can see traffic without clipping the imported geometry.
    updated = cameras.rstrip(b"\r\n") + b"\r\n\r\n[DB5]\r\n\r\n"
    for suffix in (b"", b"_HSS", b"_VSS"):
        updated += (b"bon_y" + suffix + b"=1.900000\r\n" + b"bon_z" + suffix + b"=-0.850000\r\n"
                    + b"bon_pitch" + suffix + b"=0.079000\r\n"
                    + b"r_bon_y" + suffix + b"=2.700000\r\n" + b"r_bon_z" + suffix + b"=4.500000\r\n")
    return replace_member(original, ["carcam.ini"], updated)


def build(rd2, rd3, donor_sound=False, donor_cockpit=False, *, donor_effects=False):
    if donor_effects and not donor_sound:
        raise ValueError("DB5 donor effects require donor sound")
    verify_directory(rd2 / "RD2.DIR", DONOR_DIRECTORY_HASH)
    verify_directory(rd3 / "RDH.DIR", REFERENCE_DIRECTORY_HASH)
    with (rd2 / "RD2_1.HUG").open("rb") as stream:
        donor_models = read_exact(stream, 787442 * SECTOR_SIZE, 7009268)
        donor_mechanics = read_exact(stream, 790877 * SECTOR_SIZE, 6 * SECTOR_SIZE)
    if b"[vc_2_0]" not in member(donor_mechanics, "num.ini"):
        raise ValueError("Expected mechanics for RD2 variant vc_2")

    target = read_disc_range(rd3, *REFERENCE_PACKAGES["dtm-cars"])
    donor_model = member(donor_models, "db5.mdl")
    donor_mesh = member(donor_models, "db5.msh")
    # Preserve the mesh layout validated with the DB5-specific door and glass conversions.
    model, high, low, part_map, _, _ = convert_model(
        donor_model, donor_mesh, member(target, "DTM_C_Klasse.mdl"), native_vu_banks=False)
    verify_wheel_lods(model, part_map)
    high = paint_doors(model, high, part_map)
    low = paint_doors(model, low, part_map, (1, 2, 3))
    high = convert_windshield(model, high, part_map, {0: 3})
    low = convert_windshield(model, low, part_map, {1: 3, 2: 1, 3: 1})
    texture = convert_textures(member(donor_models, "vc_2.tex"), member(target, "dtmx_13.tex"))
    high_texture = convert_textures(
        member(donor_models, "vc_2_hi.tex"), read_disc_range(rd3, 2, 185648, 381204))
    cockpit_members = ()
    if donor_cockpit:
        with (rd2 / "RD2_1.HUG").open("rb") as stream:
            donor_interiors = read_exact(stream, 797863 * SECTOR_SIZE, 10001732)
        image, palette = donor_atlas(member(donor_interiors, "int_db5_hi.tex"))
        interior_model = member(donor_interiors, "int_db5.mdl")
        interior_mesh = member(donor_interiors, "int_db5.msh")
        cockpit = convert_shell(interior_model, interior_mesh, member(target, "int_dtm.px"))
        cockpit = convert_wipers(interior_model, interior_mesh, cockpit)
        cockpit = convert_cabin(interior_model, interior_mesh, donor_model, donor_mesh, cockpit, image, palette)
        cockpit_members = (
            (b"int_db5.px", b"int_dtm.px", embedded_atlas(cockpit, image, palette)),
            # Keep the companion TIM2 archive in the existing 63-member pack layout.
            (b"int_db5.big", b"int_dtm.big", companion_atlas(
                member(target, "int_dtm.big"), image, palette)),
        )
    archive = append_variant(target, low, extra_members=cockpit_members)
    variant = member(archive, "dtmx_20.big")
    radii = tire_radii(model, part_map)
    variant_type = member(variant, "type.ini")
    if b"type=CKL" not in variant_type:
        raise ValueError("Expected the RD3 Mercedes template type")
    exterior_section = re.compile(rb"(?ms)^\[Exterior\]\r\n.*?(?=^\[)")
    donor_interior = member(donor_mechanics, "int.ini")
    donor_exterior = exterior_section.search(donor_interior)
    interior = member(variant, "int.ini")
    if donor_exterior is None or b"Part0=2\r\nNumParts=1\r\n" not in donor_exterior[0]:
        raise ValueError("Expected the DB5 exterior binding for the cockpit view")
    interior, replaced = exterior_section.subn(donor_exterior[0], interior)
    if replaced != 1 or read_part_map(part_map)[0][2] == 0xffffffff:
        raise ValueError("The DB5 cockpit exterior part is unavailable")
    if donor_cockpit:
        # Keep the right-hand seat and frame the road above the dash through the donor windscreen.
        interior = b"\r\n".join(line for line in donor_interior.splitlines()
                                if line and not line.startswith((b"Netting=", b"DigitialDisplay="))) + b"\r\n"
        camera = b"[Camera]\r\nAngle=-0.02\r\nZoom=0.87\r\nZ=0.23\r\nY=1.72\r\nX=0.32\r\n"
        interior, count = re.subn(rb"(?ms)^\[Camera\]\r\n.*?(?=^\[Shift\])", camera, interior)
        if count != 1:
            raise ValueError("Expected one DB5 interior camera section")
    changes = {
        "part.map": part_map, "dmg.ini": member(donor_mechanics, "dmg.ini"),
        "type.ini": variant_type.replace(b"type=CKL", b"type=DB5"),
        "int.ini": interior,
    }
    for name in ("Mech.csv", "SimMech.csv"):
        changes[name] = driving_csv(donor_mechanics, variant, name, radii, donor_sound)
    for name, data in changes.items():
        variant = replace_member(variant, [name], data)
    archive = repack_jpak(archive, 61 + len(cockpit_members), {
        b"dtmx_20.big": variant, b"dtmx_20.tex": texture, b"QA_Touring.mdl": model,
    }, compressor=lambda data: data)

    events = read_disc_range(rd3, 1, EVENT_CATALOG_SECTOR, EVENT_CATALOG_BYTES)
    intro = member(events, "1st__.ini")
    car = b"CareerOfferCarID = dtmx_13/CKL"
    if intro.count(car) != 1:
        raise ValueError("The reference introductory race's DTM car assignment was not found")
    events = replace_member(events, ["1st__.ini"], intro.replace(car, b"CareerOfferCarID = dtmx_20/DB5"))
    result = {
        "DTMX_EXT.JPK": archive,
        "DTMX_20_HI.TEX": high_texture,
        "QA_TOURING_HI.MSH": high,
        "events.big": events,
        "cartype.big": car_type_catalog(rd3, donor_mechanics),
        "globfil1.jpk": build_exterior_camera_archive(rd3),
        "db5.shd": build_db5_shadow(donor_model),
    }
    if donor_sound:
        result.update(sound_assets(rd2, rd3, donor_effects=donor_effects))
    if donor_cockpit:
        result["db5-dials.ini"] = b"DB5DIALS 1\r\n"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rd2-disc", type=Path, required=True)
    parser.add_argument("--disc", type=Path, required=True, help="extracted or mounted RD3 PS2 disc")
    parser.add_argument("--output", type=Path, required=True, help="new add-on directory")
    parser.add_argument("--donor-sound", action="store_true", help="add the experimental DB5 legacy samples")
    parser.add_argument("--donor-effects", action="store_true", help="also import the RD2 player effect banks (requires --donor-sound)")
    parser.add_argument("--donor-cockpit", action="store_true", help="add the experimental DB5 cockpit shell and atlas")
    args = parser.parse_args()
    try:
        result = build(args.rd2_disc, args.disc, args.donor_sound, args.donor_cockpit, donor_effects=args.donor_effects)
        args.output.mkdir()
        for name, data in result.items():
            (args.output / name).write_bytes(data)
    except (OSError, KeyError, ValueError, struct.error) as error:
        parser.exit(1, f"DB5 build failed: {error}\n")
    print(args.output)


if __name__ == "__main__":
    main()
