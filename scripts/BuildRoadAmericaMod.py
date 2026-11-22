#!/usr/bin/env python3
"""Prepare the Road America add-on from local Race Driver 2 and 3 PS2 discs."""

import argparse
import math
from pathlib import Path
import re
import struct
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from BuildTrackCollisionOverlay import (
    BIGF_ENTRY, DONOR_DIRECTORY_HASH, JPAK_ENTRY, REFERENCE_DIRECTORY_HASH,
    SECTOR_SIZE, TRACK_BYTES, TRACK_SECTOR, donor_collision, encode_lzss,
    read_exact, verify_directory,
)
from BuildTrackGeometryOverlay import DMA_BYTES, DMA_SECTOR, make_overlay


TRACK_CATALOG_SECTOR = 80673
TRACK_CATALOG_BYTES = 0x4800
EVENT_CATALOG_SECTOR = 81008
EVENT_CATALOG_BYTES = 0x1FE800
DONOR_AI_SECTOR = 805031
ROAD_AMERICA_RECORD = 19


def read_bigf(blob, count):
    signature, entries, base = struct.unpack_from("<4sII", blob)
    end = 0x24 + count * BIGF_ENTRY.size
    if signature != b"BIGF" or entries != count or not end <= base <= len(blob):
        raise ValueError("Unexpected BIGF archive directory")
    members = {}
    for name, length, relative in BIGF_ENTRY.iter_unpack(blob[0x24:end]):
        key = name.rstrip(b"\0")
        start = base + relative
        if key in members or start + length > len(blob):
            raise ValueError("Invalid BIGF archive member")
        members[key] = blob[start:start + length]
    return members, base


def repack_bigf(original, members, base, start, limit):
    if 0x24 + len(members) * BIGF_ENTRY.size > base or not base <= start <= limit <= len(original):
        raise ValueError("BIGF archive layout does not fit")
    result = bytearray(original)
    struct.pack_into("<I", result, 4, len(members))
    for index, (name, data) in enumerate(members.items()):
        if start + len(data) > limit:
            raise ValueError("BIGF payload exceeds the original read extent")
        BIGF_ENTRY.pack_into(result, 0x24 + index * BIGF_ENTRY.size, name, len(data), start - base)
        result[start:start + len(data)] = data
        start += (len(data) + 31) & ~31
    return result


def track_catalog(original):
    members, base = read_bigf(original, 80)
    index = re.compile(rb"(?mi)^HOFIndex[ \t]*=[ \t]*(\d+)[ \t]*\r?$")
    indices = {int(index.search(record)[1]) for record in members.values() if index.search(record)}
    if len(indices) != len(members) or ROAD_AMERICA_RECORD in indices or b"tqa1.ini" in members:
        raise ValueError("The Road America track or record ID is already in use")
    members[b"tqa1.ini"] = (
        b"[Info]\r\nTrackID = tqa1\r\nStage = CIRCUIT\r\nShortName = Road America\r\n"
        b"FullName = Road America\r\nPitSide = LEFT\r\nHOFIndex = "
        + str(ROAD_AMERICA_RECORD).encode("ascii") + b"\r\nLengthInKm = 6.057"
    )
    return repack_bigf(original, members, base, 0x800, 0x4300)


def event_catalog(original):
    members, base = read_bigf(original, 204)
    event = members[b"rccuf.ini"]
    number = re.compile(rb"(?mi)^RacesNum([ \t]*=[ \t]*)9(?=[ \t]*\r?$)")
    template = re.search(rb"(?ms)^\[Race 1\]\r?\n(.*?)(?=\r?\n\[)", event)
    if not template or not number.search(event):
        raise ValueError("Unexpected Clio Cup Free Race calendar")
    source = template[1].rstrip(b"\r\n")
    rounds = []
    for number_value, track in ((10, b"osc1"), (11, b"tqa1")):
        body, replacements = re.subn(rb"(?mi)^(TrackID[ \t]*=[ \t]*)hoc3", rb"\g<1>" + track, source)
        if replacements != 1:
            raise ValueError("Unexpected Clio Cup track reference")
        rounds.append(f"[Race {number_value}]\r\n".encode("ascii") + body)
    updated = number.sub(rb"RacesNum\g<1>11", event, count=1).rstrip(b"\r\n\0")
    members[b"rccuf.ini"] = updated + b"\r\n\r\n" + b"\r\n\r\n".join(rounds) + b"\r\n"
    return repack_bigf(original, members, base, (base + 31) & ~31, len(original))


