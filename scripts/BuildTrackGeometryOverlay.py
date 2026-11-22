#!/usr/bin/env python3
"""Build a Road America geometry overlay for the local QA Circuit experiment."""

import argparse
from dataclasses import dataclass
import math
from pathlib import Path
import struct
import sys

# Bring the sibling script into scope under the Windows embedded Python runtime.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from BuildTrackCollisionOverlay import (
    BIGF_ENTRY,
    DONOR_DIRECTORY_HASH,
    JPAK_ENTRY,
    REFERENCE_DIRECTORY_HASH,
    SECTOR_SIZE,
    encode_lzss,
    read_exact,
    verify_directory,
)


DMA_SECTOR = 519440
DMA_BYTES = 3590336
DONOR_SECTOR = 973763
WORD = struct.Struct("<I")
VERTEX = struct.Struct("<3f")
RELOCATION = struct.Struct("<II")
FOOTER = struct.Struct("<III")
TARGET_NODE_BYTES = 0x70
COMMANDS_WITHOUT_PAYLOAD = {0, 2, 3, 4, 5, 6, 7, 0x10, 0x11, 0x13, 0x14, 0x15, 0x17}


def read_word(data, offset):
    return WORD.unpack_from(data, offset)[0]


@dataclass(frozen=True)
class VifCommand:
    operation: int
    immediate: int
    count: int
    payload: int
    size: int


def vif_commands(source, offset, end):
    read_cycle = write_cycle = 1
    while offset < end:
        if end - offset < WORD.size:
            raise ValueError("Truncated VIF command")
        command = read_word(source, offset)
        offset += WORD.size
        operation = (command >> 24) & 0x7F
        immediate = command & 0xFFFF
        count = ((command >> 16) & 255) or 256
        if operation == 1:
            write_cycle = (immediate >> 8) or 256
            read_cycle = (immediate & 255) if immediate else write_cycle
            amount = 0
        elif operation == 0x20:
            amount = 4
        elif operation in (0x30, 0x31):
            amount = 16
        elif operation == 0x4A:
            amount = count * 8
        elif operation in (0x50, 0x51):
            amount = (immediate or 65536) * 16
        elif (operation & 0x60) == 0x60:
            elements = count
            if write_cycle > read_cycle:
                elements = count // write_cycle * read_cycle + min(count % write_cycle, read_cycle)
            components = ((operation >> 2) & 3) + 1
            bits = 16 if (operation & 15) == 15 else components * (32, 16, 8, 5)[operation & 3]
            amount = (elements * bits + 31) // 32 * 4
        elif operation in COMMANDS_WITHOUT_PAYLOAD:
            amount = 0
        else:
            raise ValueError(f"Unknown VIF command {operation:#x}")
        if offset + amount > end:
            raise ValueError("VIF command exceeds the packet extent")
        yield VifCommand(operation, immediate, count, offset, amount)
        offset += amount


def vertex_bounds(source, node, payload_bytes, base):
    tag, address = RELOCATION.unpack_from(source, node)
    offset = address - base
    end = offset + (tag & 0xFFFF) * 16
    if (tag >> 28) & 7 != 3 or not 0 <= offset <= end <= payload_bytes:
        raise ValueError("Invalid scene leaf DMA packet")
    if offset == end:
        return None  # A zero-length REF has no vertices to include in its parent's bounds.
    low = [math.inf] * 3
    high = [-math.inf] * 3
    vertices = 0
    for command in vif_commands(source, offset, end):
        if command.operation not in (0x68, 0x78):
            continue
        for point in VERTEX.iter_unpack(source[command.payload:command.payload + command.size]):
            if not all(math.isfinite(value) and abs(value) <= 100000 for value in point):
                raise ValueError("Invalid vertex coordinate in scene leaf")
            for axis, value in enumerate(point):
                low[axis] = min(low[axis], value)
                high[axis] = max(high[axis], value)
            vertices += 1
    if vertices < 3:
        raise ValueError("Scene leaf contains fewer than three position vertices")
    return tuple(low + high)


