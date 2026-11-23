"""Inspect and edit the AI lanes and lap markers of a PS2 AILD v9 route."""

import csv
from dataclasses import dataclass
from itertools import groupby
import math
from operator import itemgetter
import struct


MAGIC = b"AILD\x09\0\0\0"
SECTION = struct.Struct("<HBB")
EVENT = struct.Struct("<3f4B")
POINT = struct.Struct("<2f")
LABELS = ("main", "pit", "auxiliary")
FIELDS = ("section", "station", "normal_x", "normal_z", "distance_m", "code", "tag", "argument", "reserved")


@dataclass(frozen=True)
class Section:
    label: str
    mask: int
    loop: int
    events: tuple
    lanes: tuple

    @property
    def lane_ids(self):
        return [lane for lane in range(8) if self.mask & (1 << lane)]


def read_route(data):
    if not data.startswith(MAGIC) or len(data) < 20:
        raise ValueError("Expected an AILD version 9 route")
    headers = tuple(SECTION.iter_unpack(data[8:20]))
    if any(not count or not mask or loop not in (0, 1) for count, mask, loop in headers):
        raise ValueError("Invalid AILD section headers")
    event_at = 20
    point_at = event_at + EVENT.size * sum(count for count, _, _ in headers)
    if len(data) != point_at + POINT.size * sum(count * mask.bit_count() for count, mask, _ in headers):
        raise ValueError("AILD length does not match its route section sizes")
    sections = []
    for label, (count, mask, loop) in zip(LABELS, headers):
        end = event_at + count * EVENT.size
        events = tuple(EVENT.iter_unpack(data[event_at:end]))
        event_at = end
        lanes = []
        for _ in range(mask.bit_count()):
            end = point_at + count * POINT.size
            lanes.append(tuple(POINT.iter_unpack(data[point_at:end])))
            point_at = end
        if (any(not math.isfinite(value) for event in events for value in event[:3])
                or any(not math.isfinite(value) for lane in lanes for point in lane for value in point)):
            raise ValueError("AILD contains a non-finite route value")
        sections.append(Section(label, mask, loop, events, tuple(lanes)))
    return sections


def route_obj(args):
    sections = read_route(args.input.read_bytes())
    first = 1
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("# Race Driver 3 route. Coordinates are X/Z, with Y set to zero.\n")
        for section in sections:
            # Keep the existing OBJ group names in stored lane order.
            for lane, coordinates in enumerate(section.lanes):
                stream.write(f"g {section.label}_{lane}\n")
                stream.writelines(f"v {x:.9g} 0 {z:.9g}\n" for x, z in coordinates)
                indices = list(range(first, first + len(coordinates)))
                if section.loop:
                    indices.append(first)
                if len(indices) > 1:
                    stream.write("l " + " ".join(map(str, indices)) + "\n")
                first += len(coordinates)


def coordinate_fields(sections):
    lanes = sorted({lane for section in sections for lane in section.lane_ids})
    return tuple(f"{axis}{lane}" for lane in lanes for axis in ("x", "z"))


def route_export(args):
    sections = read_route(args.input.read_bytes())
    coordinates = coordinate_fields(sections)
    with args.output.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, FIELDS + coordinates, lineterminator="\n")
        writer.writeheader()
        for section in sections:
            for station, event in enumerate(section.events):
                values = [f"{value:.9g}" for value in event[:3]]
                row = dict(zip(FIELDS, (section.label, station, *values, *event[3:])))
                for lane, points in zip(section.lane_ids, section.lanes):
                    x, z = points[station]
                    row.update({f"x{lane}": f"{x:.9g}", f"z{lane}": f"{z:.9g}"})
                writer.writerow(row)


def route_import(args):
    sections = read_route(args.input.read_bytes())
    coordinates = coordinate_fields(sections)
    events = bytearray()
    points = bytearray()
    sizes = []
    boundary = {12: [], 13: []}
    with args.csv.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != FIELDS + coordinates:
            raise ValueError("CSV columns do not match the route template")
        groups = groupby(reader, key=itemgetter("section"))
        for section in sections:
            label, rows = next(groups, (None, ()))
            if label != section.label:
                raise ValueError(f"Expected a nonempty {section.label} route section")
            lane_ids = section.lane_ids
            active = {f"{axis}{lane}" for lane in lane_ids for axis in ("x", "z")}
            lanes = [bytearray() for _ in lane_ids]
            size = 0
            for station, row in enumerate(rows):
                if station >= 0xffff:
                    raise ValueError(f"Too many stations in the {section.label} route section")
                if row.get("station") != str(station) or None in row:
                    raise ValueError(f"Expected CSV row for {section.label} station {station}")
                if any(row[field] != "" for field in coordinates if field not in active):
                    raise ValueError(f"Unexpected lane value at {section.label} station {station}")
                event = [float(row[field]) for field in FIELDS[2:5]]
                flags = [int(row[field]) for field in FIELDS[5:]]
                events.extend(EVENT.pack(*event, *flags))
                if section.label == "main" and flags[0] in boundary:
                    boundary[flags[0]].append(station)
                for lane_id, lane in zip(lane_ids, lanes):
                    lane.extend(POINT.pack(float(row[f"x{lane_id}"]), float(row[f"z{lane_id}"])))
                size = station + 1
            if not args.resize and size != len(section.events):
                raise ValueError(f"Station count changed in {section.label}. Use --resize for intentional changes")
            sizes.append(size)
            points.extend(b"".join(lanes))
        if next(groups, None) is not None:
            raise ValueError("CSV has extra route stations")
    starts, ends = boundary[12], boundary[13]
    if len(starts) != 1 or len(ends) != 1:
        raise ValueError("Main route requires one code 12 and one code 13 lap-boundary marker")
    count = (ends[0] - starts[0]) % sizes[0] + 1
    if count != sizes[2]:
        raise ValueError("Lap-boundary markers do not span the auxiliary route's station count")
    header = b"".join(SECTION.pack(size, section.mask, section.loop) for size, section in zip(sizes, sections))
    result = MAGIC + header + events + points
    read_route(result)
    with args.output.open("xb") as stream:
        stream.write(result)
