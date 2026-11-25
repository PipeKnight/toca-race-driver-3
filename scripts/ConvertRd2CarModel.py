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
RD3_VU_BANKS = {42: 176, 369: 458, 696: 740}
RD2_VU_BANK_END = 326
RD3_VU_BANK_END = 281
RD3_TRIPLE_PASS_STRIP_SIZE = 24


def align16(offset):
    return (offset + 15) & ~15


def serialize_relocations(payload, relocations, base):
    directory = b"".join(RELOCATION.pack(offset, kind) for offset, kind in relocations.items())
    return bytes(payload) + directory + FOOTER.pack(len(relocations), len(payload), base)


def translate_vu_banks(mesh):
    extent, _, _ = relocation_table(mesh)
    output = bytearray(mesh)
    for start in range(0, extent - 35, 4):
        if read_word(mesh, start) != STREAM_HEADER:
            continue
        fields = struct.unpack_from("<8I", mesh, start + 4)
        bank, _, _, count, normal, _, _, _ = fields
        target = RD3_VU_BANKS.get(bank)
        if target is None or normal != bank + RD2_VU_BANK_END - count:
            raise ValueError(f"Unknown RD2 VU bank layout at {start:#x}")
        normal_target = target + RD3_VU_BANK_END - count
        for field, address in enumerate(fields):
            if field == 3 or address == 0:
                continue  # The count and unused pointers are independent of the VU bank.
            relative = address - bank
            if field != 4 and not 0 <= relative <= RD3_VU_BANK_END:
                raise ValueError(f"RD2 VU header address outside its strip bank at {start:#x}")
            struct.pack_into("<I", output, start + 4 * (field + 1),
                             normal_target if field == 4 else target + relative)

        for command in vif_commands(mesh, start, extent):
            at = command.payload - 4
            if command.operation in (0x14, 0x17):
                # Match the RD3 MSCAL and MSCNT encoding. The address and relocation stay intact.
                struct.pack_into("<I", output, at, read_word(mesh, at) & 0xff00ffff)
                break
            if at == start or command.operation & 0x60 != 0x60:
                continue  # Upload the two header vectors at the fixed VU address zero.
            address = command.immediate & 0x3ff
            relative = address - bank
            if not 0 <= relative <= RD2_VU_BANK_END:
                raise ValueError(f"RD2 VIF upload outside its strip bank at {at:#x}")
            translated = normal_target if address == normal else target + relative
            if not target <= translated <= target + RD3_VU_BANK_END:
                raise ValueError(f"RD2 VIF upload exceeds the RD3 strip bank at {at:#x}")
            struct.pack_into("<I", output, at, (read_word(mesh, at) & ~0x3ff) | translated)
    return bytes(output)


