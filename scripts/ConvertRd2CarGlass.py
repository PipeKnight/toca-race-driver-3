"""Keep the tinted pass of a verified RD2 windshield in the RD3 exterior renderer."""

import struct

from BuildTrackGeometryOverlay import read_word, vif_commands
from ModAssets import read_part_map
from Ps2CarModel import STREAM_HEADER, model_sections, relocation_table


def convert_windshield(model, mesh, part_map, strips_by_lod, *, share_windshield_tint=False):
    _, base, _, sections = model_sections(model)
    maps = read_part_map(part_map)
    extent, mesh_base, _ = relocation_table(mesh)
    output = bytearray(mesh)
    for lod, expected_strips in strips_by_lod.items():
        first = read_word(model, sections[lod][0] + 0x24) - base
        part = first + 0x30 * maps[lod][32]
        if not first <= part < first + 0x30 * read_word(model, sections[lod][0] + 0x30):
            raise ValueError(f"Missing RD2 windshield in LOD {lod}")
        if read_word(model, part) != 1:
            raise ValueError(f"Unexpected RD2 windshield descriptor in LOD {lod}")
        descriptor = read_word(model, part + 8) - base
        tag = (read_word(model, descriptor + 0x14) & 0x7fffffff) - base
        strips = 0
        while read_word(model, tag) >> 28 & 7 == 3:
            control, pointer = struct.unpack_from("<2I", model, tag)
            tag += 16
            begin = pointer - mesh_base
            end = begin + 16 * (control & 0xffff)
            if not 0 <= begin < end <= extent:
                continue  # A composite drawable can reference its transform in the MDL.
            for start in range(begin, end - 35, 4):
                if read_word(mesh, start) != STREAM_HEADER:
                    continue
                draw_tags = []
                tex0 = []
                for command in vif_commands(mesh, start, end):
                    if command.operation in (0x14, 0x17):
                        break
                    if command.operation == 0x6c and command.payload != start + 4:
                        for offset in range(command.payload, command.payload + command.size, 16):
                            value, registers = struct.unpack_from("<QQ", mesh, offset)
                            if registers == 0x512:
                                draw_tags.append((offset, value))
                            elif share_windshield_tint and registers == 6:
                                tex0.append((offset, value))
                if (len(draw_tags) != 2 or draw_tags[0][1] & 0x8000
                        or not draw_tags[1][1] & 0x8000):
                    raise ValueError(f"Unexpected RD2 windshield draw packet in LOD {lod}")
                offset, _ = draw_tags[1]
                # The clipper still consumes the full reflection packet. XYZ3 preserves
                # its vertex updates without drawing the additive reflection triangles.
                struct.pack_into("<Q", output, offset + 8, 0xd12)
                if tuple(value for _, value in tex0) == (
                        0x20068305e1313100, 0x20068185e1313300, 0x20068305e1313100):
                    # The Lancer's alternate binding at 0x3300 samples livery pixels in RD3.
                    # Use the matching tinted page and palette from the other two bindings.
                    struct.pack_into("<Q", output, tex0[1][0], tex0[0][1])
                strips += 1
        if strips != expected_strips:
            raise ValueError(f"Unexpected RD2 windshield strip count in LOD {lod}")
    return bytes(output)
