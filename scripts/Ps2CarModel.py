#!/usr/bin/env python3
"""Inspect PS2 Race Driver car model pairs and edit their mesh vertex streams."""

import argparse
from bisect import bisect_left
from collections import Counter
import csv
from dataclasses import dataclass
import json
import math
from pathlib import Path
import struct

from BuildTrackGeometryOverlay import FOOTER, RELOCATION, VERTEX, read_word, vif_commands
from ModAssets import read_part_map


STREAM_HEADER = 0x6c028000
CSV_FIELDS = ["packet", "vertex", "x", "y", "z"]
UV = struct.Struct("<2f")
GIF_TAG = struct.Struct("<QQ")


@dataclass(frozen=True)
class MeshPacket:
    position: int
    normal: int
    uv: int
    count: int
    triangle_strip: bool


def relocation_table(data):
    footer = len(data) - FOOTER.size
    count, payload, base = FOOTER.unpack_from(data, footer)
    if not payload or payload % 16 or payload + count * RELOCATION.size != footer:
        raise ValueError("Invalid PS2 relocation footer")
    rows = dict(RELOCATION.iter_unpack(data[payload:footer]))
    if len(rows) != count or any(offset % 4 or offset >= payload for offset in rows):
        raise ValueError("Invalid PS2 relocation offsets")
    return payload, base, rows


def mesh_packets(data):
    payload, base, rows = relocation_table(data)
    if not rows or any(kind != 4 or read_word(data, offset) >> 24 & 0x7f != 0x14
                       for offset, kind in rows.items()):
        raise ValueError("Expected the MSCAL relocation table of a PS2 car mesh")

    starts = [offset for offset in range(0, payload - 35, 4) if read_word(data, offset) == STREAM_HEADER]
    if not starts:
        raise ValueError("No car position stream headers found")
    found_calls = set()
    streams = []
    for start, end in zip(starts, starts[1:] + [payload]):
        _, _, uv, count, normal, _, _, _ = struct.unpack_from("<8I", data, start + 4)
        positions = []
        normals = []
        texcoords = []
        triangle_strip = False
        for command in vif_commands(data, start, end):
            if command.operation in (0x14, 0x17):
                if command.operation == 0x14:
                    found_calls.add(command.payload - 4)
                break
            if command.operation in (0x6c, 0x7c) and command.payload != start + 4:
                tags = data[command.payload:command.payload + command.size]
                # The car's packed GIF template supplies ST, RGBAQ, and XYZ2 for each strip vertex.
                triangle_strip |= any(tag & 0x7fff == count and tag >> 46 & 1 and tag >> 47 & 7 == 4
                                      and tag >> 58 & 3 == 0 and tag >> 60 & 15 == 3 and regs == 0x512
                                      for tag, regs in GIF_TAG.iter_unpack(tags))
            if command.count != count:
                continue
            address = command.immediate & 0x3ff
            if command.operation in (0x68, 0x78) and command.size == count * VERTEX.size:
                if address == uv + 2:
                    positions.append(command.payload)
                if address == normal:
                    normals.append(command.payload)
            if command.operation in (0x64, 0x74) and address == uv and command.size == count * 8:
                texcoords.append(command.payload)
        else:
            raise ValueError(f"Missing VU execution command after mesh header at {start:#x}")
        if not count or len(positions) != 1 or len(normals) != 1 or len(texcoords) != 1:
            raise ValueError(f"Unrecognized position, normal, or UV layout at {start:#x}")
        offset = positions[0]
        points = data[offset:offset + count * VERTEX.size]
        if not all(math.isfinite(value) for point in VERTEX.iter_unpack(points) for value in point):
            raise ValueError(f"Non-finite position in mesh packet at {start:#x}")
        streams.append(MeshPacket(offset, normals[0], texcoords[0], count, triangle_strip))
    if found_calls != rows.keys():
        raise ValueError("Mesh packet calls do not match the relocation table")
    return base, streams


def model_sections(data):
    payload, base, rows = relocation_table(data)
    if payload < 0x38 or set(rows.values()) != {0, 3, 4}:
        raise ValueError("Expected a PS2 DTM model relocation table")
    starts = [address - base for address in struct.unpack_from("<5I", data)]
    if starts != sorted(set(starts)) or any(not 0x38 <= offset < payload for offset in starts):
        raise ValueError("Invalid DTM model section offsets")
    sections = list(zip(starts, starts[1:] + [payload]))
    if any(end - start < 0x38 for start, end in sections):
        raise ValueError("Truncated DTM model detail-level header")
    return payload, base, rows, sections