def split_triple_pass_strip(mesh, start, commands):
    bank, material, uv, count, normal, third, second, tail = struct.unpack_from("<8I", mesh, start + 4)
    if (material - bank, uv - bank, third - bank, second - bank, tail) != (2, 9, 6 * count + 15, 3 * count + 12, 0):
        return ()
    # The final GIF strip uses three qwords per vertex. Keep it below the
    # normal input stream at the end of an RD3 bank.
    if third - bank + 3 * count <= RD3_VU_BANK_END - count:
        return ()
    if normal != bank + RD2_VU_BANK_END - count:
        raise ValueError(f"Unexpected RD2 normal stream at {start:#x}")
    attributes = {uv, uv + 2, normal}
    parts = []
    # Two shared vertices preserve every triangle. The even step keeps their
    # winding and the attribute samples at the seam.
    for first in range(0, count - 2, RD3_TRIPLE_PASS_STRIP_SIZE - 2):
        size = min(RD3_TRIPLE_PASS_STRIP_SIZE, count - first)
        new_normal = bank + RD2_VU_BANK_END - size
        new_second, new_third = bank + 3 * size + 12, bank + 6 * size + 15
        addresses = {second - 3: new_second - 3, third - 3: new_third - 3}
        part = bytearray(struct.pack("<9I", STREAM_HEADER, bank, material, uv, size, new_normal,
                                     new_third, new_second, tail))
        for command in commands[1:]:
            if command.operation == 0x6e:
                continue
            word = read_word(mesh, command.payload - 4)
            data = mesh[command.payload:command.payload + command.size]
            address = command.immediate & 0x3ff
            if command.operation in (0x64, 0x74, 0x68, 0x78) and address in attributes:
                if command.count != count or command.size not in (count * 8, count * 12):
                    raise ValueError(f"Unexpected RD2 attribute upload at {command.payload - 4:#x}")
                stride = command.size // count
                data = data[first * stride:(first + size) * stride]
                word = (word & ~0xff03ff) | (size << 16) | (new_normal if address == normal else address)
            elif command.operation == 0x6c:
                word = (word & ~0x3ff) | addresses.get(address, address)
                data = bytearray(data)
                for offset in range(0, len(data), 16):
                    tag, regs = struct.unpack_from("<QQ", data, offset)
                    if regs == 0x512 and tag & 0x7fff == count:
                        struct.pack_into("<Q", data, offset, (tag & ~0x7fff) | size)
            part.extend(struct.pack("<I", word))
            part.extend(data)
        parts.append(part)
    return parts


def convert_mesh(mesh, model, sections, high_base, class_base, *, native_vu_banks):
    size, base, relocations = relocation_table(mesh)
    _, packets = mesh_packets(mesh)
    ranges = lod_packet_ranges(model, sections, base, size, packets)
    starts = [i for i in range(0, size - 35, 4) if read_word(mesh, i) == STREAM_HEADER]
    output = bytearray()
    offsets = {}
    refs = []
    counts = [len(group) for group in ranges]
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
            cursor = first
            for packet in starts[bisect_left(starts, first):bisect_left(starts, last)]:
                commands = []
                for command in vif_commands(mesh, packet, last):
                    commands.append(command)
                    if command.operation in (0x14, 0x17):
                        break
                else:
                    raise ValueError(f"Missing RD2 VU call in mesh packet at {packet:#x}")
                colors = [cmd for cmd in commands if cmd.operation == 0x6e]
                if len(colors) != 1:
                    raise ValueError(f"Expected one RD2 color upload in mesh packet at {packet:#x}")
                output.extend(mesh[cursor:packet])
                pieces = split_triple_pass_strip(mesh, packet, commands) if native_vu_banks else ()
                cursor = command.payload
                if pieces:
                    counts[lod] += len(pieces) - 1
                else:
                    # RD3's CPU-side mesh walker expects positions immediately after UVs.
                    color = colors[0]
                    pieces = [mesh[packet:color.payload - 4] + mesh[color.payload + color.size:cursor]]
                calls = []
                for piece in pieces:
                    output.extend(piece)
                    calls.append(len(output) - 4)
                if command.operation == 0x14:
                    offsets[cursor - 4] = calls
            output.extend(mesh[cursor:last])
            output.extend(bytes(align16(len(output)) - len(output)))
            pointer = high_base + output_first if lod == 0 else class_base + output_first - split
            refs.append((tag, pointer, len(output) - output_first))
    if offsets.keys() != relocations.keys() or not 0 < split < len(output):
        raise ValueError("RD2 mesh relocation coverage does not match the model")
    high_rows = {offset: kind for old, kind in relocations.items() for offset in offsets[old] if offset < split}
    class_rows = {offset - split: kind for old, kind in relocations.items() for offset in offsets[old] if offset >= split}
    high = serialize_relocations(output[:split], high_rows, high_base)
    low = serialize_relocations(output[split:], class_rows, class_base)
    return high, low, refs, counts


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


