#!/usr/bin/env python3
"""Discover and convert cars from a local Race Driver 2 PS2 disc."""

import argparse
from configparser import ConfigParser, Error as IniError
import hashlib
import json
from pathlib import Path
import re
import struct
from tempfile import TemporaryDirectory

from BuildDtmVariant import read_disc_range
from BuildRd2Db5Variant import build as build_db5, member, tire_radii, verify_wheel_lods
from BuildTrackCollisionOverlay import DONOR_DIRECTORY_HASH, REFERENCE_DIRECTORY_HASH, SECTOR_SIZE, read_exact, verify_directory
from ConvertRd2CarGlass import convert_windshield
from ConvertRd2CarModel import convert_model, convert_textures
from ModAssets import REFERENCE_PACKAGES
from Ps2CarModel import inspect_model, relocation_table
from Ps2CarTexture import body_uploads
from Rd2AssetCatalog import car_packages, scan_disc


RD2_CLASSES = {"vintage": (1, 787442, 7009268)}
PLAYABLE = {"db5": ("Aston Martin DB5", build_db5)}
WINDSHIELD_STRIPS = {
    "fal_ba": (7, 5, 1, 1, 4),
    "mustang68": (1, 1, 1, 1, 4),
}


def donor_class(disc, extent):
    verify_directory(disc / "RD2.DIR", DONOR_DIRECTORY_HASH)
    hug, sector, size = extent
    if hug not in (0, 1, 2) or sector < 0 or not 0 < size <= 32 * 1024 * 1024:
        raise ValueError("Invalid class range (HUG 0–2, non-negative sector, at most 32 MiB)")
    with (disc / f"RD2_{hug}.HUG").open("rb") as stream:
        return read_exact(stream, sector * SECTOR_SIZE, size)


def variant_lookup(data):
    ini = ConfigParser(interpolation=None)
    ini.read_string(data.decode("ascii"))
    section = next((name for name in ini.sections() if name.lower() == "lookup"), "lookup")
    output = {variant: model.strip().lower() for variant, model in ini[section].items()}
    if not output or any(not re.fullmatch(r"[a-zA-Z0-9_]+", item)
                         for pair in output.items() for item in pair):
        raise ValueError("Expected simple vehicle and variant IDs in the RD2 class lookup")
    return output


def variants(archive):
    return variant_lookup(member(archive, "lookup.ini"))


def discover_variants(disc):
    for package in car_packages(scan_disc(disc)):
        try:
            lookup = variant_lookup(package.member(disc, "lookup.ini"))
        except (UnicodeError, IniError, KeyError, ValueError):
            continue
        names = set(package.names)
        for variant, model in lookup.items():
            required = (f"{model}.mdl", f"{model}.msh", f"{variant}.tex", f"{variant}_hi.tex")
            if names.issuperset(required):
                yield variant, model, package, required


def discover_car(disc, variant):
    unique = {}
    for known, _, package, files in discover_variants(disc):
        if known == variant:
            fingerprints = tuple(hashlib.sha256(package.member(disc, name)).digest() for name in files)
            unique.setdefault(fingerprints, package)
    if not unique:
        raise ValueError(f"No complete model and texture set for variant {variant!r}; use catalog to list IDs")
    if len(unique) != 1:
        ranges = "; ".join(f"{p.hug} {p.sector} {p.size}" for p in unique.values())
        raise ValueError(f"Variant {variant!r} has distinct donor packages. Select --class-range from {ranges}")
    return next(iter(unique.values())).read(disc)


def convert_car(archive, variant, disc):
    naming = variants(archive)
    if variant not in naming:
        raise ValueError(f"Unknown variant {variant!r}; use catalog to list the IDs")
    car = naming[variant]
    verify_directory(disc / "RDH.DIR", REFERENCE_DIRECTORY_HASH)
    template = read_disc_range(disc, *REFERENCE_PACKAGES["dtm-cars"])
    model, high, low, part_map, _, _ = convert_model(
        member(archive, f"{car}.mdl"), member(archive, f"{car}.msh"), member(template, "DTM_C_Klasse.mdl"),
        native_vu_banks=car != "fal_ba")
    if car in WINDSHIELD_STRIPS:
        strips = WINDSHIELD_STRIPS[car]
        high = convert_windshield(model, high, part_map, {0: strips[0]})
        low = convert_windshield(model, low, part_map, dict(enumerate(strips[1:], start=1)))
    texture = convert_textures(member(archive, f"{variant}.tex"), member(template, "dtmx_13.tex"))
    high_texture = convert_textures(member(archive, f"{variant}_hi.tex"), read_disc_range(disc, 2, 185648, 381204))
    return {"car.mdl": model, "car_hi.msh": high, "car.msh": low, "part.map": part_map,
            "car.tex": texture, "car_hi.tex": high_texture}


