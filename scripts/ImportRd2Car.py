#!/usr/bin/env python3
"""Discover and convert cars from a local Race Driver 2 PS2 disc."""

import argparse
from configparser import ConfigParser, Error as IniError
from pathlib import Path
import re
import struct

from BuildDtmVariant import read_disc_range
from BuildRd2Db5Variant import build as build_db5, member
from BuildTrackCollisionOverlay import DONOR_DIRECTORY_HASH, REFERENCE_DIRECTORY_HASH, SECTOR_SIZE, read_exact, verify_directory
from ConvertRd2CarModel import convert_model, convert_textures
from ModAssets import REFERENCE_PACKAGES


RD2_CLASSES = {"vintage": (1, 787442, 7009268)}
PLAYABLE = {"db5": ("Aston Martin DB5", build_db5)}


def donor_class(disc, extent):
    verify_directory(disc / "RD2.DIR", DONOR_DIRECTORY_HASH)
    hug, sector, size = extent
    if hug not in (0, 1, 2) or sector < 0 or not 0 < size <= 32 * 1024 * 1024:
        raise ValueError("Invalid class range (HUG 0–2, non-negative sector, at most 32 MiB)")
    with (disc / f"RD2_{hug}.HUG").open("rb") as stream:
        return read_exact(stream, sector * SECTOR_SIZE, size)


def variants(archive):
    ini = ConfigParser(interpolation=None)
    ini.read_string(member(archive, "lookup.ini").decode("ascii"))
    output = dict(ini["lookup"])
    if not output or any(not re.fullmatch(r"[a-zA-Z0-9_]+", item)
                         for pair in output.items() for item in pair):
        raise ValueError("Expected simple vehicle and variant IDs in the RD2 class lookup")
    return output


def convert_car(archive, variant, disc):
    naming = variants(archive)
    if variant not in naming:
        raise ValueError(f"Unknown variant {variant!r}; use catalog to list the IDs")
    car = naming[variant]
    verify_directory(disc / "RDH.DIR", REFERENCE_DIRECTORY_HASH)
    template = read_disc_range(disc, *REFERENCE_PACKAGES["dtm-cars"])
    model, high, low, part_map, _, _ = convert_model(
        member(archive, f"{car}.mdl"), member(archive, f"{car}.msh"), member(template, "DTM_C_Klasse.mdl"))
    texture = convert_textures(member(archive, f"{variant}.tex"), member(template, "dtmx_13.tex"))
    high_texture = convert_textures(member(archive, f"{variant}_hi.tex"), read_disc_range(disc, 2, 185648, 381204))
    return {"car.mdl": model, "car_hi.msh": high, "car.msh": low, "part.map": part_map,
            "car.tex": texture, "car_hi.tex": high_texture}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="list the supported playable presets")
    catalog = commands.add_parser("catalog", help="list variants in a donor class")
    convert = commands.add_parser("convert", help="build a development model pair (not a playable pack)")
    build = commands.add_parser("build", help="build an add-on for a supported playable preset")
    for command in (catalog, convert, build):
        command.add_argument("--rd2-disc", type=Path, required=True, help="mounted or extracted RD2 disc directory")
    for command in (catalog, convert):
        source = command.add_mutually_exclusive_group()
        source.add_argument("--class", dest="donor_class", choices=RD2_CLASSES, default="vintage")
        source.add_argument("--class-range", type=int, nargs=3, metavar=("HUG", "SECTOR", "BYTES"))
    for command in (convert, build):
        command.add_argument("--disc", type=Path, required=True, help="mounted or extracted RD3 disc directory")
        command.add_argument("--output", type=Path, required=True, help="new output directory")
    convert.add_argument("variant", type=str.lower)
    build.add_argument("car", type=str.lower, choices=PLAYABLE)
    build.add_argument("--stock-sound", action="store_true", help="retain the RD3 template engine audio")
    build.add_argument("--stock-cockpit", action="store_true", help="retain the RD3 template cockpit")
    args = parser.parse_args()
    try:
        if args.command == "list":
            for key, (name, _) in PLAYABLE.items():
                print(f"{key:<12} {name}")
            return
        if args.command != "build":
            archive = donor_class(args.rd2_disc, args.class_range or RD2_CLASSES[args.donor_class])
            if args.command == "catalog":
                for variant, model in variants(archive).items():
                    print(f"{variant:<12} {model}")
                return
        if args.output.exists():
            raise ValueError("Choose a new output directory")
        if args.command == "convert":
            result = convert_car(archive, args.variant, args.disc)
        else:
            _, builder = PLAYABLE[args.car]
            result = builder(args.rd2_disc, args.disc, donor_sound=not args.stock_sound,
                             donor_cockpit=not args.stock_cockpit)
        args.output.mkdir()
        for name, data in result.items():
            (args.output / name).write_bytes(data)
    except (OSError, UnicodeError, IniError, KeyError, ValueError, struct.error) as error:
        parser.exit(1, f"RD2 car import failed: {error}\n")
    print(args.output)


if __name__ == "__main__":
    main()