def convert_draw_transforms(model, base, relocations, sections):
    output = bytearray(model)
    entries = dict(relocations)
    converted = set()
    for start, end in sections:
        local_matrices = {}
        first, last = (p - base for p in struct.unpack_from("<2I", model, start + 0x24))
        if first != start + 0x30 or not first < last <= end or (last - first) % PART_BYTES:
            raise ValueError("Invalid RD2 part table")
        for part in range(first, last, PART_BYTES):
            if read_word(model, part) != 0:
                continue
            draw = read_word(model, part + 8) - base
            if draw in converted:
                continue
            converted.add(draw)
            if not first <= draw <= end - 0xa0:
                raise ValueError("Invalid RD2 draw transform location")
            marker = read_word(model, draw)
            if marker == 0x30000005:
                # RD2 lower LODs borrow the high-detail matrix and skip the local one.
                if (entries.get(draw) != 3 or entries.get(draw + 0x10) != 3
                        or read_word(model, draw + 0x10) != 0x20000000
                        or read_word(model, draw + 0x14) != base + draw + 0x70):
                    raise ValueError("Unexpected RD2 shared matrix chain")
                shared = read_word(model, draw + 4)
                local_matrices.setdefault(shared, base + draw + 0x20)
                del entries[draw]
                del entries[draw + 0x10]
            elif marker != 0x10000000 or read_word(model, draw + 0x10) != 0x10000005:
                raise ValueError("Unexpected RD2 inline matrix chain")
            if read_word(model, draw + 0x60) >> 24 != 0x11:
                raise ValueError("Missing RD2 transform chain terminator")
            index = read_word(model, draw + 0x5c)
            if not 1 <= index <= 5:
                raise ValueError(f"Unsupported RD2 draw matrix index {index}")
            # RD3 has an additional draw matrix slot before the five RD2 slots.
            struct.pack_into("<8I", output, draw, 0x10000000, 0, 0, 0, 0x10000005, 0, 0, 0x6c048000)
            struct.pack_into("<I", output, draw + 0x5c, index + 1)
        for offset, kind in entries.items():
            if kind != 3 or not start <= offset <= end - 16:
                continue
            tag, pointer, _, unpack = struct.unpack_from("<4I", model, offset)
            if tag != 0x30000005 or unpack != 0x6c048000 or not base <= pointer < base + start:
                continue
            # Composite parts also borrow matrices. Bind them to the same LOD as their geometry.
            if pointer not in local_matrices:
                raise ValueError(f"Missing local RD3 draw matrix for RD2 pointer {pointer:#x}")
            struct.pack_into("<I", output, offset + 4, local_matrices[pointer])
    return output, entries


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


def convert_model(model, mesh, target, *, native_vu_banks=True):
    _, base, relocations, sections = model_sections(model)
    _, target_base, _, target_sections = model_sections(target)
    lod_part_counts(target, target_sections, target_base)
    texture_base, high_base, class_base = struct.unpack_from("<3I", target, 0x2c)
    if not texture_base or not high_base or not class_base or high_base == class_base:
        raise ValueError("The RD3 template must provide separate class and high-detail files")
    high, low, refs, counts = convert_mesh(mesh, model, sections, high_base, class_base, native_vu_banks=native_vu_banks)
    if native_vu_banks:
        high, low = translate_vu_banks(high), translate_vu_banks(low)
    model, relocations = convert_draw_transforms(model, base, relocations, sections)
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
    if entries.get(0) == 3:
        headers = (0x10,)
    elif entries.get(0x10) == 3 and entries.get(8) == 0:
        # The class texture embeds a separate one-image container for LOD 4.
        far_texture = read_word(source, 8) - base
        if entries.get(far_texture) != 3:
            raise ValueError("Missing RD2 far-detail texture container")
        headers = (0x20, far_texture + 0x10)
    else:
        raise ValueError("Unsupported RD2 texture header")
    for header in headers:
        count, start = struct.unpack_from("<2I", source, header)
        start -= base
        if not header + 16 <= start < size or not 0 < count <= (size - start) // 0x170:
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
