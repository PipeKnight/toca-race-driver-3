#!/usr/bin/env python3
"""Build a Road America collision overlay for the local QA Circuit experiment."""

import argparse
from array import array
from collections import defaultdict, deque
import hashlib
import math
from pathlib import Path
import struct


SECTOR_SIZE = 2048
TRACK_SECTOR = 516992
TRACK_BYTES = 1378240
DONOR_SECTOR = 973763
REFERENCE_DIRECTORY_HASH = "10e4cc05d7d83b419eeb812ed8f0096bc40fe4932fa41d0b4fd88fba61704871"
DONOR_DIRECTORY_HASH = "44d9757ba1d4bef1765cb8247c1c6585320e1a413b0af13979e28d05689915a2"
JPAK_ENTRY = struct.Struct("<8I")
BIGF_ENTRY = struct.Struct("<16sII")


def read_exact(stream, offset, length):
    stream.seek(offset)
    data = stream.read(length)
    if len(data) != length:
        raise ValueError(f"Short archive read at byte {offset:#x}")
    return data


def verify_directory(path, expected_hash):
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
        raise ValueError(f"Unverified disc directory {path}")


def donor_collision(archive):
    with archive.open("rb") as stream:
        start = DONOR_SECTOR * SECTOR_SIZE
        magic, count, data_offset = struct.unpack("<4sII", read_exact(stream, start, 12))
        if magic != b"BIGF" or count != 47 or data_offset < 36 + count * BIGF_ENTRY.size:
            raise ValueError("Unexpected Road America BIGF directory")
        directory = read_exact(stream, start + 36, count * BIGF_ENTRY.size)
        entries = [(size, offset) for name, size, offset in BIGF_ENTRY.iter_unpack(directory)
                   if name.split(b"\0", 1)[0].lower() == b"col.col"]
        if len(entries) != 1 or entries[0][0] != 573324:
            raise ValueError("Unexpected Road America collision entry")
        size, offset = entries[0]
        return read_exact(stream, start + data_offset + offset, size)


def collision_counts(data):
    bounds = struct.unpack_from("<6f", data)
    grid_bytes, triangles, vertices, reserved = struct.unpack_from("<4I", data, 24)
    index_offset = 40 + vertices * 8 + triangles * 4
    grid_offset = index_offset + triangles * 6
    if (not vertices or not triangles or reserved
            or not all(math.isfinite(value) for value in bounds)
            or not all(lower < upper for lower, upper in zip(bounds[:3], bounds[3:]))
            or grid_offset + grid_bytes > len(data)):
        raise ValueError("Invalid collision dimensions")
    indices = memoryview(data)[index_offset:grid_offset]
    if any(index >= vertices for (index,) in struct.iter_unpack("<H", indices)):
        raise ValueError("Collision triangle index falls outside the vertex array")
    return vertices, triangles


def encode_lzss(data):
    """Encode the 4 KiB ring-buffer format used by compressed JPAK members."""
    positions = defaultdict(lambda: deque(maxlen=32))
    packed = bytearray()
    cursor = 0
    while cursor < len(data):
        flags = len(packed)
        packed.append(0)
        for bit in range(8):
            remaining = min(18, len(data) - cursor)
            if not remaining:
                break
            match_length = 0
            match_position = 0
            if remaining >= 3:
                for previous in reversed(positions[data[cursor:cursor + 3]]):
                    if cursor - previous > 4096:
                        break
                    length = 3
                    while length < remaining and data[cursor + length] == data[previous + length]:
                        length += 1
                    if length > match_length:
                        match_length, match_position = length, previous
                        if length == remaining:
                            break
            if match_length:
                ring_position = (match_position + 0xFEE) & 0xFFF
                packed.extend((ring_position & 0xFF, (ring_position >> 4 & 0xF0) | (match_length - 3)))
            else:
                packed[flags] |= 1 << bit
                packed.append(data[cursor])
                match_length = 1
            for position in range(cursor, min(cursor + match_length, len(data) - 2)):
                positions[data[position:position + 3]].append(position)
            cursor += match_length
    return packed


