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

from BuildDtmVariant import append_variant, read_disc_range
from BuildRd2Db5Variant import build as build_db5, member, tire_radii, verify_wheel_lods
from BuildRoadAmericaMod import EVENT_CATALOG_BYTES, EVENT_CATALOG_SECTOR, repack_jpak
from BuildTrackCollisionOverlay import DONOR_DIRECTORY_HASH, REFERENCE_DIRECTORY_HASH, SECTOR_SIZE, read_exact, verify_directory
from ConvertRd2CarGlass import convert_windshield
from ConvertRd2CarModel import convert_model, convert_textures
from ConvertRd2LancerCockpit import DTM_STEERING_X, convert_wheel
from ModAssets import REFERENCE_PACKAGES, replace_member
from Ps2CarModel import inspect_model, relocation_table
from Ps2CarTexture import body_uploads
from Rd2AssetCatalog import car_packages, read_index, scan_disc


RD2_CLASSES = {"vintage": (1, 787442, 7009268)}
PLAYABLE = {"db5": ("Aston Martin DB5", build_db5)}
WINDSHIELD_STRIPS = {
    "evo7": (6, 5, 3, 4, 4),
    "fal_ba": (7, 5, 1, 1, 4),
    "mustang68": (1, 1, 1, 1, 4),
}
DTM_MESH_LIMIT = 512 * 1024


def donor_class(disc, extent, *, reference_layout=True):
    if reference_layout:
        verify_directory(disc / "RD2.DIR", DONOR_DIRECTORY_HASH)
    hug, sector, size = extent
    if hug < 0 or sector < 0 or not 0 < size <= 32 * 1024 * 1024:
        raise ValueError("Invalid class range (non-negative HUG and sector, at most 32 MiB)")
    with (disc / f"RD2_{hug}.HUG").open("rb") as stream:
        start = sector * SECTOR_SIZE
        end = start + size
        if stream.seek(0, 2) < end:
            raise ValueError("Class range extends beyond the RD2 archive")
        package = read_index(stream, start, end, hug)
        if package is None or not tuple(car_packages((package,))):
            raise ValueError("Class range does not contain an indexed RD2 vehicle package")
        return read_exact(stream, start, size)


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
        bad_tint = dict(enumerate((3, 2, 2, 4, 4))) if car == "evo7" else None
        high = convert_windshield(model, high, part_map, {0: strips[0]}, bad_tint_strips_by_lod=bad_tint)
        low = convert_windshield(model, low, part_map, dict(enumerate(strips[1:], start=1)),
                                 bad_tint_strips_by_lod=bad_tint)
    texture = convert_textures(member(archive, f"{variant}.tex"), member(template, "dtmx_13.tex"))
    high_texture = convert_textures(member(archive, f"{variant}_hi.tex"), read_disc_range(disc, 2, 185648, 381204))
    return {"car.mdl": model, "car_hi.msh": high, "car.msh": low, "part.map": part_map,
            "car.tex": texture, "car_hi.tex": high_texture}


def discover_mechanics(disc, variant):
    number_section = re.compile(rb"(?mi)^\[" + re.escape(variant.encode("ascii")) + rb"(?:_[0-9]+)?\][ \t]*\r?$")
    required = {"dmg.ini", "int.ini", "num.ini"}
    matching = set()
    for package in scan_disc(disc):
        if required.issubset(package.names) and number_section.search(package.member(disc, "num.ini")):
            matching.add((package.member(disc, "dmg.ini"), package.member(disc, "int.ini")))
    if len(matching) != 1:
        raise ValueError(f"Expected one interior and damage configuration for {variant!r}, found {len(matching)}")
    return matching.pop()


def discover_cockpit(disc, model):
    model_name, texture_name = f"{model}.p3d", f"{model}.big"
    matches = {(package.member(disc, model_name), package.member(disc, texture_name))
               for package in scan_disc(disc) if {model_name, texture_name}.issubset(package.names)}
    if len(matches) != 1:
        raise ValueError(f"Expected one model and texture archive for {model!r}, found {len(matches)}")
    return matches.pop()


