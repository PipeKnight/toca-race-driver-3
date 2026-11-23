#!/usr/bin/env python3
"""Inspect, extract, and edit assets from the reference Race Driver 3 PS2 disc."""

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import struct

from BuildRoadAmericaMod import (
    EVENT_CATALOG_BYTES, EVENT_CATALOG_SECTOR, TRACK_CATALOG_BYTES, TRACK_CATALOG_SECTOR,
    jpak_entries, repack_jpak, unpack_lzss,
)
from BuildTrackCollisionOverlay import (
    BIGF_ENTRY, REFERENCE_DIRECTORY_HASH, SECTOR_SIZE, TRACK_BYTES, TRACK_SECTOR,
    collision_counts, encode_lzss, encode_lzss_compact, read_exact, verify_directory,
)
from BuildTrackGeometryOverlay import DMA_BYTES, DMA_SECTOR
from Ps2TrackCollision import collision_append, collision_export
from Ps2TrackScene import scene_append, scene_info


REFERENCE_PACKAGES = {
    "tracks": (1, TRACK_CATALOG_SECTOR, TRACK_CATALOG_BYTES),
    "events": (1, EVENT_CATALOG_SECTOR, EVENT_CATALOG_BYTES),
    "oschersleben-track": (1, TRACK_SECTOR, TRACK_BYTES),
    "oschersleben-scene": (1, DMA_SECTOR, DMA_BYTES),
    "oschersleben-metadata": (1, 522960, 328064),
    "dtm-cars": (2, 187552, 5145344),
    "dtm-mercedes-hi": (2, 190800, 369788),
}


@dataclass(frozen=True)
class Member:
    name: str
    offset: int
    stored: int
    expanded: int
    size_field: int
    jpak: bool = False

    @property
    def compressed(self):
        return self.stored != self.expanded

    def read(self, archive):
        payload = archive[self.offset:self.offset + self.stored]
        if self.compressed:
            # One two-byte LZSS reference expands to at most 18 bytes.
            if self.expanded > self.stored * 9:
                raise ValueError(f"Invalid expanded length for {self.name}")
            return bytes(unpack_lzss(payload, self.expanded))
        return payload


def members(archive):
    magic = archive[:4]
    if magic == b"JPAK":
        count = struct.unpack_from("<I", archive, 8)[0]
        for first_data, row_offset, name, row in jpak_entries(archive, count):
            _, stored, offset, expanded, _, _, flags, _ = row
            if offset < first_data or stored != expanded and not flags & 1:
                raise ValueError("Unrecognized JPAK member layout")
            yield Member(name.decode("ascii"), offset, stored, expanded, row_offset + 4, True)
    elif magic == b"BIGF":
        count, base = struct.unpack_from("<2I", archive, 4)
        end = 0x24 + count * BIGF_ENTRY.size
        if not end <= base <= len(archive):
            raise ValueError("Invalid indexed BIGF directory")
        for index, (name, size, relative) in enumerate(BIGF_ENTRY.iter_unpack(archive[0x24:end])):
            offset = base + relative
            if offset + size > len(archive):
                raise ValueError("BIGF member extends past the package")
            yield Member(name.split(b"\0", 1)[0].decode("ascii"), offset, size, size, 0x34 + index * 24)
    else:
        raise ValueError("Expected an indexed PS2 BIGF or JPAK package")


def find_member(archive, name):
    directory = list(members(archive))
    matches = [member for member in directory if member.name.casefold() == name.casefold()]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one member named {name!r}; found {len(matches)}")
    return matches[0], directory


def replace_member(archive, chain, replacement):
    member, directory = find_member(archive, chain[0])
    original = member.read(archive)
    if len(chain) > 1:
        replacement = replace_member(original, chain[1:], replacement)
    if replacement == original:
        return archive
    end = member.offset + member.stored
    if any(other is not member and other.stored and other.offset < end
           and other.offset + other.stored > member.offset for other in directory):
        raise ValueError(f"{member.name} shares its stored range with another member")
    payload = encode_lzss(replacement) if member.compressed else replacement
    if member.compressed and len(payload) > member.stored and len(replacement) > member.stored:
        payload = encode_lzss_compact(replacement)
    # Equal stored and expanded lengths signal a raw member even when the flag is set.
    if len(payload) >= len(replacement):
        payload = replacement
    if len(payload) > member.stored:
        if member.jpak:
            return bytes(repack_jpak(archive, len(directory), {member.name.encode("ascii"): replacement},
                                     len(archive), compressor=lambda _: payload))
        raise ValueError(f"{member.name} needs {len(payload)} stored bytes but has room for {member.stored}")
    output = bytearray(archive)
    output[member.offset:end] = payload + bytes(member.stored - len(payload))
    if member.jpak:
        struct.pack_into("<III", output, member.size_field, len(payload), member.offset, len(replacement))
    else:
        struct.pack_into("<I", output, member.size_field, len(payload))
    return bytes(output)


