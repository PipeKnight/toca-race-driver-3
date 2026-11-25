#!/usr/bin/env python3
"""Prepare Road America and optional A1-Ring layouts from local PS2 discs."""

import argparse
from bisect import bisect_right
from dataclasses import dataclass, field
from itertools import accumulate, pairwise
import math
from pathlib import Path
import re
import struct
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from BuildTrackCollisionOverlay import (
    BIGF_ENTRY, DONOR_DIRECTORY_HASH, JPAK_ENTRY, REFERENCE_DIRECTORY_HASH,
    SECTOR_SIZE, TRACK_BYTES, TRACK_SECTOR, encode_lzss,
    read_exact, verify_directory,
)
from BuildTrackGeometryOverlay import DMA_BYTES, DMA_SECTOR, make_overlay
from Ps2TrackRoute import PIT_STALL_COUNT


TRACK_CATALOG_SECTOR = 80673
TRACK_CATALOG_BYTES = 0x4800
EVENT_CATALOG_SECTOR = 81008
EVENT_CATALOG_BYTES = 0x1FE800
RAIN_TRACK_SECTOR = 510880
RAIN_TRACK_BYTES = 1363456
RAIN_DMA_SECTOR = 513312
RAIN_DMA_BYTES = 3568768
ROAD_AMERICA_RAIN_DONOR_SECTOR = 976987


@dataclass(frozen=True)
class TrackEntry:
    slot: str
    name: str
    km: str
    record: int
    pit_side: str = field(default="LEFT", kw_only=True)


@dataclass(frozen=True)
class Course(TrackEntry):
    donor_prefix: str
    route_package: tuple[int, int, int]  # Sector, BIGF entry count, expected .aid size.
    scene_package: tuple[int, int, int]  # Sector, BIGF entry count, expected col.col size.
    route_counts: tuple[int, int, int]  # Main, pit, and auxiliary route lengths.


ROAD_AMERICA = Course("tqa1", "Road America", "6.057", 19, "roa",
                      (805031, 50, 23884), (973763, 47, 573324), (387, 42, 50))
A1_RING = (
    Course("tqa2", "A1-Ring GP", "4.293", 34, "a11", (803257, 25, 20364), (805290, 36, 595956), (306, 79, 36)),
    Course("tqa3", "A1-Ring Short", "2.303", 35, "a12", (803292, 23, 10956), (808393, 35, 558396), (114, 79, 28)),
)


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
    struct.pack_into("<II", result, 4, len(members), base)
    for index, (name, data) in enumerate(members.items()):
        if start + len(data) > limit:
            raise ValueError("BIGF payload exceeds the original read extent")
        BIGF_ENTRY.pack_into(result, 0x24 + index * BIGF_ENTRY.size, name, len(data), start - base)
        result[start:start + len(data)] = data
        start += (len(data) + 31) & ~31
    return result


def track_catalog(original, courses=(ROAD_AMERICA,), *, existing=80):
    members, base = read_bigf(original, existing)
    index = re.compile(rb"(?mi)^HOFIndex[ \t]*=[ \t]*(\d+)[ \t]*\r?$")
    indices = {int(index.search(record)[1]) for record in members.values() if index.search(record)}
    if len(indices) != len(members):
        raise ValueError("Unexpected stock track record indices")
    for course in courses:
        member = f"{course.slot}.ini".encode("ascii")
        if course.record in indices or member in members:
            raise ValueError(f"The track or record ID for {course.name} is already in use")
        if course.pit_side not in ("LEFT", "RIGHT"):
            raise ValueError(f"Invalid pit side for {course.name}: {course.pit_side}")
        indices.add(course.record)
        members[member] = (
            f"[Info]\r\nTrackID = {course.slot}\r\nStage = CIRCUIT\r\nShortName = {course.name}\r\n"
            f"FullName = {course.name}\r\nPitSide = {course.pit_side}\r\n"
            f"HOFIndex = {course.record}\r\nLengthInKm = {course.km}"
        ).encode("ascii")
    base = max(base, (0x24 + len(members) * BIGF_ENTRY.size + 31) & ~31)
    return repack_bigf(original, members, base, max(base, 0x800), 0x4300)