def lod_packet_ranges(model, sections, reference, mesh_size, packets):
    offsets = [packet.position for packet in packets]
    ranges = []
    previous_end = 0
    for start, end in sections:
        first = previous_end
        # The model submits contiguous mesh blocks through aligned DMA REF tags.
        for tag_offset in range((start + 15) & ~15, end - 15, 16):
            control, pointer = struct.unpack_from("<2I", model, tag_offset)
            if control >> 16 != 0x3000 or not reference <= pointer < reference + mesh_size:
                continue
            offset = pointer - reference
            length = (control & 0xffff) * 16
            if offset != previous_end or not length or offset + length > mesh_size:
                raise ValueError("The model's DMA references do not form contiguous mesh blocks")
            previous_end += length
        first_packet = bisect_left(offsets, first)
        next_packet = bisect_left(offsets, previous_end)
        if first_packet == next_packet:
            raise ValueError("No mesh packets found for a DTM model detail level")
        ranges.append(range(first_packet, next_packet))
    if previous_end != mesh_size:
        raise ValueError("The model's detail levels do not cover the mesh payload")
    return ranges


def lod_part_counts(model, sections, base):
    counts = {}
    for lod, (start, end) in enumerate(sections):
        first, last = (address - base for address in struct.unpack_from("<2I", model, start + 0x24))
        count = read_word(model, start + 0x30)
        if not start + 0x38 <= first < last <= end or last - first != count * 0x30:
            raise ValueError(f"Invalid model part table for LOD {lod}")
        counts[lod] = count
    return counts


def part_map_coverage(data, counts):
    lods = read_part_map(data)
    if len(lods) != len(counts):
        raise ValueError(f"Part map contains {len(lods)} detail levels, expected {len(counts)}")
    levels = {}
    for lod, row in enumerate(lods):
        used = set()
        active = 0
        for slot, part in enumerate(row):
            if part == 0xffffffff:
                continue
            if part >= counts[lod]:
                raise ValueError(f"Part map LOD {lod} slot {slot} refers to part {part}, "
                                 f"outside the model's {counts[lod]} parts")
            used.add(part)
            active += 1
        levels[lod] = {"assigned_slots": active, "distinct_parts": len(used)}
    return {"entries_per_lod": len(lods[0]), "lods": levels}


def model_info(args):
    data = args.model.read_bytes()
    payload, base, rows, sections = model_sections(data)
    starts = [start for start, _ in sections]
    hi_reference, mesh_reference = struct.unpack_from("<2I", data, 0x30)
    mesh = args.mesh.read_bytes()
    mesh_base, streams = mesh_packets(mesh)
    if mesh_base != mesh_reference:
        raise ValueError("The mesh base does not match the model's mesh reference")
    ranges = lod_packet_ranges(data, sections[1:], mesh_reference, relocation_table(mesh)[0], streams)
    info = dict(model_base=f"{base:#010x}", model_payload_bytes=payload, model_section_offsets=starts,
                model_relocation_kinds=dict(sorted(Counter(rows.values()).items())),
                mesh_base=f"{mesh_reference:#010x}", mesh_packets=len(streams),
                mesh_positions=sum(packet.count for packet in streams), hi_mesh_reference=f"{hi_reference:#010x}")
    if args.hi_mesh:
        hi_mesh = args.hi_mesh.read_bytes()
        hi_base, hi_streams = mesh_packets(hi_mesh)
        if hi_base != hi_reference:
            raise ValueError("The high-detail mesh base does not match the model's high-detail reference")
        info["hi_mesh_packets"] = len(hi_streams)
        info["hi_mesh_positions"] = sum(packet.count for packet in hi_streams)
        ranges = lod_packet_ranges(data, sections[:1], hi_reference, relocation_table(hi_mesh)[0], hi_streams) + ranges
    info["lod_packet_ranges"] = {}
    info["lod_part_counts"] = lod_part_counts(data, sections, base)
    for lod, packets in enumerate(ranges, start=0 if args.hi_mesh else 1):
        if len(packets) != read_word(data, starts[lod] + 0x34):
            raise ValueError(f"The traced packets do not match the model's LOD {lod} packet count")
        info["lod_packet_ranges"][lod] = {"first_packet": packets.start, "packet_count": len(packets)}
    if args.part_map:
        info["part_map"] = part_map_coverage(args.part_map.read_bytes(), info["lod_part_counts"])
    print(json.dumps(info, indent=2))


