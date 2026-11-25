"""Read animated parts from the RD2 PS2 CP3D cockpit model."""

import math
import struct

from BuildTrackGeometryOverlay import read_word, vif_commands
from Ps2CarModel import UV, VERTEX


def cockpit_part(data, part_id):
    if len(data) < 0x130 or data[:8] != b"CP3D\x01\x01\x06\x02":
        raise ValueError("Expected an RD2 PS2 CP3D cockpit")
    directory = read_word(data, 8)
    if not 0x130 <= directory <= len(data) - 0x38:
        raise ValueError("Invalid CP3D cockpit directory")

    instance = read_word(data, 0x128)
    visited = set()
    while instance:
        node = instance + 0x80
        geometry = node + 0xd0
        if (instance in visited or instance % 16 or not 0x130 <= instance <= directory - 0x160
                or read_word(data, node) != geometry or read_word(data, node + 4) != 0xa0):
            raise ValueError("Invalid CP3D cockpit instance")
        visited.add(instance)
        if read_word(data, node + 0xc0) == part_id:
            matrix = data[instance + 0x40:node]
            entries = read_word(data, geometry + 4)
            if not 0x130 <= entries <= directory - 32 or read_word(data, entries + 4) != 1:
                raise ValueError("Expected one CP3D material group for the part")
            group = read_word(data, entries + 8)
            if not 0x130 <= group <= directory - 0x30:
                raise ValueError("Invalid CP3D material group")
            name = read_word(data, group + 0x28)
            if not 0x130 <= name < directory:
                raise ValueError("Invalid CP3D material name")
            end = data.find(b"\0", name, min(name + 32, directory))
            if end <= name or not all(map(math.isfinite, struct.unpack("<16f", matrix))):
                raise ValueError("Invalid CP3D part material or transform")
            return matrix, data[name:end].decode("ascii"), tuple(draw_strips(data, read_word(data, group + 4), directory))
        instance = read_word(data, node + 12)
    raise ValueError(f"Missing CP3D cockpit part {part_id}")


def draw_strips(data, packet, directory):
    visited = set()
    while True:
        if packet in visited or packet % 16 or not 0x130 <= packet <= directory - 16:
            raise ValueError("Invalid CP3D draw chain")
        visited.add(packet)
        tag, following = struct.unpack_from("<2I", data, packet)
        kind = tag >> 28
        end = packet + 16 + (tag & 0xffff) * 16
        if kind not in (2, 6) or end > directory or (kind == 6 and following):
            raise ValueError("Invalid CP3D draw packet")
        commands = tuple(cmd for cmd in vif_commands(data, packet + 12, end) if cmd.operation)
        if tuple(cmd.operation for cmd in commands) != (0x6c, 0x68, 0x6e, 0x64, 0x69, 0x17):
            raise ValueError("Unsupported CP3D triangle strip")
        header, vertex, color, uv, normal, draw = commands
        count = read_word(data, header.payload)
        if (header.count != 2 or draw.immediate != 0 or not 3 <= count <= 30
                or any(cmd.count != count for cmd in (vertex, color, uv, normal))):
            raise ValueError("Inconsistent CP3D vertex count")
        points = tuple(VERTEX.iter_unpack(data[vertex.payload:vertex.payload + vertex.size]))
        texcoords = tuple(UV.iter_unpack(data[uv.payload:uv.payload + uv.size]))
        if not all(math.isfinite(value) for rows in (points, texcoords) for row in rows for value in row):
            raise ValueError("Non-finite CP3D strip coordinate")
        yield points, texcoords
        if kind == 6:
            return
        packet = following