def event_catalog(original, courses=(ROAD_AMERICA,), *, existing_rounds=9, add_oschersleben=True,
                  rainy_slots=(b"osc1", b"tqa1")):
    members, base = read_bigf(original, 204)
    event = members[b"rccuf.ini"]
    number = re.compile(rb"(?mi)^RacesNum([ \t]*=[ \t]*)(\d+)(?=[ \t]*\r?$)")
    total = number.search(event)
    template = re.search(rb"(?ms)^\[Race 1\]\r?\n(.*?)(?=\r?\n\[)", event)
    if not template or not total or int(total[2]) != existing_rounds:
        raise ValueError("Unexpected Clio Cup Free Race calendar")
    source = template[1].rstrip(b"\r\n")
    rounds = []
    stock = (b"osc1",) if add_oschersleben else ()
    tracks = stock + tuple(course.slot.encode("ascii") for course in courses)
    for number_value, track in enumerate(tracks, existing_rounds + 1):
        body, replacements = re.subn(rb"(?mi)^(TrackID[ \t]*=[ \t]*)hoc3", rb"\g<1>" + track, source)
        if replacements != 1:
            raise ValueError("Unexpected Clio Cup track reference")
        if track not in rainy_slots:
            body = re.sub(rb"(?mi)^Weather2[^\r\n]*\r?\n|^WeatherProb2[^\r\n]*\r?\n", b"", body)
            body = re.sub(rb"(?mi)^(WeatherProb1[ \t]*=[ \t]*)90", rb"\g<1>100", body)
        rounds.append(f"[Race {number_value}]\r\n".encode("ascii") + body)
    updated = number.sub(lambda match: b"RacesNum" + match[1] + str(existing_rounds + len(tracks)).encode("ascii"),
                         event, count=1).rstrip(b"\r\n\0")
    members[b"rccuf.ini"] = updated + b"\r\n\r\n" + b"\r\n\r\n".join(rounds) + b"\r\n"
    return repack_bigf(original, members, base, (base + 31) & ~31, len(original))


def read_donor_member(donor, package, member):
    sector, entries, size = package
    start = sector * SECTOR_SIZE
    magic, count, base = struct.unpack("<4sII", read_exact(donor, start, 12))
    if magic != b"BIGF" or count != entries or base < 0x24 + count * BIGF_ENTRY.size:
        raise ValueError(f"Unexpected donor BIGF at sector {sector}")
    directory = read_exact(donor, start + 0x24, count * BIGF_ENTRY.size)
    for name, length, relative in BIGF_ENTRY.iter_unpack(directory):
        if name.rstrip(b"\0") == member and length == size:
            return read_exact(donor, start + base + relative, length)
    raise ValueError(f"Missing or unexpected donor member {member!r}")


def expand_pit_stalls(lanes, rows, lap_length):
    stalls = [i for i, (_, argument, code, _) in enumerate(rows) if code == 3 and argument]
    if len(stalls) >= PIT_STALL_COUNT or not stalls:
        return None
    progress = tuple(accumulate((math.dist(a, b) for a, b in pairwise(lanes[3])), initial=0.))
    exit_gate = next((i for i in range(stalls[-1] + 1, len(rows)) if rows[i][2] == 15), len(rows) - 1)
    stop_length = 4.
    first = progress[stalls[0]]
    last = min(progress[stalls[-1]], progress[exit_gate] - stop_length)
    spacing = (last - first) / (PIT_STALL_COUNT - 1)
    if spacing < 6.:
        return None  # Preserve the source stall intervals when there is too little room for sixteen cars.

    markers = {}
    for tag in range(PIT_STALL_COUNT):
        start = first + spacing * tag
        for at, code, argument in ((start, 3, 1), (start + stop_length, 4, 0)):
            i = bisect_right(progress, at) - 1
            if i == len(progress) - 1:
                fraction = 0.
            else:
                gap = progress[i + 1] - progress[i]
                fraction = (at - progress[i]) / gap
                if fraction < 1e-6 and rows[i][2] not in (0, 3, 4):
                    fraction = min(0.05 / gap, 0.5)
            markers[i + fraction] = (tag, argument, code)

    coordinates = tuple([] for _ in lanes)
    events = []
    for key in sorted(markers.keys() | set(range(len(rows)))):
        i = int(key)
        fraction = key - i
        tag, argument, code, distance = rows[i]
        if key in markers:
            tag, argument, code = markers[key]
        elif i in stalls or code == 4:
            tag, argument, code = 255, 0, 0
        else:
            tag, argument = 255, 0
        if fraction:
            span = rows[i + 1][3] - distance
            if span < 0 and lap_length > 0:
                span += lap_length
            distance += span * fraction
            if lap_length > 0 and distance >= lap_length:
                distance -= lap_length
        events.append((tag, argument, code, distance))
        for source, target in zip(lanes, coordinates, strict=True):
            ax, az = source[i]
            if fraction:
                bx, bz = source[i + 1]
                ax += (bx - ax) * fraction
                az += (bz - az) * fraction
            target.append((ax, az))
    return coordinates, events


