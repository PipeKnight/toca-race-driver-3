#!/usr/bin/env python3
"""Convert the PS2 RD2 class model pair to the RD3 PS2 model layout."""

import argparse
from bisect import bisect_left
from pathlib import Path
import struct

from BuildTrackGeometryOverlay import FOOTER, RELOCATION, read_word, vif_commands
from Ps2CarModel import (
    STREAM_HEADER, lod_packet_ranges, lod_part_counts, mesh_packets, model_sections, relocation_table,
)


PART_BYTES = 0x30
RD3_PART_SLOTS = 320
DMA_REF = 3


def align16(offset):
    return (offset + 15) & ~15


def serialize_relocations(payload, relocations, base):
    directory = b"".join(RELOCATION.pack(offset, kind) for offset, kind in relocations.items())
    return bytes(payload) + directory + FOOTER.pack(len(relocations), len(payload), base)


def convert_mesh(mesh, model, sections, high_base, class_base):
    size, base, relocations = relocation_table(mesh)
    _, packets = mesh_packets(mesh)
    ranges = lod_packet_ranges(model, sections, base, size, packets)
    starts = [i for i in range(0, size - 35, 4) if read_word(mesh, i) == STREAM_HEADER]
    output = bytearray()
    offsets = {}
    refs = []
    split = 0
    for lod, (start, end) in enumerate(sections):
        if lod == 1:
            split = len(output)
        for tag in range(align16(start), end - 15, 16):
            control, address = struct.unpack_from("<2I", model, tag)
            if control >> 16 != 0x3000 or not base <= address < base + size:
                continue
            first = address - base
            last = first + (control & 0xffff) * 16
            output_first = len(output)
            cuts = []
            for packet in starts[bisect_left(starts, first):bisect_left(starts, last)]:
                colors = []
                for command in vif_commands(mesh, packet, last):
                    if command.operation == 0x6e:
                        colors.append((command.payload - 4, command.payload + command.size))
                    if command.operation in (0x14, 0x17):
                        break
                if len(colors) != 1:
                    raise ValueError(f"Expected one RD2 color upload in mesh packet at {packet:#x}")
                cuts.extend(colors)
            # RD3's CPU-side mesh walker expects positions immediately after UVs.
            cursor = first
            for cut_first, cut_last in cuts:
                output.extend(mesh[cursor:cut_first])
                cursor = cut_last
            output.extend(mesh[cursor:last])
            output.extend(bytes(align16(len(output)) - len(output)))
            for offset in relocations:
                if first <= offset < last:
                    removed = sum(b - a for a, b in cuts if b <= offset)
                    offsets[offset] = output_first + offset - first - removed
            pointer = high_base + output_first if lod == 0 else class_base + output_first - split
            refs.append((tag, pointer, len(output) - output_first))
    if offsets.keys() != relocations.keys() or not 0 < split < len(output):
        raise ValueError("RD2 mesh relocation coverage does not match the model")
    high_rows = {offsets[old]: kind for old, kind in relocations.items() if offsets[old] < split}
    class_rows = {offsets[old] - split: kind for old, kind in relocations.items() if offsets[old] >= split}
    high = serialize_relocations(output[:split], high_rows, high_base)
    low = serialize_relocations(output[split:], class_rows, class_base)
    return high, low, refs, [len(part) for part in ranges]


def count_part_chains(model, base, section_end, part):
    mode = read_word(model, part)
    if mode not in (0, 1):
        raise ValueError(f"Unsupported RD2 drawable part type {mode}")
    descriptor = read_word(model, part + 8) - base
    draw_field = descriptor + (0x14 if mode == 1 else 0x94)
    if not 0 <= descriptor <= draw_field <= section_end - 4:
        raise ValueError("Invalid RD2 drawable part descriptor")
    tag = (read_word(model, draw_field) & 0x7fffffff) - base
    first = tag
    while 0 <= tag <= section_end - 16 and read_word(model, tag) >> 28 & 7 == DMA_REF:
        tag += 16
    return (tag - first) // 16


def compact_rd2_model(model, base, sections, packet_counts):
    first_header = sections[0][0]
    if first_header != 0x38:
        raise ValueError("Unsupported RD2 model header size")
    output = bytearray(model[:first_header])
    spans = [(0, first_header, 0)]
    maps = []

    def copy(first, last):
        spans.append((first, last, len(output)))
        output.extend(model[first:last])

    for (start, end), packet_count in zip(sections, packet_counts):
        first, last = (p - base for p in struct.unpack_from("<2I", model, start + 0x24))
        slots, remainder = divmod(last - first, PART_BYTES)
        end_bindings = align16(last + slots * 4)
        if first != start + 0x30 or remainder or not 0 < slots <= RD3_PART_SLOTS or end_bindings > end:
            raise ValueError("Invalid RD2 sparse part or binding table")
        new_header = len(output)
        copy(start, first)
        output.extend(bytes(16))
        part_map = [0xffffffff] * RD3_PART_SLOTS
        active = []
        chains = 0
        for slot in range(slots):
            offset = first + slot * PART_BYTES
            if read_word(model, offset) == 0xffffffff:
                continue
            part_map[slot] = len(active)
            active.append(slot)
            chains += count_part_chains(model, base, end, offset)
            copy(offset, offset + PART_BYTES)
            struct.pack_into("<I", output, len(output) - PART_BYTES + 12, 0)
        if not active or active[0] != 0:
            raise ValueError("Expected a root part in RD2 slot zero")
        # The binding pointer table has the same sparse ordering as the parts.
        for slot in active:
            binding = last + slot * 4
            copy(binding, binding + 4)
        output.extend(bytes(align16(len(output)) - len(output)))
        copy(end_bindings, end)
        struct.pack_into("<3I", output, new_header + 0x2c, chains, len(active), packet_count)
        maps.append(part_map)
    return output, spans, maps


