#!/usr/bin/env python3
"""Build the experimental DB5 exterior and driving data from two PS2 discs."""

import argparse
import csv
import io
from pathlib import Path
import struct

from BuildDtmVariant import append_variant, read_disc_range
from BuildRoadAmericaMod import EVENT_CATALOG_BYTES, EVENT_CATALOG_SECTOR, read_bigf, repack_bigf, repack_jpak
from BuildTrackCollisionOverlay import (
    BIGF_ENTRY, DONOR_DIRECTORY_HASH, REFERENCE_DIRECTORY_HASH, SECTOR_SIZE, read_exact, verify_directory,
)
from ConvertRd2CarModel import convert_model, convert_textures
from ModAssets import REFERENCE_PACKAGES, find_member, read_part_map, replace_member
from Ps2CarModel import model_sections


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


def build(rd2, rd3, donor_sound=False):
    verify_directory(rd2 / "RD2.DIR", DONOR_DIRECTORY_HASH)
    verify_directory(rd3 / "RDH.DIR", REFERENCE_DIRECTORY_HASH)
    with (rd2 / "RD2_1.HUG").open("rb") as stream:
        donor_models = read_exact(stream, 787442 * SECTOR_SIZE, 7009268)
        donor_mechanics = read_exact(stream, 790877 * SECTOR_SIZE, 6 * SECTOR_SIZE)
    if b"[vc_2_0]" not in member(donor_mechanics, "num.ini"):
        raise ValueError("Expected mechanics for RD2 variant vc_2")

    target = read_disc_range(rd3, *REFERENCE_PACKAGES["dtm-cars"])
    model, high, low, part_map, _, _ = convert_model(
        member(donor_models, "db5.mdl"), member(donor_models, "db5.msh"), member(target, "DTM_C_Klasse.mdl"))
    texture = convert_textures(member(donor_models, "vc_2.tex"), member(target, "dtmx_13.tex"))
    high_texture = convert_textures(
        member(donor_models, "vc_2_hi.tex"), read_disc_range(rd3, 2, 185648, 381204))
    archive = append_variant(target, low)
    variant = member(archive, "dtmx_20.big")
    radii = tire_radii(model, part_map)
    changes = {"part.map": part_map, "dmg.ini": member(donor_mechanics, "dmg.ini")}
    for name in ("Mech.csv", "SimMech.csv"):
        changes[name] = driving_csv(donor_mechanics, variant, name, radii, donor_sound)
    for name, data in changes.items():
        variant = replace_member(variant, [name], data)
    archive = repack_jpak(archive, 61, {
        b"dtmx_20.big": variant, b"dtmx_20.tex": texture, b"QA_Touring.mdl": model,
    }, compressor=lambda data: data)

    events = read_disc_range(rd3, 1, EVENT_CATALOG_SECTOR, EVENT_CATALOG_BYTES)
    intro = member(events, "1st__.ini")
    car = b"CareerOfferCarID = dtmx_13/CKL"
    if intro.count(car) != 1:
        raise ValueError("The reference introductory race's DTM car assignment was not found")
    events = replace_member(events, ["1st__.ini"], intro.replace(car, b"CareerOfferCarID = dtmx_20/CKL"))
    result = {
        "DTMX_EXT.JPK": archive,
        "DTMX_20_HI.TEX": high_texture,
        "QA_TOURING_HI.MSH": high,
        "events.big": events,
    }
    if donor_sound:
        result.update(sound_assets(rd2, rd3))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rd2-disc", type=Path, required=True)
    parser.add_argument("--disc", type=Path, required=True, help="extracted or mounted RD3 PS2 disc")
    parser.add_argument("--output", type=Path, required=True, help="new add-on directory")
    parser.add_argument("--donor-sound", action="store_true", help="add the experimental DB5 legacy samples")
    args = parser.parse_args()
    try:
        result = build(args.rd2_disc, args.disc, args.donor_sound)
        args.output.mkdir()
        for name, data in result.items():
            (args.output / name).write_bytes(data)
    except (OSError, KeyError, ValueError, struct.error) as error:
        parser.exit(1, f"DB5 build failed: {error}\n")
    print(args.output)


if __name__ == "__main__":
    main()