def convert_pit(lanes, rows, lap_length):
    left, right, stalls = lanes
    # RD2's extra lane leads to the stalls. RD3 also needs a driving line
    # between the entrance and exit corridor edges.
    driving = [((ax + bx) / 2, (az + bz) / 2) for (ax, az), (bx, bz) in zip(left, right, strict=True)]
    source = left, right, driving, stalls
    expanded = expand_pit_stalls(source, rows, lap_length)
    if expanded is not None:
        return expanded
    converted = tuple([] for _ in source)
    events = []
    for i, (tag, argument, code, distance) in enumerate(rows):
        for before, after in zip(source, converted, strict=True):
            after.append(before[i])
        if code != 3 or argument == 0:
            events.append((tag if code == 4 else 255, 0, code, distance))
            continue

        events.append((argument, 1, 3, distance))
        if i + 1 == len(rows):
            raise ValueError(f"Donor pit stall {argument} has no following station")
        if rows[i + 1][2] == 4:
            if rows[i + 1][0] != argument:
                raise ValueError(f"Donor pit stall {argument} has a mismatched end marker")
            continue
        gap = rows[i + 1][3] - distance
        if gap < 0 and lap_length > 0:
            gap += lap_length
        if not math.isfinite(gap) or gap <= 0:
            raise ValueError(f"Donor pit stall {argument} has no usable stop interval")
        length = min(6., gap / 2)
        fraction = length / gap
        end = distance + length
        if lap_length > 0 and end >= lap_length:
            end -= lap_length
        events.append((argument, 0, 4, end))
        for before, after in zip(source, converted, strict=True):
            ax, az = before[i]
            bx, bz = before[i + 1]
            after.append((ax + (bx - ax) * fraction, az + (bz - az) * fraction))
    return converted, events


def pit_distances(lanes, events, lap_length):
    finishes = [i for i, (_, _, code, _) in enumerate(events) if code == 6]
    if len(finishes) != 1 or not math.isfinite(lap_length) or lap_length <= 0:
        return events
    # Rebuild the distance axis together with its lap wrap. The RD2 odometer
    # can wrap at a different station from the physical pit finish gate.
    distances = tuple(accumulate((max(.001, math.dist(a, b)) for a, b in pairwise(lanes[2])), initial=0.))
    finish = distances[finishes[0]]
    return [(tag, argument, code, (distance - finish) % lap_length)
            for (tag, argument, code, _), distance in zip(events, distances, strict=True)]


def convert_route(source, counts=ROAD_AMERICA.route_counts):
    main_count, pit_count, aux_count = counts
    if source[:6] != bytes.fromhex("060d01200005") or struct.unpack_from("<H", source, 6)[0] != main_count:
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

    main, main_events, position = section(12, main_count, 5)
    if struct.unpack_from("<BBH", source, position) != (1, 3, pit_count):
        raise ValueError("Unexpected donor pit lane")
    pit, pit_events, position = section(position + 8, pit_count, 3)
    if struct.unpack_from("<BBH", source, position) != (2, 2, aux_count):
        raise ValueError("Unexpected donor auxiliary route")
    auxiliary, aux_events, _ = section(position + 8, aux_count, 2)
    starts = [i for i, row in enumerate(main_events) if row[2] == 12]
    ends = [i for i, row in enumerate(main_events) if row[2] == 13]
    if len(starts) != 1 or len(ends) != 1:
        raise ValueError("Donor main route requires exactly one start and end marker for the grid route")
    first, = starts
    last, = ends
    if (last - first) % len(main_events) + 1 != len(aux_events):
        raise ValueError("Donor route checkpoints disagree")
    lap_length = main_events[0][3]
    pit, pit_events = convert_pit(pit, pit_events, lap_length)
    pit_events = pit_distances(pit, pit_events, lap_length)
    sections = ((main, main_events, 0x1F, 1), (pit, pit_events, 0x27, 0),
                (auxiliary, aux_events, 3, 0))

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
            flags = (0, 1, 0, 0) if group == 2 else (code, tag & 255, argument, 0)
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


def repack_jpak(original, count, replacements, extent=None, *, compressor=encode_lzss):
    entries = list(jpak_entries(original, count))
    output = bytearray(original[:entries[0][0]])
    seen = set()
    for _, entry, name, row in entries:
        _, length, offset, expanded, _, _, flags, _ = row
        data = original[offset:offset + length]
        if name in replacements:
            seen.add(name)
            raw = bytes(replacements[name])
            data = compressor(raw) if flags & 1 else raw
            if len(data) >= len(raw):
                data = raw
            expanded = len(raw)
        output.extend(bytes(-len(output) % 64))
        struct.pack_into("<III", output, entry + 4, len(data), len(output), expanded)
        output.extend(data)
    if seen != set(replacements):
        raise ValueError("Reference JPAK is missing a required member")
    if extent is not None:
        if len(output) > extent:
            raise ValueError("Repacked JPAK exceeds the original package extent")
        output.extend(bytes(extent - len(output)))
    return output