def read_package(args):
    if args.file:
        if args.package or args.archive_range:
            raise ValueError("Choose --package or --range only with --disc")
        return args.file.read_bytes()
    if args.package is None and args.archive_range is None:
        raise ValueError("Choose a reference package with --package or an archive range with --range")
    verify_directory(args.disc / "RDH.DIR", REFERENCE_DIRECTORY_HASH)
    part, sector, size = args.archive_range if args.archive_range else REFERENCE_PACKAGES[args.package]
    offset = sector * SECTOR_SIZE
    if part not in (0, 1, 2) or offset < 0 or size <= 0:
        raise ValueError("Expected archive 0–2, a nonnegative sector, and a positive byte count")
    archive = args.disc / f"RDH_{part}.HUG"
    with archive.open("rb") as stream:
        if offset + size > stream.seek(0, 2):
            raise ValueError("The selected range extends past the HUG archive")
        return read_exact(stream, offset, size)


def archive_command(args):
    archive = read_package(args)
    if args.command == "extract-resource":
        write_extracted(args.output, archive)
        return
    if args.command == "replace":
        result = replace_member(archive, args.inside + [args.member], args.replacement.read_bytes())
        with args.output.open("xb") as stream:
            stream.write(result)
        return
    for name in args.inside:
        archive = find_member(archive, name)[0].read(archive)
    if args.command == "extract":
        result = find_member(archive, args.member)[0].read(archive)
        write_extracted(args.output, result)
    else:
        print(f"{'Name':32} {'Offset':>10} {'Stored':>9} {'Decoded':>9}  Encoding")
        for member in members(archive):
            encoding = "LZSS" if member.compressed else "raw"
            print(f"{member.name:32} {member.offset:#10x} {member.stored:9d} {member.expanded:9d}  {encoding}")


def write_extracted(output, data):
    with output.open("xb") as stream:
        stream.write(data)
    print(f"{len(data)} bytes  sha256 {hashlib.sha256(data).hexdigest()}")


def part_map(args):
    if args.command == "part-map-export":
        data = args.input.read_bytes()
        version, lod_count, width = struct.unpack_from("<3I", data)
        if version != 1 or not lod_count or not width or len(data) != 12 + lod_count * width * 4:
            raise ValueError("Invalid version 1 part map")
        lods = [struct.unpack_from(f"<{width}I", data, 12 + index * width * 4) for index in range(lod_count)]
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(dict(version=version, entries_per_lod=width, lods=lods), stream, indent=2)
            stream.write("\n")
    else:
        data = json.loads(args.input.read_text(encoding="utf-8"))
        version, width, lods = data["version"], data["entries_per_lod"], data["lods"]
        if type(version) is not int or version != 1 or type(width) is not int or not 0 < width <= 0xffffffff:
            raise ValueError("Expected a version 1 part map with a positive entries_per_lod")
        if not isinstance(lods, list) or not lods:
            raise ValueError("Expected a non-empty list of LODs")
        result = bytearray(struct.pack("<3I", version, len(lods), width))
        for index, row in enumerate(lods):
            if not isinstance(row, list) or len(row) != width:
                raise ValueError(f"LOD {index} must contain {width} entries")
            if any(type(value) is not int or not 0 <= value <= 0xffffffff for value in row):
                raise ValueError(f"LOD {index} must hold {width} unsigned 32-bit integers")
            result.extend(struct.pack(f"<{width}I", *row))
        with args.output.open("xb") as stream:
            stream.write(result)


def collision_info(args):
    data = args.input.read_bytes()
    vertices, triangles = collision_counts(data)
    bounds = struct.unpack_from("<6f", data)
    cell_bytes = struct.unpack_from("<I", data, 24)[0]
    trailer = len(data) - 40 - 8 * vertices - 10 * triangles - cell_bytes
    start = 40 + 8 * vertices
    surface_types = data[start + 2:start + 4 * triangles:4]
    profile = {surface: dict(triangles=count, first_triangle=surface_types.index(surface))
               for surface, count in sorted(Counter(surface_types).items())}
    print(json.dumps(dict(bounds_min=bounds[:3], bounds_max=bounds[3:], vertices=vertices,
                          triangles=triangles, cell_bytes=cell_bytes, trailer_bytes=trailer,
                          surface_types=profile), indent=2))


def collision_surface(args):
    data = bytearray(args.input.read_bytes())
    vertices, triangles = collision_counts(data)
    if not 0 <= args.triangle < triangles or not 0 <= args.from_triangle < triangles:
        raise ValueError(f"Choose triangle indices from 0 to {triangles - 1}")
    start = 40 + 8 * vertices + 2
    data[start + 4 * args.triangle] = data[start + 4 * args.from_triangle]
    with args.output.open("xb") as stream:
        stream.write(data)