def build_test_pack(rd2, rd3, variant, *, donor_wheel=False):
    cars = convert_car(discover_car(rd2, variant), variant, rd3)
    if max(len(cars["car.msh"]), len(cars["car_hi.msh"])) > DTM_MESH_LIMIT:
        raise ValueError(f"The converted meshes exceed the {DTM_MESH_LIMIT}-byte test pack limit")
    damage, interior = discover_mechanics(rd2, variant)
    stock = read_disc_range(rd3, *REFERENCE_PACKAGES["dtm-cars"])
    extra_members = ()
    if donor_wheel:
        if b"\r\nModelName=int_left\r\n" not in interior:
            raise ValueError("Expected the Lancer's int_left donor cockpit")
        donor_model, donor_archive = discover_cockpit(rd2, "int_left")
        stock_archive = member(stock, "int_dtm.big")
        px, big = convert_wheel(donor_model, member(donor_archive, "gen02.tm2"), member(donor_archive, "disp_num.tm2"),
                                member(stock, "int_dtm.px"), stock_archive, member(stock_archive, "int_01.tm2"))
        extra_members = ((b"int_evo.px", b"int_dtm.px", px), (b"int_evo.big", b"int_dtm.big", big))
    archive = append_variant(stock, cars["car.msh"], extra_members=extra_members)
    car = member(archive, "dtmx_20.big")
    exterior = re.compile(rb"(?ms)^\[Exterior\]\r\n.*?(?=^\[)")
    donor_binding = exterior.search(interior)
    if donor_binding is None or b"Part0=2\r\nNumParts=1\r\n" not in donor_binding[0]:
        raise ValueError("Expected the Lancer exterior binding for the cockpit camera")
    cockpit, count = exterior.subn(lambda _: donor_binding[0], member(car, "int.ini"))
    if count != 1:
        raise ValueError("Expected one exterior section in the test cockpit")
    if donor_wheel:
        camera = f"[Camera]\r\nAngle=0.05\r\nZoom=0.85\r\nZ=0.16\r\nY=0.915\r\nX={DTM_STEERING_X:.4f}\r\n".encode("ascii")
        cockpit, count = re.subn(rb"(?ms)^\[Camera\]\r\n.*?(?=^\[Shift\])", lambda _: camera, cockpit)
        if count != 1 or cockpit.count(b"ModelName=int_dtm\r\n") != 1:
            raise ValueError("Expected the DTM template's model and camera settings")
        cockpit = cockpit.replace(b"ModelName=int_dtm\r\n", b"ModelName=int_evo\r\n")
    for name, data in (("part.map", cars["part.map"]), ("dmg.ini", damage), ("int.ini", cockpit)):
        car = replace_member(car, [name], data)
    archive = repack_jpak(archive, struct.unpack_from("<I", archive, 8)[0], {
        b"dtmx_20.big": car,
        b"dtmx_20.tex": cars["car.tex"],
        b"QA_Touring.mdl": cars["car.mdl"],
    }, compressor=lambda data: data)
    events = read_disc_range(rd3, 1, EVENT_CATALOG_SECTOR, EVENT_CATALOG_BYTES)
    intro = member(events, "1st__.ini")
    assignment = b"CareerOfferCarID = dtmx_13/CKL"
    if intro.count(assignment) != 1:
        raise ValueError("Expected one introductory DTM car assignment")
    events = replace_member(events, ["1st__.ini"], intro.replace(assignment, b"CareerOfferCarID = dtmx_20/CKL"))
    pack = {"DTMX_EXT.JPK": archive, "QA_TOURING_HI.MSH": cars["car_hi.msh"],
            "DTMX_20_HI.TEX": cars["car_hi.tex"], "events.big": events}
    if donor_wheel:
        pack["evo-speed.ini"] = b"EVO7SPEED 1\r\n"
    return pack


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
    limits = {"car.mdl": 72716, "car.msh": DTM_MESH_LIMIT, "car_hi.msh": DTM_MESH_LIMIT, "car_hi.tex": 381204}
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
    test_pack = commands.add_parser("build-test-pack", help="build a Lancer Evolution VII DTM test pack")
    build = commands.add_parser("build", help="build an add-on for a supported playable preset")
    audit = commands.add_parser("audit", help="check converted model, wheels, textures, and overlay limits")
    audit.add_argument("bundle", type=Path, help="directory produced by convert or build")
    audit.add_argument("--dtm-pack", action="store_true", help="audit the installed DTM variant archive and separate high-detail assets")
    for command in (catalog, convert, build, test_pack):
        command.add_argument("--rd2-disc", type=Path, required=True, help="mounted or extracted RD2 disc directory")
    for command in (catalog, convert):
        source = command.add_mutually_exclusive_group()
        source.add_argument("--class", dest="donor_class", choices=("auto", *RD2_CLASSES), default="auto",
                            help="discover variants on the disc (default) or use a named class")
        source.add_argument("--class-range", type=int, nargs=3, metavar=("HUG", "SECTOR", "BYTES"))
    for command in (convert, build, test_pack):
        command.add_argument("--disc", type=Path, required=True, help="mounted or extracted RD3 disc directory")
        command.add_argument("--output", type=Path, required=True, help="new output directory")
    convert.add_argument("variant", type=str.lower)
    test_pack.add_argument("variant", type=str.lower, choices=("bs_0",))
    test_pack.add_argument("--donor-wheel", action="store_true", help="install the experimental RD2 steering wheel and speed display")
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
        if args.command in ("convert", "catalog"):
            discover = not args.class_range and args.donor_class == "auto"
            if discover and args.command == "catalog":
                for variant, model, package, _ in sorted(discover_variants(args.rd2_disc),
                                                          key=lambda row: (row[0], row[2].hug, row[2].sector)):
                    print(f"{variant:<12} {model:<16} HUG {package.hug}, sector {package.sector}")
                return
            archive = (discover_car(args.rd2_disc, args.variant) if discover else
                       donor_class(args.rd2_disc, args.class_range or RD2_CLASSES[args.donor_class],
                                   reference_layout=args.class_range is None))
            if args.command == "catalog":
                for variant, model in variants(archive).items():
                    print(f"{variant:<12} {model}")
                return
        if args.output.exists():
            raise ValueError("Choose a new output directory")
        if args.command == "convert":
            result = convert_car(archive, args.variant, args.disc)
        elif args.command == "build-test-pack":
            result = build_test_pack(args.rd2_disc, args.disc, args.variant, donor_wheel=args.donor_wheel)
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