def audit_bundle(folder, *, dtm_pack=False):
    if dtm_pack:
        archive = (folder / "DTMX_EXT.JPK").read_bytes()
        variant = member(archive, "dtmx_20.big")
        files = {
            "car.mdl": member(archive, "QA_Touring.mdl"),
            "car.msh": member(archive, "QA_Touring.msh"),
            "car_hi.msh": (folder / "QA_TOURING_HI.MSH").read_bytes(),
            "part.map": member(variant, "part.map"),
            "car.tex": member(archive, "dtmx_20.tex"),
            "car_hi.tex": (folder / "DTMX_20_HI.TEX").read_bytes(),
        }
    else:
        names = ("car.mdl", "car.msh", "car_hi.msh", "part.map", "car.tex", "car_hi.tex")
        files = {name: (folder / name).read_bytes() for name in names}
    report = inspect_model(files["car.mdl"], files["car.msh"],
                           hi_mesh=files["car_hi.msh"], part_map=files["part.map"])
    for lod, coverage in report["part_map"]["lods"].items():
        if not coverage["assigned_slots"] == coverage["distinct_parts"] == report["lod_part_counts"][lod]:
            raise ValueError(f"The converted part map does not assign every LOD {lod} part exactly once")
    texture_base, = struct.unpack_from("<I", files["car.mdl"], 0x2c)
    if relocation_table(files["car.tex"])[1] != texture_base:
        raise ValueError("The class texture base does not match the model's texture reference")
    verify_wheel_lods(files["car.mdl"], files["part.map"])
    report["tire_radii_m"] = [float(value) for value in tire_radii(files["car.mdl"], files["part.map"])]
    report["body_pages"] = {}
    for name in ("car.tex", "car_hi.tex"):
        report["body_pages"][name] = {
            page.decode("ascii"): bitmap.size for page, (bitmap, _) in sorted(body_uploads(files[name]).items())
        }
    # These are the current portable DTM overlay's loader limits, in bytes.
    limits = {"car.mdl": 72716, "car.msh": 376572, "car_hi.msh": 369788, "car_hi.tex": 381204}
    report["dtm_preview_oversize"] = {
        name: {"bytes": len(files[name]), "limit": limit}
        for name, limit in limits.items() if len(files[name]) > limit
    }
    report["asset_sha256"] = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="list the supported playable presets")
    catalog = commands.add_parser("catalog", help="list variants in a donor class")
    convert = commands.add_parser("convert", help="build a development model pair (not a playable pack)")
    build = commands.add_parser("build", help="build an add-on for a supported playable preset")
    audit = commands.add_parser("audit", help="check converted model, wheels, textures, and overlay limits")
    audit.add_argument("bundle", type=Path, help="directory produced by convert or build")
    audit.add_argument("--dtm-pack", action="store_true", help="audit the installed DTM variant archive and separate high-detail assets")
    for command in (catalog, convert, build):
        command.add_argument("--rd2-disc", type=Path, required=True, help="mounted or extracted RD2 disc directory")
    for command in (catalog, convert):
        source = command.add_mutually_exclusive_group()
        source.add_argument("--class", dest="donor_class", choices=("auto", *RD2_CLASSES), default="auto",
                            help="discover variants on the disc (default) or use a named class")
        source.add_argument("--class-range", type=int, nargs=3, metavar=("HUG", "SECTOR", "BYTES"))
    for command in (convert, build):
        command.add_argument("--disc", type=Path, required=True, help="mounted or extracted RD3 disc directory")
        command.add_argument("--output", type=Path, required=True, help="new output directory")
    convert.add_argument("variant", type=str.lower)
    build.add_argument("car", type=str.lower, choices=PLAYABLE)
    sound = build.add_mutually_exclusive_group()
    sound.add_argument("--stock-sound", action="store_true", help="retain the RD3 template engine audio")
    sound.add_argument("--donor-effects", action="store_true", help="also import the experimental RD2 DB5 player effects")
    build.add_argument("--stock-cockpit", action="store_true", help="retain the RD3 template cockpit")
    args = parser.parse_args()
    try:
        if args.command == "list":
            for key, (name, _) in PLAYABLE.items():
                print(f"{key:<12} {name}")
            return
        if args.command == "audit":
            print(json.dumps(audit_bundle(args.bundle, dtm_pack=args.dtm_pack), indent=2))
            return
        if args.command != "build":
            discover = not args.class_range and args.donor_class == "auto"
            if discover and args.command == "catalog":
                for variant, model, package, _ in sorted(discover_variants(args.rd2_disc),
                                                          key=lambda row: (row[0], row[2].hug, row[2].sector)):
                    print(f"{variant:<12} {model:<16} HUG {package.hug}, sector {package.sector}")
                return
            archive = (discover_car(args.rd2_disc, args.variant) if discover else
                       donor_class(args.rd2_disc, args.class_range or RD2_CLASSES[args.donor_class]))
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
                             donor_cockpit=not args.stock_cockpit, donor_effects=args.donor_effects)
        with TemporaryDirectory(dir=args.output.parent) as stage:
            folder = Path(stage) / "car"
            folder.mkdir()
            for name, data in result.items():
                (folder / name).write_bytes(data)
            folder.rename(args.output.resolve())
    except (OSError, UnicodeError, IniError, KeyError, ValueError, struct.error) as error:
        parser.exit(1, f"RD2 car import failed: {error}\n")
    print(args.output)


if __name__ == "__main__":
    main()