def route_obj(args):
    data = args.input.read_bytes()
    if data[:8] != b"AILD\x09\0\0\0":
        raise ValueError("Expected an AILD version 9 route")
    groups = tuple(struct.iter_unpack("<HBB", data[8:20]))
    if len(groups) != 3 or any(not count or not mask or loop not in (0, 1) for count, mask, loop in groups):
        raise ValueError("Invalid AILD section headers")
    offset = 20 + 16 * sum(count for count, _, _ in groups)
    if len(data) != offset + 8 * sum(count * mask.bit_count() for count, mask, _ in groups):
        raise ValueError("AILD length does not match its route section sizes")
    obj = ["# Race Driver 3 route. Coordinates are X/Z, with Y set to zero.\n"]
    first = 1
    for label, (count, mask, loop) in zip(("main", "pit", "auxiliary"), groups):
        for lane in range(mask.bit_count()):
            end = offset + count * 8
            obj.append(f"g {label}_{lane}\n")
            for x, z in struct.iter_unpack("<2f", data[offset:end]):
                if not math.isfinite(x) or not math.isfinite(z):
                    raise ValueError("AILD contains a non-finite route coordinate")
                obj.append(f"v {x:.9g} 0 {z:.9g}\n")
            indices = list(range(first, first + count))
            if loop:
                indices.append(first)
            if len(indices) > 1:
                obj.append("l " + " ".join(map(str, indices)) + "\n")
            first += count
            offset = end
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.writelines(obj)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (("list", "list archive members"), ("extract", "extract a decoded member"),
                            ("extract-resource", "extract a complete disc resource by range or name"),
                            ("replace", "replace one member within the original package extent")):
        command = commands.add_parser(name, help=help_text)
        source = command.add_mutually_exclusive_group(required=True)
        if name == "extract-resource":
            command.set_defaults(file=None)
        else:
            source.add_argument("--file", type=Path, help="local BIGF or JPAK package")
        source.add_argument("--disc", type=Path, help="mounted or extracted SLUS-21182 v1.02 DVD directory")
        location = command.add_mutually_exclusive_group()
        location.add_argument("--package", choices=REFERENCE_PACKAGES, help="known package on the reference disc")
        location.add_argument("--range", dest="archive_range", nargs=3, type=int, metavar=("HUG", "SECTOR", "BYTES"),
                              help="use a traced HUG archive index, archive-relative sector and byte count")
        if name != "extract-resource":
            command.add_argument("--inside", action="append", default=[], help="descend into a nested member, repeat as needed")
        if name in ("extract", "replace"):
            command.add_argument("member")
            if name == "replace":
                command.add_argument("replacement", type=Path)
        if name != "list":
            command.add_argument("output", type=Path, help="new output file")
        command.set_defaults(run=archive_command)
    for name, help_text, handler in (
        ("part-map-export", "write a version 1 part map as editable JSON", part_map),
        ("part-map-import", "serialize part map JSON to a new binary file", part_map),
        ("collision-info", "validate collision bounds and triangle indices", collision_info),
        ("collision-surface", "copy a triangle's surface type within a collision mesh", collision_surface),
        ("collision-export", "export a PS2 collision mesh as a triangle OBJ in game coordinates", collision_export),
        ("collision-append", "add triangles from an OBJ to an existing PS2 collision mesh", collision_append),
        ("scene-info", "list track scene roots with usable material leaves", scene_info),
        ("scene-append", "add OBJ triangles to a PS2 track scene using a local material", scene_append),
        ("route-obj", "export AILD version 9 routes as flat OBJ polylines", route_obj),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("input", type=Path)
        if name not in ("collision-info", "scene-info"):
            command.add_argument("output", type=Path, help="new output file")
        if name == "collision-surface":
            command.add_argument("--triangle", type=int, required=True, help="zero-based destination triangle index")
            command.add_argument("--from-triangle", type=int, required=True, help="zero-based source triangle index")
        if name == "collision-append":
            command.add_argument("--obj", type=Path, required=True, help="triangulated OBJ in game coordinates")
            command.add_argument("--surface-from", type=int, required=True,
                                 help="copy the surface type of this zero-based template triangle")
        if name == "scene-info":
            command.add_argument("--near", type=float, nargs=2, default=(0, 0), metavar=("X", "Z"),
                                 help="choose a nearby material leaf per scene root")
        if name == "scene-append":
            command.add_argument("--obj", type=Path, required=True, help="triangulated OBJ in game coordinates")
            command.add_argument("--root", type=lambda value: int(value, 0), required=True, help="root offset from scene-info")
            command.add_argument("--leaf", type=lambda value: int(value, 0), required=True,
                                 help="material leaf offset from scene-info")
            command.add_argument("--rgb", type=int, nargs=3, metavar=("R", "G", "B"), help="override the material's vertex color")
            command.add_argument("--offset-y", type=float, default=0, help="shift authored vertices vertically in metres")
        command.set_defaults(run=handler)
    args = parser.parse_args()
    try:
        args.run(args)
    except (OSError, ValueError, IndexError, KeyError, TypeError, struct.error) as error:
        parser.exit(1, f"Asset operation failed: {error}\n")


if __name__ == "__main__":
    main()