def convert_model(model, mesh, target):
    _, base, relocations, sections = model_sections(model)
    _, target_base, _, target_sections = model_sections(target)
    lod_part_counts(target, target_sections, target_base)
    texture_base, high_base, class_base = struct.unpack_from("<3I", target, 0x2c)
    if not texture_base or not high_base or not class_base or high_base == class_base:
        raise ValueError("The RD3 template must provide separate class and high-detail files")
    high, low, refs, counts = convert_mesh(mesh, model, sections, high_base, class_base)
    output, spans, maps = compact_rd2_model(model, base, sections, counts)

    def rebase(offset):
        for first, last, dest in spans:
            if first <= offset < last:
                return dest + offset - first
        raise ValueError(f"Model relocation refers to an absent part or padding at {offset:#x}")

    new_relocations = {}
    for old, kind in relocations.items():
        new_relocations[rebase(old)] = kind
        if kind != 4:
            field = old + (4 if kind == 3 else 0)
            value = read_word(model, field)
            if value:
                struct.pack_into("<I", output, rebase(field), target_base + rebase(value - base))
    for offset, pointer, length in refs:
        if not 0 < length // 16 <= 0xffff:
            raise ValueError("Converted mesh DMA block exceeds a single REF")
        struct.pack_into("<2I", output, rebase(offset), 0x30000000 | (length // 16), pointer)
    struct.pack_into("<3I", output, 0x2c, texture_base, high_base, class_base)
    converted = serialize_relocations(output, new_relocations, target_base)
    _, _, _, new_sections = model_sections(converted)
    part_counts = lod_part_counts(converted, new_sections, target_base)
    for body, lods, expected in ((high, new_sections[:1], counts[:1]), (low, new_sections[1:], counts[1:])):
        size, mesh_base, _ = relocation_table(body)
        _, packets = mesh_packets(body)
        if [len(group) for group in lod_packet_ranges(converted, lods, mesh_base, size, packets)] != expected:
            raise ValueError("Converted mesh changed the detail-level packet counts")
    part_map = struct.pack("<3I", 1, len(maps), RD3_PART_SLOTS)
    part_map += b"".join(struct.pack(f"<{RD3_PART_SLOTS}I", *row) for row in maps)
    return converted, high, low, part_map, part_counts, counts


def convert_textures(source, template):
    size, base, entries = relocation_table(source)
    _, target_base, _ = relocation_table(template)
    output = bytearray(source[:size])
    for offset, kind in entries.items():
        field = offset + (4 if kind == 3 else 0)
        if kind not in (0, 3) or field + 4 > size:
            raise ValueError("Unsupported RD2 texture relocation")
        pointer = read_word(source, field)
        if not base <= pointer < base + size:
            raise ValueError("Unsupported RD2 texture relocation")
        struct.pack_into("<I", output, field, pointer - base + target_base)
    header = 0x10 if entries.get(0) == 3 else 0x20
    count, start = struct.unpack_from("<2I", source, header)
    start -= base
    if not 0 <= start < size or not 0 < count <= (size - start) // 0x170:
        raise ValueError("Invalid RD2 texture descriptors")
    for index in range(count):
        row = start + index * 0x170
        if entries.get(row + 0xcc) != 0 or entries.get(row + 0xe8) != 0:
            raise ValueError(f"Unknown RD2 texture format at descriptor {index}")
        # RD2 stores the image size here. RD3 reads the number of mip uploads.
        struct.pack_into("<I", output, row + 0x38, 1)
        output[row + 0xd0:row + 0xe8] = bytes(0x18)
    return serialize_relocations(output, entries, target_base)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("model", "mesh", "class-textures", "high-textures", "target-model",
                 "target-class-textures", "target-high-textures", "output"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    args = parser.parse_args()
    try:
        converted, high, low, part_map, parts, packets = convert_model(
            args.model.read_bytes(), args.mesh.read_bytes(), args.target_model.read_bytes())
        class_textures = convert_textures(args.class_textures.read_bytes(), args.target_class_textures.read_bytes())
        high_textures = convert_textures(args.high_textures.read_bytes(), args.target_high_textures.read_bytes())
        _, class_texture_base, _ = relocation_table(class_textures)
        if class_texture_base != read_word(converted, 0x2c):
            raise ValueError("The class texture template must match the RD3 model reference address")
        args.output.mkdir(parents=True, exist_ok=False)
        for name, payload in (("car.mdl", converted), ("car_hi.msh", high), ("car.msh", low),
                              ("part.map", part_map), ("car.tex", class_textures), ("car_hi.tex", high_textures)):
            (args.output / name).write_bytes(payload)
    except (OSError, ValueError, struct.error) as error:
        parser.exit(1, f"Conversion failed: {error}\n")
    for lod, packet_count in enumerate(packets):
        print(f"LOD {lod}: {parts[lod]} drawable parts, {packet_count} mesh packets")


if __name__ == "__main__":
    main()
