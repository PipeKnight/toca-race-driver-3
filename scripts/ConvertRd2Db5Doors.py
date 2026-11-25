"""Supply paint materials for the DB5 door strips drawn by RD3."""

import math
import struct
from dataclasses import dataclass

from BuildTrackGeometryOverlay import read_word, vif_commands
from ModAssets import read_part_map
from Ps2CarModel import STREAM_HEADER, UV, VERTEX, mesh_packets, model_sections, relocation_table


INTERIOR_PAGE = 0x3200
DONOR_PAINT_PAGE = 0x351c
CLASS_DOOR_PAINT_PAGE = 0x349c
BODY_TEX0 = (0x2007e0062131341c, 0x2007f0062131398e, 0x2000000621310000)


@dataclass
class DoorStreams:
    trim: list
    paint: list
    trim_textures: list
    paint_textures: tuple
    trim_settings: int | None
    paint_settings: int | None
    trim_reflections: list

def blend_paint(y, z, samples, size):
    nearest = sorted(((sy - y)**2 + (sz - z)**2, value) for (_, sy, sz), value in samples)[:4]
    if not nearest:
        raise ValueError("No reference samples for the DB5 door paint")
    weights = [1 / max(0.0001, distance) for distance, _ in nearest]
    return tuple(sum(weight * value[axis] for weight, (_, value) in zip(weights, nearest)) / sum(weights)
                 for axis in range(size))


def paint_uv(y, z, samples):
    return blend_paint(y, z, samples, 2)


def paint_normal(y, z, samples):
    direction = blend_paint(y, z, samples, 3)
    magnitude = math.hypot(*direction)
    if not math.isfinite(magnitude) or magnitude < .4:
        raise ValueError("Invalid exterior reference normals for the DB5 door paint")
    return tuple(value / magnitude for value in direction)


def door_streams(model, mesh, part_map, lod):
    _, base, _, sections = model_sections(model)
    mesh_base, mesh_packets_ = mesh_packets(mesh)
    extent, _, _ = relocation_table(mesh)
    start, end = sections[lod]
    first, last = (pointer - base for pointer in struct.unpack_from("<2I", model, start + 0x24))
    active = read_part_map(part_map)[lod]
    interior_counts = ((5, 4), (3, 4), (1, 1), (1, 1))
    paint_page = DONOR_PAINT_PAGE if not lod else CLASS_DOOR_PAINT_PAGE
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
        trim, paint, swaps, trim_reflections = [], [], [], []
        trim_settings = paint_settings = None
        paint_textures = ()
        material = None
        for offset, packet in zip(starts, packets, strict=True):
            texture_changes = []
            draw_tags = []
            settings = None
            for command in vif_commands(mesh, offset, finish):
                if command.operation in (0x14, 0x17):
                    break
                if command.operation != 0x6c or command.payload == offset + 4:
                    continue
                if settings is None and command.size == 32:
                    settings = command.payload
                for at in range(command.payload, command.payload + command.size, 16):
                    value, register = struct.unpack_from("<QQ", mesh, at)
                    if register == 6:
                        texture_changes.append((at, value))
                    if register == 0x512:
                        draw_tags.append((at, value))
            if texture_changes:
                material = texture_changes[0][1] & 0x3fff
                if material == INTERIOR_PAGE:
                    swaps.extend(at for at, value in texture_changes if value & 0x3fff == INTERIOR_PAGE)
                    trim_settings = settings
                elif material == paint_page and not paint_textures:
                    paint_textures = tuple(value for _, value in texture_changes)
                    paint_settings = settings
            if material == INTERIOR_PAGE:
                trim.append(packet)
                if len(draw_tags) == 2 and not draw_tags[0][1] & 0x8000 and draw_tags[1][1] & 0x8000:
                    trim_reflections.append(draw_tags[1][0])
            elif material == paint_page:
                paint.append(packet)
        if len(swaps) != 3 or len(trim) != interior_count or not paint:
            raise ValueError(f"Unexpected material groups for DB5 LOD {lod} door part {slot}")
        if not lod and len(paint) != (4 if slot == 12 else 3):
            raise ValueError(f"Unexpected high-detail paint group for DB5 door part {slot}")
        if lod and (len(paint_textures) != 3 or trim_settings is None or paint_settings is None):
            raise ValueError(f"Missing DB5 LOD {lod} exterior paint bindings for part {slot}")
        yield DoorStreams(trim, paint, swaps, paint_textures, trim_settings, paint_settings, trim_reflections)


def paint_doors(model, mesh, part_map, lods=(0,)):
    output = bytearray(mesh)
    for lod in lods:
        for side, door in zip((-1, 1), door_streams(model, mesh, part_map, lod), strict=True):
            samples, normals = [], []
            for strip in door.paint:
                xyz = tuple(VERTEX.iter_unpack(mesh[strip.position:strip.position + VERTEX.size * strip.count]))
                uv = mesh[strip.uv:strip.uv + UV.size * strip.count]
                normal = mesh[strip.normal:strip.normal + VERTEX.size * strip.count]
                samples.extend(zip(xyz, UV.iter_unpack(uv), strict=True))
                # Lower-detail strips can share paint between outward faces and folded edges.
                normals.extend((pos, n) for pos, n in zip(xyz, VERTEX.iter_unpack(normal), strict=True)
                               if side * n[0] > .4)
            # RD3 draws this leading group in the exterior, but it names an RD2 global trim page.
            # Rebind its paint and lighting without changing the door skin, hinge, or cockpit trim.
            textures = door.paint_textures if lod else BODY_TEX0
            for offset, tex0 in zip(door.trim_textures, textures, strict=True):
                struct.pack_into("<Q", output, offset, tex0)
            if lod:
                source = door.paint_settings
                target = door.trim_settings
                assert source is not None and target is not None
                output[target:target + 32] = mesh[source:source + 32]
                # Keep additive reflections on the outer skin. Use XYZ3 on the
                # trim to retain the clipper's packet layout without drawing it twice.
                for offset in door.trim_reflections:
                    struct.pack_into("<Q", output, offset + 8, 0xd12)
            for strip in door.trim:
                for index in range(strip.count):
                    _, y, z = VERTEX.unpack_from(mesh, strip.position + VERTEX.size * index)
                    UV.pack_into(output, strip.uv + UV.size * index, *paint_uv(y, z, samples))
                    VERTEX.pack_into(output, strip.normal + VERTEX.size * index, *paint_normal(y, z, normals))
    return bytes(output)
