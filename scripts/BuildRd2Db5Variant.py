#!/usr/bin/env python3
"""Build the experimental DB5 exterior and driving data from two PS2 discs."""

import argparse
import csv
import io
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
from ConvertRd2CarModel import convert_model, convert_textures
from ModAssets import REFERENCE_PACKAGES, find_member, read_part_map, replace_member
from Ps2CarModel import model_sections
from Ps2CarShadow import build_db5_shadow


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


def sound_assets(rd2, rd3):
    with (rd2 / "RD2_1.HUG").open("rb") as stream:
        donor = read_exact(stream, 1000174 * SECTOR_SIZE, 11115173)
    reference = read_disc_range(rd3, 2, 369392, 1345212)
    sounds, _ = read_bigf(reference, 211)
    for original, name in (
            ("AstonDB5.ini", b"DB5.ini"), ("AstonDB5ai.ini", b"DB5ai.ini"),
            ("AstonDB5.msc", b"AstonDB5.msc"), ("AstonDB5ai.msc", b"AstonDB5ai.msc")):
        if any(key.lower() == name.lower() for key in sounds):
            raise ValueError(f"The reference sound archive already contains {name.decode('ascii')}")
        sounds[name] = member(donor, original)
    if sounds[b"grup_db5.msc"] != member(donor, "grup_db5.msc"):
        raise ValueError("The shared DB5 gear shift bank does not match")

    base = (0x24 + BIGF_ENTRY.size * len(sounds) + SECTOR_SIZE - 1) & -SECTOR_SIZE
    size = base + sum((len(payload) + 31) & ~31 for payload in sounds.values())
    cars = repack_bigf(reference[:0x24].ljust(size, b"\0"), sounds, base, base, size)
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


def build(rd2, rd3, donor_sound=False, donor_cockpit=False):
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
    model, high, low, part_map, _, _ = convert_model(
        donor_model, donor_mesh, member(target, "DTM_C_Klasse.mdl"))
    high = paint_doors(model, high, part_map)
    low = paint_doors(model, low, part_map, lods=(1, 2, 3))
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
        # Keep the donor's right-hand seat and put the eye behind the restored wheel and rear mirror.
        interior = b"\r\n".join(line for line in donor_interior.splitlines()
                                if line and not line.startswith((b"Netting=", b"DigitialDisplay="))) + b"\r\n"
        camera = b"[Camera]\r\nAngle=-0.16\r\nZoom=1.03\r\nZ=-0.24\r\nY=1.50\r\nX=0.32\r\n"
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
        "db5.shd": build_db5_shadow(donor_model),
    }
    if donor_sound:
        result.update(sound_assets(rd2, rd3))
    if donor_cockpit:
        result["db5-dials.ini"] = b"DB5DIALS 1\r\n"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rd2-disc", type=Path, required=True)
    parser.add_argument("--disc", type=Path, required=True, help="extracted or mounted RD3 PS2 disc")
    parser.add_argument("--output", type=Path, required=True, help="new add-on directory")
    parser.add_argument("--donor-sound", action="store_true", help="add the experimental DB5 legacy samples")
    parser.add_argument("--donor-cockpit", action="store_true", help="add the experimental DB5 cockpit shell and atlas")
    args = parser.parse_args()
    try:
        result = build(args.rd2_disc, args.disc, args.donor_sound, args.donor_cockpit)
        args.output.mkdir()
        for name, data in result.items():
            (args.output / name).write_bytes(data)
    except (OSError, KeyError, ValueError, struct.error) as error:
        parser.exit(1, f"DB5 build failed: {error}\n")
    print(args.output)


if __name__ == "__main__":
    main()