def read_route(donor):
    start = DONOR_AI_SECTOR * SECTOR_SIZE
    magic, count, base = struct.unpack("<4sII", read_exact(donor, start, 12))
    if magic != b"BIGF" or count != 50 or base < 0x24 + count * BIGF_ENTRY.size:
        raise ValueError("Unexpected donor AI package")
    directory = read_exact(donor, start + 0x24, count * BIGF_ENTRY.size)
    for name, length, relative in BIGF_ENTRY.iter_unpack(directory):
        if name.rstrip(b"\0") == b"roa.aid" and length == 23884:
            return read_exact(donor, start + base + relative, length)
    raise ValueError("Missing donor route")


def convert_route(source):
    if source[:8] != bytes.fromhex("060d012000058301"):
        raise ValueError("Unexpected donor route header")

    def section(offset, size, lanes):
        coordinates = []
        for _ in range(lanes):
            end = offset + size * 8
            coordinates.append(tuple(struct.iter_unpack("<2f", source[offset:end])))
            offset = end
        end = offset + size * 8
        rows = tuple(struct.iter_unpack("<HBBf", source[offset:end]))
        if len(rows) != size or any(len(line) != size for line in coordinates):
            raise ValueError("Truncated donor route section")
        return coordinates, rows, end

    main, main_events, position = section(12, 387, 5)
    if struct.unpack_from("<BBH", source, position) != (1, 3, 42):
        raise ValueError("Unexpected donor pit lane")
    pit, pit_events, position = section(position + 8, 42, 3)
    if struct.unpack_from("<BBH", source, position) != (2, 2, 50):
        raise ValueError("Unexpected donor auxiliary route")
    auxiliary, aux_events, _ = section(position + 8, 50, 2)
    sections = ((main, main_events, 0x1F, 1), (pit + [pit[2]], pit_events, 0x27, 0),
                (auxiliary, aux_events, 3, 0))
    first = next(i for i, row in enumerate(main_events) if row[2] == 12)
    last = next(i for i, row in enumerate(main_events) if row[2] == 13)
    if (last - first) % len(main_events) + 1 != len(aux_events):
        raise ValueError("Donor route checkpoints disagree")

    header = bytearray(b"AILD" + struct.pack("<I", 9))
    events = bytearray()
    lanes = bytearray()
    for group, (coordinates, rows, mask, loop) in enumerate(sections):
        header.extend(struct.pack("<HBB", len(rows), mask, loop))
        for i, (tag, argument, code, distance) in enumerate(rows):
            x, z = coordinates[0][i]
            right_x, right_z = coordinates[1][i]
            dx, dz = right_x - x, right_z - z
            width = math.hypot(dx, dz)
            if width < 0.01:
                previous = coordinates[0][max(0, i - 1)]
                upcoming = coordinates[0][min(len(rows) - 1, i + 1)]
                dx, dz = upcoming[1] - previous[1], previous[0] - upcoming[0]
                width = math.hypot(dx, dz)
            if not width or not math.isfinite(width) or not math.isfinite(distance):
                raise ValueError("Invalid donor route coordinate")
            if group == 0:
                flags = (code, tag & 255, argument, 0)
            elif group == 1:
                pit_marker = code == 3 and argument != 0
                flags = (code, argument if pit_marker else 255, int(pit_marker), 0)
            else:
                flags = (0, 1, 0, 0)
            events.extend(struct.pack("<3f4B", dx / width, dz / width, distance, *flags))
        for line in coordinates:
            for point in line:
                lanes.extend(struct.pack("<2f", *point))
    return header + events + lanes


def unpack_lzss(data, size):
    window = bytearray(4096)
    cursor = 0xFEE
    offset = 0
    result = bytearray()
    while len(result) < size:
        flags = data[offset]
        offset += 1
        for bit in range(8):
            if len(result) == size:
                break
            if flags & (1 << bit):
                values = (data[offset],)
                offset += 1
            else:
                low, high = data[offset:offset + 2]
                position = low | ((high & 0xF0) << 4)
                values = (window[(position + i) & 0xFFF] for i in range((high & 15) + 3))
                offset += 2
            for value in values:
                window[cursor] = value
                cursor = (cursor + 1) & 0xFFF
                result.append(value)
    if len(result) != size:
        raise ValueError("JPAK member exceeds its expanded length")
    return result