def convert_scene(source):
    count, size, base = FOOTER.unpack_from(source, len(source) - FOOTER.size)
    if size + RELOCATION.size * count + FOOTER.size != len(source) or size % 16:
        raise ValueError("Invalid donor DMA envelope")
    relocations = dict(RELOCATION.iter_unpack(source[size:-FOOTER.size]))
    if len(relocations) != count:
        raise ValueError("Duplicate donor DMA relocation")

    roots = []
    head = read_word(source, 0)
    while head:
        offset = head - base
        if head in roots or not 0 <= offset <= size - 32 or relocations.get(offset + 4) != 0:
            raise ValueError("Invalid donor display-list root chain")
        roots.append(head)
        head = read_word(source, offset + 24)
    if not roots:
        raise ValueError("Missing donor display-list root")

    nodes = {}
    children_by_node = {}
    bounds_by_node = {}
    pending = [read_word(source, head - base + 4) for head in roots]
    while pending:
        address = pending.pop()
        if address in nodes:
            continue
        offset = address - base
        if not 0 <= offset <= size - 64 or relocations.get(offset) != 3 or offset % 16 != 4:
            raise ValueError(f"Invalid donor scene node {address:#x}")
        children = []
        for field in range(offset + 0x28, offset + 0x38, 4):
            child = read_word(source, field)
            if child:
                if relocations.get(field) != 0:
                    raise ValueError("Non-relocatable donor scene child")
                children.append(child)
        leaf = read_word(source, offset + 0x38)
        if leaf not in (0, 1) or bool(leaf) == bool(children):
            raise ValueError(f"Invalid donor scene node flags at {address:#x}")
        nodes[address] = size + TARGET_NODE_BYTES * len(nodes)
        children_by_node[address] = children
        pending.extend(children)
        if leaf:
            bounds_by_node[address] = vertex_bounds(source, offset, size, base)

    visiting = set()

    def bounds_of(address):
        if address not in bounds_by_node:
            if address in visiting:
                raise ValueError("Cycle in donor scene tree")
            visiting.add(address)
            boxes = tuple(box for child in children_by_node[address] if (box := bounds_of(child)) is not None)
            if boxes:
                low = tuple(min(box[axis] for box in boxes) for axis in range(3))
                high = tuple(max(box[axis] for box in boxes) for axis in range(3, 6))
                bounds_by_node[address] = low + high
            else:
                bounds_by_node[address] = None
            visiting.remove(address)
        return bounds_by_node[address]

    payload = bytearray(source[:size])
    added = []
    for address, new_start in nodes.items():
        old_start = address - base
        node = bytearray(TARGET_NODE_BYTES)
        # The newer node stores two bounding vectors ahead of the old packet metadata.
        node[:0x18] = source[old_start:old_start + 0x18]
        node[0x40:0x68] = source[old_start + 0x18:old_start + 0x40]
        bounds = bounds_of(address)
        if bounds is not None:
            VERTEX.pack_into(node, 0x20, *bounds[:3])
            VERTEX.pack_into(node, 0x30, *bounds[3:])
        for relative in range(0, 0x40, 4):
            kind = relocations.get(old_start + relative)
            if kind is None:
                continue
            target = relative if relative < 0x18 else relative + 0x28
            if 0x28 <= relative < 0x38:
                child = read_word(source, old_start + relative)
                if child:
                    WORD.pack_into(node, target, base + nodes[child])
            added.append(RELOCATION.pack(new_start + target, kind))
        payload.extend(node)

    for head in roots:
        position = head - base + 4
        WORD.pack_into(payload, position, base + nodes[read_word(source, position)])
    return (bytes(payload) + source[size:-FOOTER.size] + b"".join(added)
            + FOOTER.pack(count + len(added), len(payload), base)), len(nodes)


