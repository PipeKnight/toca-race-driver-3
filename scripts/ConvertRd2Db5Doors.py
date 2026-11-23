"""Supply paint materials for the DB5 door strips drawn by RD3."""

import struct

from BuildTrackGeometryOverlay import read_word, vif_commands
from ModAssets import read_part_map
from Ps2CarModel import STREAM_HEADER, UV, VERTEX, mesh_packets, model_sections, relocation_table


INTERIOR_PAGE = 0x3200
DONOR_PAINT_PAGE = 0x351c
BODY_PAGE = 0x341c
BODY_TEX0 = (0x2007e0062131341c, 0x2007f0062131398e, 0x2000000621310000)
CLASS_BODY_TEX0 = (0x2007e005e131341c, 0x2007f005e131398e, 0x20000005e1310000)


def paint_uv(y, z, samples):
    nearest = sorted(((sy - y)**2 + (sz - z)**2, uv) for (_, sy, sz), uv in samples)[:4]
    weights = [1 / max(0.0001, distance) for distance, _ in nearest]
    return tuple(sum(weight * uv[axis] for weight, (_, uv) in zip(weights, nearest)) / sum(weights)
                 for axis in range(2))


def door_streams(model, mesh, part_map, lod):
    _, base, _, sections = model_sections(model)
    mesh_base, mesh_packets_ = mesh_packets(mesh)
    extent, _, _ = relocation_table(mesh)
    start, end = sections[lod]
    first, last = (pointer - base for pointer in struct.unpack_from("<2I", model, start + 0x24))
    active = read_part_map(part_map)[lod]
    interior_counts = ((5, 4), (3, 4), (1, 1), (1, 1))
    paint_page = DONOR_PAINT_PAGE if not lod else BODY_PAGE
    for slot, interior_count in zip((12, 13), interior_counts[lod]):
        part = first + 0x30 * active[slot]
        if not first <= part <= last - 0x30 or read_word(model, part):
            raise ValueError(f"Missing DB5 LOD {lod} door part {slot}")
        draw = read_word(model, part + 8) - base
        if not last <= draw <= end - 0x98:
            raise ValueError("Invalid DB5 door draw descriptor")
        ref = (read_word(model, draw + 0x94) & 0x7fffffff) - base
        if not start <= ref <= end - 32:
            raise ValueError("Invalid DB5 door mesh reference")
        command, pointer = struct.unpack_from("<2I", model, ref)
        begin = pointer - mesh_base
        finish = begin + 16 * (command & 0xffff)
        if command >> 16 != 0x3000 or read_word(model, ref + 16) >> 28 & 7 == 3 or not 0 <= begin < finish <= extent:
            raise ValueError("Expected one DMA reference for each DB5 door")
        starts = [index for index in range(begin, finish - 35, 4) if read_word(mesh, index) == STREAM_HEADER]
        packets = [p for p in mesh_packets_ if begin <= p.position < finish]
        swaps, interior, paint = [], [], []
        material = None
        for offset, packet in zip(starts, packets, strict=True):
            texture_changes = []
            for command in vif_commands(mesh, offset, finish):
                if command.operation in (0x14, 0x17):
                    break
                if command.operation != 0x6c or command.payload == offset + 4:
                    continue
                for at in range(command.payload, command.payload + command.size, 16):
                    value, register = struct.unpack_from("<QQ", mesh, at)
                    if register == 6:
                        texture_changes.append((at, value & 0x3fff))
            if texture_changes:
                material = texture_changes[0][1]
                if material == INTERIOR_PAGE:
                    swaps.extend(at for at, base in texture_changes if base == INTERIOR_PAGE)
            if material == INTERIOR_PAGE:
                interior.append(packet)
            elif material == paint_page:
                paint.append(packet)
        if len(swaps) != 3 or len(interior) != interior_count or not paint:
            raise ValueError(f"Unexpected material groups for DB5 LOD {lod} door part {slot}")
        if not lod and len(paint) != (4 if slot == 12 else 3):
            raise ValueError(f"Unexpected high-detail paint group for DB5 door part {slot}")
        yield swaps, interior, paint


def paint_doors(model, mesh, part_map, lods=(0,)):
    output = bytearray(mesh)
    for lod in lods:
        for swaps, interior, paint in door_streams(model, mesh, part_map, lod):
            samples = []
            for strip in paint:
                xyz = mesh[strip.position:strip.position + VERTEX.size * strip.count]
                uv = mesh[strip.uv:strip.uv + UV.size * strip.count]
                samples.extend(zip(VERTEX.iter_unpack(xyz), UV.iter_unpack(uv), strict=True))
            # RD3 draws this leading group in the exterior, but it names an RD2 global trim page.
            for offset, tex0 in zip(swaps, CLASS_BODY_TEX0 if lod else BODY_TEX0, strict=True):
                struct.pack_into("<Q", output, offset, tex0)
            for strip in interior:
                for index in range(strip.count):
                    _, y, z = VERTEX.unpack_from(mesh, strip.position + VERTEX.size * index)
                    UV.pack_into(output, strip.uv + UV.size * index, *paint_uv(y, z, samples))
    return bytes(output)