def vertices(streams):
    for index, packet in enumerate(streams):
        for vertex in range(packet.count):
            yield index, vertex, packet.position + vertex * VERTEX.size


def mesh_export(args):
    data = args.mesh.read_bytes()
    _, streams = mesh_packets(data)
    with args.output.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(CSV_FIELDS)
        for packet, vertex, offset in vertices(streams):
            coordinates = (f"{value:.9g}" for value in VERTEX.unpack_from(data, offset))
            writer.writerow((packet, vertex, *coordinates))


def mesh_import(args):
    data = bytearray(args.mesh.read_bytes())
    _, streams = mesh_packets(data)
    with args.positions.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        if next(reader, None) != CSV_FIELDS:
            raise ValueError("Expected the packet,vertex,x,y,z columns from mesh-export")
        for (packet, vertex, offset), line in zip(vertices(streams), reader, strict=True):
            if len(line) != 5 or int(line[0]) != packet or int(line[1]) != vertex:
                raise ValueError(f"Expected packet {packet}, vertex {vertex} in CSV row {reader.line_num}")
            coordinates = tuple(map(float, line[2:]))
            if not all(map(math.isfinite, coordinates)):
                raise ValueError(f"Non-finite position at CSV row {reader.line_num}")
            VERTEX.pack_into(data, offset, *coordinates)
    with args.output.open("xb") as stream:
        stream.write(data)


def mesh_preview(args):
    data = args.mesh.read_bytes()
    base, packets = mesh_packets(data)
    indices = range(len(packets))
    if (args.model is None) != (args.lod is None):
        raise ValueError("Supply both --model and --lod to preview one detail level")
    if args.combined_lods and args.model is None:
        raise ValueError("Supply --model and --lod with --combined-lods")
    if args.model is not None:
        model = args.model.read_bytes()
        _, _, _, sections = model_sections(model)
        high, standard = struct.unpack_from("<2I", model, 0x30)
        reference = high if args.lod == 0 and not args.combined_lods else standard
        if base != reference:
            raise ValueError(f"The mesh base does not match the model's LOD {args.lod} reference")
        detail_sections = sections
        if not args.combined_lods:
            detail_sections = sections[:1] if args.lod == 0 else sections[1:]
        ranges = lod_packet_ranges(model, detail_sections, reference, relocation_table(data)[0], packets)
        indices = ranges[args.lod if args.combined_lods else max(0, args.lod - 1)]
    if not all(packets[index].triangle_strip for index in indices):
        raise ValueError("An input packet lacks a supported triangle-strip GIF template")
    output = ["# PS2 car strip preview in local mesh coordinates.\n"]
    first = 1
    for index in indices:
        packet = packets[index]
        points = list(VERTEX.iter_unpack(data[packet.position:packet.position + packet.count * VERTEX.size]))
        output.append(f"g packet_{index}\n")
        for label, values in (("v", points),
                              ("vt", UV.iter_unpack(data[packet.uv:packet.uv + packet.count * UV.size])),
                              ("vn", VERTEX.iter_unpack(data[packet.normal:packet.normal + packet.count * VERTEX.size]))):
            for row in values:
                if not all(map(math.isfinite, row)):
                    raise ValueError(f"Non-finite {label} values in packet {index}")
                output.append(label + " " + " ".join(f"{component:.9g}" for component in row) + "\n")
        for vertex in range(packet.count - 2):
            order = (vertex, vertex + 1, vertex + 2) if vertex % 2 == 0 else (vertex + 1, vertex, vertex + 2)
            if len({points[i] for i in order}) == 3:
                output.append("f " + " ".join(f"{first+i}/{first+i}/{first+i}" for i in order) + "\n")
        first += packet.count
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.writelines(output)


def obj_index(value, values):
    index = int(value)
    offset = index - 1 if index > 0 else len(values) + index
    if not index or not 0 <= offset < len(values):
        raise ValueError("OBJ index refers to a missing attribute")
    return values[offset]


def unit_vector(point):
    length = math.hypot(*point)
    if not length:
        raise ValueError("OBJ contains a zero-length normal or a degenerate triangle")
    return tuple(value / length for value in point)