def make_overlay(original, donor_archive, *, donor_sector=DONOR_SECTOR, donor_prefix="roa",
                 donor_members_count=47, reference_members=()):
    magic, _, count = struct.unpack_from("<4sII", original)
    if magic != b"JPAK" or count != 14:
        raise ValueError("Unexpected reference DMA1.JPK directory")
    index_end = 32 + count * JPAK_ENTRY.size
    entries = list(JPAK_ENTRY.iter_unpack(original[32:index_end]))
    data_start = min(entry[2] for entry in entries)
    if not index_end <= data_start <= len(original):
        raise ValueError("Invalid reference DMA1.JPK directory bounds")

    start = donor_sector * SECTOR_SIZE
    magic, donor_count, data_base = struct.unpack("<4sII", read_exact(donor_archive, start, 12))
    available = donor_archive.seek(0, 2) - start - data_base
    if (magic != b"BIGF" or donor_count != donor_members_count
            or data_base < 36 + donor_count * BIGF_ENTRY.size or available <= 0):
        raise ValueError(f"Unexpected {donor_prefix} BIGF directory")
    bigf = read_exact(donor_archive, start + 36, donor_count * BIGF_ENTRY.size)
    donor_members = {name.split(b"\0", 1)[0].decode("ascii").lower(): (length, relative)
                     for name, length, relative in BIGF_ENTRY.iter_unpack(bigf)}
    names = {"wal1": "wal", "fob1": "fob"}
    output = bytearray(original[:data_start])
    nodes = 0
    for index, fields in enumerate(entries):
        name_offset, stored, offset, expanded, _, _, flags, _ = fields
        if not index_end <= name_offset < data_start or not flags & 1:
            raise ValueError("Unexpected reference DMA1.JPK member")
        member = original[name_offset:data_start].split(b"\0", 1)[0].decode("ascii")
        if member in reference_members:
            if not data_start <= offset <= len(original) - stored:
                raise ValueError(f"Invalid reference geometry member {member!r}")
            packed = original[offset:offset + stored]
        else:
            stem = Path(member).stem
            donor_name = f"{donor_prefix}_{names.get(stem, stem)}.dma"
            if donor_name not in donor_members:
                raise ValueError(f"Donor geometry member {donor_name!r} is missing")
            length, relative = donor_members[donor_name]
            if not 0 < length <= available - relative:
                raise ValueError(f"Donor geometry member {donor_name!r} exceeds the archive")
            source = read_exact(donor_archive, start + data_base + relative, length)
            converted, converted_count = convert_scene(source)
            nodes += converted_count
            expanded = len(converted)
            packed = encode_lzss(converted)
        output.extend(bytes(-len(output) % 64))
        struct.pack_into("<III", output, 36 + index * JPAK_ENTRY.size, len(packed), len(output), expanded)
        output.extend(packed)
    if len(output) > len(original):
        raise ValueError("Converted geometry exceeds the reference DMA1.JPK archive extent")
    output.extend(bytes(len(original) - len(output)))
    return output, nodes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference_disc", type=Path, help="extracted SLUS-21182 v1.02 disc directory")
    parser.add_argument("donor_disc", type=Path, help="mounted or extracted SLES-52638 v1.02 disc directory")
    parser.add_argument("output", type=Path, help="new local DMA1.JPK overlay file")
    args = parser.parse_args()
    try:
        verify_directory(args.reference_disc / "RDH.DIR", REFERENCE_DIRECTORY_HASH)
        verify_directory(args.donor_disc / "RD2.DIR", DONOR_DIRECTORY_HASH)
        with (args.reference_disc / "RDH_1.HUG").open("rb") as stream:
            original = read_exact(stream, DMA_SECTOR * SECTOR_SIZE, DMA_BYTES)
        with (args.donor_disc / "RD2_1.HUG").open("rb") as stream:
            output, nodes = make_overlay(original, stream)
        with args.output.open("xb") as stream:
            stream.write(output)
    except (OSError, ValueError, struct.error, RecursionError) as error:
        parser.exit(1, f"Geometry overlay failed: {error}\n")
    print(f"Wrote {len(output)} bytes with {nodes} rebuilt scene nodes to {args.output}")


if __name__ == "__main__":
    main()
