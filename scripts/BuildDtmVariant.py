#!/usr/bin/env python3
"""Build the additional DTM test variant from a local PS2 disc and edited meshes."""

import argparse
from pathlib import Path
import struct

from BuildRoadAmericaMod import EVENT_CATALOG_BYTES, EVENT_CATALOG_SECTOR, jpak_entries
from BuildTrackCollisionOverlay import (
    REFERENCE_DIRECTORY_HASH, SECTOR_SIZE, encode_lzss_compact, read_exact, verify_directory,
)
from ModAssets import REFERENCE_PACKAGES, find_member, replace_member
from Ps2CarModel import mesh_packets, relocation_table
from Ps2CarTexture import copy_body_pages


def read_disc_range(disc, hug, sector, length):
    with (disc / f"RDH_{hug}.HUG").open("rb") as stream:
        return read_exact(stream, sector * SECTOR_SIZE, length)


def check_mesh_layout(candidate, template, label):
    if (len(candidate) != len(template) or relocation_table(candidate) != relocation_table(template)
            or mesh_packets(candidate) != mesh_packets(template)):
        raise ValueError(f"The {label} mesh must retain the Mercedes template's packet and relocation layout")


def append_variant(archive, mesh, livery=None, extra_members=()):
    count = struct.unpack_from("<I", archive, 8)[0]
    entries = {}
    for _, _, name, row in jpak_entries(archive, count):
        _, length, offset, expanded, *metadata = row
        entries[name] = (archive[offset:offset + length], expanded, metadata)
    for name in (b"dtmx_20.big", b"dtmx_20.tex", b"QA_Touring.mdl", b"QA_Touring.msh"):
        if any(key.lower() == name.lower() for key in entries):
            raise ValueError(f"The class package already contains {name.decode('ascii')}")
    variant_data = find_member(archive, "dtmx_13.big")[0].read(archive)
    entries[b"dtmx_20.big"] = (variant_data, len(variant_data), entries[b"dtmx_13.big"][2])
    entries[b"dtmx_20.tex"] = entries[b"dtmx_13.tex"]
    if livery is not None:
        original_texture = find_member(archive, "dtmx_13.tex")[0].read(archive)
        texture = copy_body_pages(livery, original_texture)
        entries[b"dtmx_20.tex"] = (texture, len(texture), entries[b"dtmx_13.tex"][2])
    model = find_member(archive, "DTM_C_Klasse.mdl")[0].read(archive)
    entries[b"QA_Touring.mdl"] = (model, len(model), entries[b"DTM_C_Klasse.mdl"][2])
    entries[b"QA_Touring.msh"] = (mesh, len(mesh), entries[b"DTM_C_Klasse.msh"][2])
    lookup = find_member(archive, "lookup.ini")[0].read(archive)
    if any(line.lower().lstrip().startswith(b"dtmx_20=") for line in lookup.splitlines()):
        raise ValueError("The class lookup already contains dtmx_20")
    lookup = lookup.rstrip() + b"\r\ndtmx_20=QA_Touring\r\n"
    _, _, lookup_metadata = entries.pop(b"lookup.ini")
    entries[b"lookup.ini"] = (lookup, len(lookup), lookup_metadata)
    for name, template, data in extra_members:
        if any(key.lower() == name.lower() for key in entries):
            raise ValueError(f"The class package already contains {name.decode('ascii')}")
        stored = encode_lzss_compact(data)
        entries[name] = (stored if len(stored) < len(data) else data, len(data), entries[template][2])

    table_end = 32 + len(entries) * 32
    output = bytearray(archive[:32])
    struct.pack_into("<I", output, 8, len(entries))
    struct.pack_into("<I", output, 20, table_end)
    output.extend(bytes(table_end - len(output)))
    for index, (name, (stored, expanded, metadata)) in enumerate(entries.items()):
        struct.pack_into("<8I", output, 32 + index * 32, len(output), len(stored), 0, expanded, *metadata)
        output.extend(name + b"\0")
    for index, (stored, _, _) in enumerate(entries.values()):
        output.extend(bytes(-len(output) % 64))
        struct.pack_into("<I", output, 32 + index * 32 + 8, len(output))
        output.extend(stored)
    return output


def build(args):
    verify_directory(args.disc / "RDH.DIR", REFERENCE_DIRECTORY_HASH)
    archive = read_disc_range(args.disc, *REFERENCE_PACKAGES["dtm-cars"])
    original_high = read_disc_range(args.disc, *REFERENCE_PACKAGES["dtm-mercedes-hi"])
    mesh = args.mesh.read_bytes()
    high = args.hi_mesh.read_bytes()
    check_mesh_layout(mesh, find_member(archive, "DTM_C_Klasse.msh")[0].read(archive), "class")
    check_mesh_layout(high, original_high, "high-detail")
    variant = append_variant(archive, mesh, args.livery_class.read_bytes() if args.livery_class else None)
    events = read_disc_range(args.disc, 1, EVENT_CATALOG_SECTOR, EVENT_CATALOG_BYTES)
    intro = find_member(events, "1st__.ini")[0].read(events)
    current = b"CareerOfferCarID = dtmx_13/CKL"
    if intro.count(current) != 1:
        raise ValueError("The reference introductory race's DTM car assignment was not found")
    intro = intro.replace(current, b"CareerOfferCarID = dtmx_20/CKL")
    modified_events = replace_member(events, ["1st__.ini"], intro)
    texture = read_disc_range(args.disc, 2, 185648, 381204)
    if args.livery_hi:
        texture = copy_body_pages(args.livery_hi.read_bytes(), texture)
    args.output.mkdir()
    for name, data in {
        "DTMX_EXT.JPK": variant,
        "QA_TOURING_HI.MSH": high,
        "DTMX_20_HI.TEX": texture,
        "events.big": modified_events,
    }.items():
        with (args.output / name).open("xb") as stream:
            stream.write(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disc", required=True, type=Path, help="reference mounted or extracted PS2 DVD directory")
    parser.add_argument("--mesh", required=True, type=Path, help="edited Mercedes class mesh")
    parser.add_argument("--hi-mesh", required=True, type=Path, help="edited Mercedes high-detail mesh")
    parser.add_argument("--livery-class", type=Path, help="donor class .tex with compatible body textures")
    parser.add_argument("--livery-hi", type=Path, help="donor high-detail .tex with compatible body textures")
    parser.add_argument("--output", required=True, type=Path, help="new add-on directory")
    args = parser.parse_args()
    if bool(args.livery_class) != bool(args.livery_hi):
        parser.error("Supply --livery-class and --livery-hi together")
    try:
        build(args)
    except (OSError, KeyError, ValueError, struct.error) as error:
        parser.exit(1, f"DTM variant build failed: {error}\n")
    print(args.output)


if __name__ == "__main__":
    main()