def track_package(original, collision, route):
    for _, _, name, row in jpak_entries(original, 44):
        if name == b"osc1.big":
            _, length, offset, expanded, _, _, flags, _ = row
            stored = original[offset:offset + length]
            nested = unpack_lzss(stored, expanded) if flags & 1 else stored
            rebuilt = repack_jpak(nested, 163, {b"osc1.ail": route})
            return repack_jpak(original, 44, {b"col.col": collision, b"osc1.big": rebuilt}, len(original))
    raise ValueError("Missing nested reference track route")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference_disc", type=Path, help="extracted SLUS-21182 v1.02 disc directory")
    parser.add_argument("donor_disc", type=Path, help="mounted or extracted SLES-52638 v1.02 disc directory")
    parser.add_argument("output", type=Path, help="new directory for the generated add-on")
    parser.add_argument("--include-a1-ring", action="store_true", help="add separate A1-Ring GP and Short slots")
    args = parser.parse_args()
    try:
        verify_directory(args.reference_disc / "RDH.DIR", REFERENCE_DIRECTORY_HASH)
        verify_directory(args.donor_disc / "RD2.DIR", DONOR_DIRECTORY_HASH)
        if args.output.exists():
            raise ValueError("Choose a new add-on output directory")
        courses = (ROAD_AMERICA, *A1_RING) if args.include_a1_ring else (ROAD_AMERICA,)
        with (args.reference_disc / "RDH_1.HUG").open("rb") as reference, \
             (args.donor_disc / "RD2_1.HUG").open("rb") as donor, tempfile.TemporaryDirectory(dir=args.output.parent) as stage:
            output = Path(stage)
            tracks = track_catalog(read_exact(reference, TRACK_CATALOG_SECTOR * SECTOR_SIZE, TRACK_CATALOG_BYTES), courses)
            events = event_catalog(read_exact(reference, EVENT_CATALOG_SECTOR * SECTOR_SIZE, EVENT_CATALOG_BYTES), courses)
            (output / "tracks.big").write_bytes(tracks)
            (output / "events.big").write_bytes(events)
            original_track = read_exact(reference, TRACK_SECTOR * SECTOR_SIZE, TRACK_BYTES)
            original_dma = read_exact(reference, DMA_SECTOR * SECTOR_SIZE, DMA_BYTES)
            for course in courses:
                folder = output if course == ROAD_AMERICA else output / course.slot
                folder.mkdir(exist_ok=True)
                collision = read_donor_member(donor, course.scene_package, b"col.col")
                route = read_donor_member(donor, course.route_package, f"{course.donor_prefix}.aid".encode("ascii"))
                route = convert_route(route, course.route_counts)
                track = track_package(original_track, collision, route)
                scene_sector, scene_entries, _ = course.scene_package
                geometry, _ = make_overlay(original_dma, donor, donor_sector=scene_sector, donor_prefix=course.donor_prefix,
                                           donor_members_count=scene_entries)
                (folder / "TRACK.JPK").write_bytes(track)
                (folder / "DMA1.JPK").write_bytes(geometry)
                if course == ROAD_AMERICA:
                    rain = output / "rain"
                    rain.mkdir()
                    rain_track = read_exact(reference, RAIN_TRACK_SECTOR * SECTOR_SIZE, RAIN_TRACK_BYTES)
                    rain_dma = read_exact(reference, RAIN_DMA_SECTOR * SECTOR_SIZE, RAIN_DMA_BYTES)
                    rain_geometry, _ = make_overlay(rain_dma, donor, donor_sector=ROAD_AMERICA_RAIN_DONOR_SECTOR,
                                                   donor_members_count=scene_entries, reference_members=("sky.dma",))
                    (rain / "TRACK.JPK").write_bytes(track_package(rain_track, collision, route))
                    (rain / "DMA1.JPK").write_bytes(rain_geometry)
            output.rename(args.output)
    except (OSError, ValueError, IndexError, KeyError, StopIteration, struct.error) as error:
        parser.exit(1, f"Road America setup failed: {error}\n")
    print(f"Road America add-on prepared at {args.output}")


if __name__ == "__main__":
    main()