def jpak_entries(original, count):
    magic, _, entries = struct.unpack_from("<4sII", original)
    end = 32 + count * JPAK_ENTRY.size
    if magic != b"JPAK" or entries != count or end > len(original):
        raise ValueError("Unexpected JPAK directory")
    rows = list(JPAK_ENTRY.iter_unpack(original[32:end]))
    first_data = min(row[2] for row in rows)
    if not end <= first_data <= len(original):
        raise ValueError("Invalid JPAK directory bounds")
    for index, row in enumerate(rows):
        name, length, offset, _, _, _, _, _ = row
        if not end <= name < first_data or offset + length > len(original):
            raise ValueError("Invalid JPAK member bounds")
        label = bytes(original[name:first_data].split(b"\0", 1)[0])
        yield first_data, 32 + index * JPAK_ENTRY.size, label, row


def repack_jpak(original, count, replacements, extent=None):
    entries = list(jpak_entries(original, count))
    output = bytearray(original[:entries[0][0]])
    seen = set()
    for _, entry, name, row in entries:
        _, length, offset, expanded, _, _, flags, _ = row
        data = original[offset:offset + length]
        if name in replacements:
            seen.add(name)
            raw = bytes(replacements[name])
            data = encode_lzss(raw) if flags & 1 else raw
            expanded = len(raw)
        output.extend(bytes(-len(output) % 64))
        struct.pack_into("<III", output, entry + 4, len(data), len(output), expanded)
        output.extend(data)
    if seen != set(replacements):
        raise ValueError("Reference JPAK is missing a required member")
    if extent is not None:
        if len(output) > extent:
            raise ValueError("Repacked TRACK.JPK exceeds the original disc read extent")
        output.extend(bytes(extent - len(output)))
    return output


def track_package(original, collision, route):
    for _, _, name, row in jpak_entries(original, 44):
        if name == b"osc1.big":
            _, length, offset, expanded, _, _, flags, _ = row
            stored = original[offset:offset + length]
            nested = unpack_lzss(stored, expanded) if flags & 1 else stored
            rebuilt = repack_jpak(nested, 163, {b"osc1.ail": route})
            return repack_jpak(original, 44, {b"col.col": collision, b"osc1.big": rebuilt}, TRACK_BYTES)
    raise ValueError("Missing nested reference track route")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference_disc", type=Path, help="extracted SLUS-21182 v1.02 disc directory")
    parser.add_argument("donor_disc", type=Path, help="mounted or extracted SLES-52638 v1.02 disc directory")
    parser.add_argument("output", type=Path, help="new directory for the generated add-on")
    args = parser.parse_args()
    try:
        verify_directory(args.reference_disc / "RDH.DIR", REFERENCE_DIRECTORY_HASH)
        verify_directory(args.donor_disc / "RD2.DIR", DONOR_DIRECTORY_HASH)
        if args.output.exists():
            raise ValueError("Choose a new add-on output directory")
        with (args.reference_disc / "RDH_1.HUG").open("rb") as reference, \
             (args.donor_disc / "RD2_1.HUG").open("rb") as donor:
            tracks = track_catalog(read_exact(reference, TRACK_CATALOG_SECTOR * SECTOR_SIZE, TRACK_CATALOG_BYTES))
            events = event_catalog(read_exact(reference, EVENT_CATALOG_SECTOR * SECTOR_SIZE, EVENT_CATALOG_BYTES))
            collision = donor_collision(args.donor_disc / "RD2_1.HUG")
            route = convert_route(read_route(donor))
            track = track_package(read_exact(reference, TRACK_SECTOR * SECTOR_SIZE, TRACK_BYTES), collision, route)
            geometry, _ = make_overlay(read_exact(reference, DMA_SECTOR * SECTOR_SIZE, DMA_BYTES), donor)
        with tempfile.TemporaryDirectory(dir=args.output.parent) as stage:
            for name, data in (("tracks.big", tracks), ("events.big", events), ("TRACK.JPK", track), ("DMA1.JPK", geometry)):
                (Path(stage) / name).write_bytes(data)
            Path(stage).rename(args.output)
    except (OSError, ValueError, IndexError, KeyError, StopIteration, struct.error) as error:
        parser.exit(1, f"Road America setup failed: {error}\n")
    print(f"Road America add-on prepared at {args.output}")


if __name__ == "__main__":
    main()