def read_obj_packets(path):
    attributes = {"v": (VERTEX, []), "vt": (UV, []), "vn": (VERTEX, [])}
    positions, texcoords, normals = (attributes[key][1] for key in ("v", "vt", "vn"))
    groups = {}
    packet = None
    with path.open(encoding="utf-8-sig") as stream:
        for number, line in enumerate(stream, 1):
            fields = line.partition("#")[0].split()
            if not fields:
                continue
            label, *values = fields
            if label in attributes:
                layout, target = attributes[label]
                data = tuple(map(float, values))
                if len(data) * 4 != layout.size or not all(map(math.isfinite, data)):
                    raise ValueError(f"Invalid {label} on OBJ line {number}")
                target.append(layout.unpack(layout.pack(*data)))
            elif label == "g":
                name = values[0] if len(values) == 1 else ""
                suffix = name.removeprefix("packet_")
                packet = int(suffix) if name.startswith("packet_") and suffix.isascii() and suffix.isdecimal() else None
            elif label == "f":
                if packet is None or len(values) != 3:
                    raise ValueError(f"Expected a triangle in a packet_N group on OBJ line {number}")
                corners = [value.split("/") for value in values]
                if any(not 2 <= len(corner) <= 3 or not corner[1] for corner in corners):
                    raise ValueError(f"OBJ line {number} needs a texture coordinate per corner")
                points = [obj_index(corner[0], positions) for corner in corners]
                a, b, c = points
                ab = tuple(v - u for u, v in zip(a, b))
                ac = tuple(v - u for u, v in zip(a, c))
                normal = unit_vector((ab[1] * ac[2] - ab[2] * ac[1], ab[2] * ac[0] - ab[0] * ac[2],
                                      ab[0] * ac[1] - ab[1] * ac[0]))
                face = []
                for point, corner in zip(points, corners):
                    uv = obj_index(corner[1], texcoords)
                    direction = unit_vector(obj_index(corner[2], normals)) if len(corner) == 3 and corner[2] else normal
                    face.append((point, uv, direction))
                groups.setdefault(packet, []).append(tuple(face))
    if not groups:
        raise ValueError("OBJ contains no packet triangles")
    return groups


def triangle_strip(faces):
    strip = list(faces[0])
    for face in faces[1:]:
        # Match the ordered edge after applying the strip's alternating winding.
        tail = tuple(strip[-2:])
        if len(strip) % 2:
            tail = tail[::-1]
        for i in range(3):
            if (face[i], face[(i + 1) % 3]) == tail:
                strip.append(face[(i + 2) % 3])
                break
        else:
            a, b, c = face if len(strip) % 2 == 0 else (face[1], face[0], face[2])
            strip.extend((strip[-1], a, a, b, c))
    return strip


def write_mesh_strip(data, packet, strip):
    strip.extend([strip[-1]] * (packet.count - len(strip)))
    for vertex, (point, uv, normal) in enumerate(strip):
        VERTEX.pack_into(data, packet.position + vertex * VERTEX.size, *point)
        UV.pack_into(data, packet.uv + vertex * UV.size, *uv)
        VERTEX.pack_into(data, packet.normal + vertex * VERTEX.size, *normal)


def mesh_replace(args):
    data = bytearray(args.mesh.read_bytes())
    _, packets = mesh_packets(data)
    for index, faces in read_obj_packets(args.obj).items():
        if index >= len(packets) or not packets[index].triangle_strip:
            raise ValueError(f"Packet {index} has no supported triangle strip")
        packet = packets[index]
        strip = triangle_strip(faces)
        if len(strip) > packet.count:
            raise ValueError(f"Packet {index} needs {len(strip)} strip vertices and has room for {packet.count}")
        write_mesh_strip(data, packet, strip)
    with args.output.open("xb") as stream:
        stream.write(data)


