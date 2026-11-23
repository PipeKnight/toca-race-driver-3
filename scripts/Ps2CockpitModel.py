#!/usr/bin/env python3
"""Export local-coordinate mesh strips from an RD3 PS2 cockpit model."""

import argparse
from itertools import islice
import math
from pathlib import Path
import struct

from BuildTrackGeometryOverlay import read_word, vif_commands
from Ps2CarModel import UV, VERTEX


def cockpit_nodes(data):
    if len(data) < 36 or data[:4] != b"PS2M" or read_word(data, 4) != 3:
        raise ValueError("Expected a version 3 PS2M cockpit model")
    scene = read_word(data, 0x20)
    if not 36 <= scene <= len(data) - 40 or scene % 4:
        raise ValueError("Invalid PS2M scene offset")
    first_name = scene + 40
    offset = first_name + read_word(data, scene + 0x24)
    if offset > len(data) - 4 or offset % 4:
        raise ValueError("Invalid PS2M scene name table extent")
    names = data[first_name:offset].rstrip(b"\0").decode("ascii").split("\0")
    if read_word(data, offset) != len(names):
        raise ValueError("The cockpit name count does not match its node table")
    offset += 4
    nodes = []
    for name in names:
        if offset > len(data) - 80:
            raise ValueError("Truncated cockpit node")
        count = read_word(data, offset + 76)
        offset += 80
        if count > (len(data) - offset) // 4:
            raise ValueError("Truncated cockpit node draw references")
        references = struct.unpack_from(f"<{count}I", data, offset)
        if any(reference >= read_word(data, 8) for reference in references):
            raise ValueError(f"Invalid draw section reference for cockpit node {name}")
        nodes.append((name, references))
        offset += 4 * count
    for _ in range(read_word(data, 16)):
        if offset > len(data) - 4:
            raise ValueError("Truncated cockpit scene node list")
        count = read_word(data, offset)
        offset += 4
        if count > (len(data) - offset) // 4:
            raise ValueError("Invalid cockpit scene node list length")
        offset += 4 * count
    return offset, nodes


def cockpit_sections(data):
    offset, _ = cockpit_nodes(data)
    count = read_word(data, 8)
    if not 0 < count <= (len(data) - offset) // 40:
        raise ValueError("Missing cockpit draw sections")
    first = offset + 40
    sections = []
    for index in range(count):
        if (first > len(data) - 52 or read_word(data, first) != 0x6c018000
                or read_word(data, first - 40) != 1 or read_word(data, first - 8) != 0):
            raise ValueError(f"Invalid cockpit draw section {index}")
        size = read_word(data, first - 4)
        end = first + size
        if size < 52 or size % 16 or end > len(data) - 4:
            raise ValueError(f"Invalid cockpit draw section extent at {first:#x}")
        sections.append((first, end))
        first = end + 40
    if end != len(data) - 4 or read_word(data, end) != 0:
        raise ValueError("Unexpected data after the last cockpit draw section")
    return sections


def cockpit_strips(data):
    expected = (0x6c, 0, 0, 0, 0x6c, 0x74, 0x6e, 0x68, 0x17)
    for section, (begin, end) in enumerate(cockpit_sections(data)):
        for start in range(begin, end - 51, 4):
            if read_word(data, start) != 0x6c018000 or read_word(data, start + 16) != 0xf5:
                continue
            tag, registers = struct.unpack_from("<QQ", data, start + 36)
            if registers != 0x512 or (tag >> 47) & 7 != 4:
                continue
            commands = tuple(islice(vif_commands(data, start, end), len(expected)))
            if tuple(command.operation for command in commands) != expected:
                raise ValueError(f"Unsupported cockpit triangle strip at {start:#x}")
            uv, color, vertex = commands[5:8]
            if not 3 <= vertex.count == uv.count == color.count == (tag & 0x7fff):
                raise ValueError(f"Inconsistent cockpit strip length at {start:#x}")
            points = tuple(VERTEX.iter_unpack(data[vertex.payload:vertex.payload + vertex.size]))
            texcoords = tuple(UV.iter_unpack(data[uv.payload:uv.payload + uv.size]))
            if not all(math.isfinite(value) for rows in (points, texcoords) for row in rows for value in row):
                raise ValueError(f"Non-finite cockpit vertex at {start:#x}")
            yield section, start, points, texcoords


def preview(data, output):
    strips = tuple(cockpit_strips(data))
    if not strips:
        raise ValueError("No supported cockpit triangle strips")
    first = 1
    faces = 0
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("# RD3 PS2 cockpit strips in local mesh coordinates.\n")
        _, nodes = cockpit_nodes(data)
        for name, sections in nodes:
            for section in sections:
                stream.write(f"# Draw section {section}: {name}\n")
        for section, offset, points, texcoords in strips:
            stream.write(f"g section_{section}_strip_{offset:08x}\n")
            for label, rows in (("v", points), ("vt", texcoords)):
                for row in rows:
                    stream.write(label + " " + " ".join(f"{value:.9g}" for value in row) + "\n")
            for vertex in range(len(points) - 2):
                order = (vertex, vertex + 1, vertex + 2)
                if vertex % 2:
                    order = (vertex + 1, vertex, vertex + 2)
                if len({points[index] for index in order}) == 3:
                    stream.write("f " + " ".join(f"{first + index}/{first + index}" for index in order) + "\n")
                    faces += 1
            first += len(points)
    return len(strips), faces


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("output", type=Path, help="new OBJ file")
    args = parser.parse_args()
    try:
        strips, faces = preview(args.model.read_bytes(), args.output)
    except (OSError, ValueError, struct.error) as error:
        parser.exit(1, f"Cockpit preview failed: {error}\n")
    print(f"{args.output} ({strips} strips, {faces} triangles)")


if __name__ == "__main__":
    main()
