#!/usr/bin/env python3
"""Build the experimental DB5 exterior and driving data from two PS2 discs."""

import argparse
import csv
import io
from pathlib import Path
import struct

from BuildDtmVariant import append_variant, read_disc_range
from BuildRoadAmericaMod import EVENT_CATALOG_BYTES, EVENT_CATALOG_SECTOR, repack_jpak
from BuildTrackCollisionOverlay import (
    DONOR_DIRECTORY_HASH, REFERENCE_DIRECTORY_HASH, SECTOR_SIZE, read_exact, verify_directory,
)
from ConvertRd2CarModel import convert_model, convert_textures
from ModAssets import REFERENCE_PACKAGES, find_member, replace_member


def member(archive, name):
    return find_member(archive, name)[0].read(archive)


def driving_csv(donor, target, name):
    source_rows = list(csv.reader(member(donor, name).decode("ascii").splitlines()))
    target_rows = list(csv.reader(member(target, name).decode("ascii").splitlines()))
    if (len(source_rows) != 1 or len(target_rows) != 1 or len(source_rows[0]) != 130
            or len(target_rows[0]) != 200 or source_rows[0][:3] != ["car", "Aston Martin DB5", "Standard"]):
        raise ValueError(f"Unexpected DB5 or RD3 fields in {name}")
    source, row = source_rows[0], target_rows[0]
    # Preserve RD3's extra fields and its installed sound bank references.
    for start, end in ((1, 49), (50, 57), (62, 129)):
        for index in range(start, end):
            if source[index]:
                row[index] = source[index]
            elif 17 <= index < 49 or 68 <= index < 76:
                row[index] = "0"
    output = io.StringIO()
    csv.writer(output, lineterminator="\r\n").writerow(row)
    return output.getvalue().encode("ascii")


def build(rd2, rd3):
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
    changes = {"part.map": part_map, "dmg.ini": member(donor_mechanics, "dmg.ini")}
    for name in ("Mech.csv", "SimMech.csv"):
        changes[name] = driving_csv(donor_mechanics, variant, name)
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
    return {
        "DTMX_EXT.JPK": archive,
        "DTMX_20_HI.TEX": high_texture,
        "QA_TOURING_HI.MSH": high,
        "events.big": events,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rd2-disc", type=Path, required=True)
    parser.add_argument("--disc", type=Path, required=True, help="extracted or mounted RD3 PS2 disc")
    parser.add_argument("--output", type=Path, required=True, help="new add-on directory")
    args = parser.parse_args()
    try:
        result = build(args.rd2_disc, args.disc)
        args.output.mkdir()
        for name, data in result.items():
            (args.output / name).write_bytes(data)
    except (OSError, ValueError, struct.error) as error:
        parser.exit(1, f"DB5 build failed: {error}\n")
    print(args.output)


if __name__ == "__main__":
    main()