def mesh_copy_strip(args):
    if any(not math.isfinite(value) or value <= 0 for value in args.scale):
        raise ValueError("Strip scale values must be finite and positive")
    if not all(map(math.isfinite, args.offset)):
        raise ValueError("Strip translation must be finite")
    source = args.source.read_bytes()
    data = bytearray(args.mesh.read_bytes())
    _, source_packets = mesh_packets(source)
    _, target_packets = mesh_packets(data)
    if not 0 <= args.from_packet < len(source_packets):
        raise ValueError(f"Source packet {args.from_packet} is out of range")
    if not 0 <= args.to_packet < len(target_packets):
        raise ValueError(f"Target packet {args.to_packet} is out of range")
    donor = source_packets[args.from_packet]
    target = target_packets[args.to_packet]
    if not donor.triangle_strip or not target.triangle_strip:
        raise ValueError("Both mesh packets must use a supported triangle strip")
    if donor.count > target.count:
        raise ValueError(f"Source strip has {donor.count} vertices but target packet has room for {target.count}")

    smallest_scale = min(args.scale)
    normal_scale = tuple(smallest_scale / scale for scale in args.scale)
    strip = []
    for vertex in range(donor.count):
        original = VERTEX.unpack_from(source, donor.position + vertex * VERTEX.size)
        point = tuple(value * scale + offset for value, scale, offset in zip(original, args.scale, args.offset))
        uv = UV.unpack_from(source, donor.uv + vertex * UV.size)
        normal = VERTEX.unpack_from(source, donor.normal + vertex * VERTEX.size)
        if not all(map(math.isfinite, (*point, *uv, *normal))):
            raise ValueError(f"Non-finite mesh attributes at source vertex {vertex}")
        if normal_scale != (1, 1, 1) and any(normal):
            normal = unit_vector(tuple(value * scale for value, scale in zip(normal, normal_scale)))
        strip.append((point, uv, normal))
    write_mesh_strip(data, target, strip)
    with args.output.open("xb") as stream:
        stream.write(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    info = commands.add_parser("model-info", help="check a DTM model and its referenced meshes")
    info.add_argument("model", type=Path)
    info.add_argument("mesh", type=Path)
    info.add_argument("--hi-mesh", type=Path)
    info.add_argument("--part-map", type=Path, help="check a variant's part.map indices against the model")
    info.set_defaults(run=model_info)
    export = commands.add_parser("mesh-export", help="export packed vertex positions as editable CSV")
    export.add_argument("mesh", type=Path)
    export.add_argument("output", type=Path)
    export.set_defaults(run=mesh_export)
    load = commands.add_parser("mesh-import", help="copy edited CSV positions into a new mesh file")
    load.add_argument("mesh", type=Path, help="original mesh providing the packet layout")
    load.add_argument("positions", type=Path, help="edited CSV from mesh-export")
    load.add_argument("output", type=Path)
    load.set_defaults(run=mesh_import)
    preview = commands.add_parser("mesh-preview", help="export verified triangle-strip streams as an OBJ preview")
    preview.add_argument("mesh", type=Path)
    preview.add_argument("output", type=Path)
    preview.add_argument("--model", type=Path, help="matching .mdl for a single detail level")
    preview.add_argument("--lod", type=int, choices=range(5), help="0 for high detail, or 1 to 4 for class mesh detail")
    preview.add_argument("--combined-lods", action="store_true",
                         help="use the RD2 mesh layout containing all five detail levels")
    preview.set_defaults(run=mesh_preview)
    replace = commands.add_parser("mesh-replace", help="replace selected car mesh packets with triangulated OBJ geometry")
    replace.add_argument("mesh", type=Path, help="template mesh providing the packet capacities and materials")
    replace.add_argument("obj", type=Path, help="triangles with UVs in packet_N groups")
    replace.add_argument("output", type=Path)
    replace.set_defaults(run=mesh_replace)
    copy = commands.add_parser("mesh-copy-strip", help="copy an existing PS2 car triangle strip into another mesh")
    copy.add_argument("source", type=Path, help="donor mesh")
    copy.add_argument("mesh", type=Path, help="target template mesh")
    copy.add_argument("output", type=Path, help="new mesh file")
    copy.add_argument("--from-packet", type=int, required=True, help="zero-based donor packet index")
    copy.add_argument("--to-packet", type=int, required=True, help="zero-based target packet index")
    copy.add_argument("--scale", type=float, nargs=3, default=(1, 1, 1), metavar=("X", "Y", "Z"),
                      help="scale donor positions in the target axes before applying the offset")
    copy.add_argument("--offset", type=float, nargs=3, default=(0, 0, 0), metavar=("X", "Y", "Z"),
                      help="donor translation in the target mesh's local coordinates")
    copy.set_defaults(run=mesh_copy_strip)
    args = parser.parse_args()
    try:
        args.run(args)
    except (OSError, ValueError, OverflowError, struct.error) as error:
        parser.exit(1, f"Car mesh operation failed: {error}\n")


if __name__ == "__main__":
    main()