def encode_lzss_compact(data):
    """Choose a smaller encoding when the normal encoding does not fit a JPAK slot."""
    size = len(data)
    lengths = bytearray(size)
    ring_positions = array("H", [0]) * size
    history = defaultdict(deque)

    for position in range(size - 2):
        expired = position - 4097
        if expired >= 0:
            expired_key = data[expired:expired + 3]
            history[expired_key].popleft()
            if not history[expired_key]:
                del history[expired_key]
        previous_positions = history[data[position:position + 3]]
        limit = min(18, size - position)
        for previous in reversed(previous_positions):
            length = 3
            while length < limit and data[position + length] == data[previous + length]:
                length += 1
            if length > lengths[position]:
                lengths[position] = length
                ring_positions[position] = (previous + 0xFEE) & 0xFFF
            if length == limit:
                break
        previous_positions.append(position)

    # Costs depend on the next slot in the flag byte and at most 18 future source bytes.
    window = 19
    costs = [[0] * window for _ in range(8)]
    choices = [bytearray(size) for _ in range(8)]
    for position in range(size - 1, -1, -1):
        for slot, cost in enumerate(costs):
            next_cost = costs[(slot + 1) % 8]
            best = 1 + next_cost[(position + 1) % window]
            for length in range(3, lengths[position] + 1):
                candidate = 2 + next_cost[(position + length) % window]
                if candidate < best:
                    best = candidate
                    choices[slot][position] = length
            cost[position % window] = best + (slot == 0)

    packed = bytearray()
    position = 0
    while position < size:
        flags = len(packed)
        packed.append(0)
        for slot in range(8):
            if position == size:
                break
            match = choices[slot][position]
            if match:
                ring_position = ring_positions[position]
                packed.extend((ring_position & 0xFF, (ring_position >> 4 & 0xF0) | (match - 3)))
                position += match
            else:
                packed[flags] |= 1 << slot
                packed.append(data[position])
                position += 1
    return packed


def replace_collision(package, collision):
    magic, _, count = struct.unpack_from("<4sII", package)
    if magic != b"JPAK" or count != 44:
        raise ValueError("Unexpected reference TRACK.JPK directory")
    names_start = 32 + count * JPAK_ENTRY.size
    for entry in range(32, names_start, JPAK_ENTRY.size):
        name, stored, offset, expanded, _, _, flags, _ = JPAK_ENTRY.unpack_from(package, entry)
        if not names_start <= name < offset <= len(package) or offset + stored > len(package):
            raise ValueError("Invalid JPAK entry bounds")
        if package[name:name + 8] != b"col.col\0":
            continue
        if not flags & 1 or stored == expanded:
            raise ValueError("Expected a compressed reference collision entry")
        packed = encode_lzss(collision)
        if len(packed) > stored:
            raise ValueError(f"Compressed collision exceeds its {stored}-byte JPAK span")
        result = bytearray(package)
        struct.pack_into("<III", result, entry + 4, len(packed), offset, len(collision))
        result[offset:offset + stored] = packed + bytes(stored - len(packed))
        return result
    raise ValueError("Reference JPAK has no col.col member")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference_disc", type=Path, help="extracted SLUS-21182 v1.02 disc directory")
    parser.add_argument("donor_disc", type=Path, help="mounted or extracted SLES-52638 v1.02 disc directory")
    parser.add_argument("output", type=Path, help="new local TRACK.JPK overlay file")
    args = parser.parse_args()
    try:
        verify_directory(args.reference_disc / "RDH.DIR", REFERENCE_DIRECTORY_HASH)
        verify_directory(args.donor_disc / "RD2.DIR", DONOR_DIRECTORY_HASH)
        collision = donor_collision(args.donor_disc / "RD2_1.HUG")
        vertices, triangles = collision_counts(collision)
        with (args.reference_disc / "RDH_1.HUG").open("rb") as stream:
            package = read_exact(stream, TRACK_SECTOR * SECTOR_SIZE, TRACK_BYTES)
        overlay = replace_collision(package, collision)
        with args.output.open("xb") as stream:
            stream.write(overlay)
    except (OSError, ValueError, struct.error) as error:
        parser.exit(1, f"Collision overlay failed: {error}\n")
    print(f"Wrote {len(overlay)} bytes with {vertices} vertices and {triangles} triangles to {args.output}")


if __name__ == "__main__":
    main()
