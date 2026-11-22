#!/usr/bin/env python3
"""Inspect PS2 DTM model pairs and edit the position streams of their meshes."""

import argparse
from collections import Counter
import csv
from dataclasses import dataclass
import json
import math
from pathlib import Path
import struct

from BuildTrackGeometryOverlay import FOOTER, RELOCATION, VERTEX, read_word, vif_commands


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


def model_info(args):
    data = args.model.read_bytes()
    payload, base, rows = relocation_table(data)
    if payload < 0x38 or set(rows.values()) != {0, 3, 4}:
        raise ValueError("Expected a PS2 DTM model relocation table")
    starts = [address - base for address in struct.unpack_from("<5I", data)]
    if starts != sorted(set(starts)) or any(not 0x38 <= offset < payload for offset in starts):
        raise ValueError("Invalid DTM model section offsets")
    hi_reference, mesh_reference = struct.unpack_from("<2I", data, 0x30)
    mesh_base, streams = mesh_packets(args.mesh.read_bytes())
    if mesh_base != mesh_reference:
        raise ValueError("The mesh base does not match the model's mesh reference")
    info = dict(model_base=f"{base:#010x}", model_payload_bytes=payload, model_section_offsets=starts,
                model_relocation_kinds=dict(sorted(Counter(rows.values()).items())),
                mesh_base=f"{mesh_reference:#010x}", mesh_packets=len(streams),
                mesh_positions=sum(packet.count for packet in streams), hi_mesh_reference=f"{hi_reference:#010x}")
    if args.hi_mesh:
        hi_base, hi_streams = mesh_packets(args.hi_mesh.read_bytes())
        if hi_base != hi_reference:
            raise ValueError("The high-detail mesh base does not match the model's high-detail reference")
        info["hi_mesh_packets"] = len(hi_streams)
        info["hi_mesh_positions"] = sum(packet.count for packet in hi_streams)
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
    _, packets = mesh_packets(data)
    if not all(packet.triangle_strip for packet in packets):
        raise ValueError("An input packet lacks a supported triangle-strip GIF template")
    output = ["# PS2 DTM strip preview in local mesh coordinates.\n"]
    first = 1
    for index, packet in enumerate(packets):
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    info = commands.add_parser("model-info", help="check a DTM model and its referenced meshes")
    info.add_argument("model", type=Path)
    info.add_argument("mesh", type=Path)
    info.add_argument("--hi-mesh", type=Path)
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
    preview.set_defaults(run=mesh_preview)
    args = parser.parse_args()
    try:
        args.run(args)
    except (OSError, ValueError, OverflowError, struct.error) as error:
        parser.exit(1, f"Car mesh operation failed: {error}\n")


if __name__ == "__main__":
    main()
