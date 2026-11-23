#!/usr/bin/env python3
"""Build an original circuit from a closed two-dimensional centerline."""

import argparse
from bisect import bisect_right
import json
import math
from pathlib import Path
import shutil
import struct
from tempfile import TemporaryDirectory

from BuildFoundryOval import build_packages, write_obj
from BuildRoadAmericaMod import TrackEntry, event_catalog, track_catalog
from Ps2TrackRoute import EVENT, MAGIC, POINT, SECTION, read_route


def unit(x, z):
    length = math.hypot(x, z)
    if length < 1e-6:
        raise ValueError("Coincident points or a reversal in the centerline")
    return x / length, z / length


class Circuit:
    def __init__(self, layout):
        self.name = layout["name"]
        if (not isinstance(self.name, str) or not 1 <= len(self.name) <= 48
                or not self.name.isascii() or not self.name.isprintable() or any(c in self.name for c in ";#[]")):
            raise ValueError("Use a printable ASCII circuit name of 1–48 characters")
        self.width = float(layout["road_width_m"])
        self.height = float(layout.get("height_m", 12))
        self.sectors = tuple(map(float, layout.get("sectors", (1 / 3, 2 / 3))))
        if not 8 <= self.width <= 24 or not -100 <= self.height <= 500:
            raise ValueError("Road width must be 8–24 m and height must be -100–500 m")
        if (len(self.sectors) != 2 or not 0.13 < self.sectors[0] < self.sectors[1] < 0.87
                or self.sectors[1] - self.sectors[0] < 0.08):
            raise ValueError("Supply two separated sector fractions in driving order")
        anchors = [tuple(map(float, p)) for p in layout["centerline"]]
        if not 8 <= len(anchors) <= 256 or any(
                len(p) != 2 or not all(math.isfinite(v) and abs(v) <= 10000 for v in p) for p in anchors):
            raise ValueError("Supply 8–256 finite X/Z pairs, without repeating the closing point")
        edges = [(b[0] - a[0], b[1] - a[1]) for a, b in zip(anchors, anchors[1:] + anchors[:1])]
        directions = [unit(*edge) for edge in edges]
        tangents = [unit(x + directions[i - 1][0], z + directions[i - 1][1])
                    for i, (x, z) in enumerate(directions)]

        points = []
        for i, a in enumerate(anchors):
            nxt = (i + 1) % len(anchors)
            b = anchors[nxt]
            span = math.hypot(*edges[i])
            for step in range(16):
                t = step / 16
                smooth = t * t * (3 - 2 * t)
                points.append(tuple(a[k] * (1 - smooth) + b[k] * smooth
                                    + span * t * (1 - t) * ((1 - t) * tangents[i][k] - t * tangents[nxt][k])
                                    for k in range(2)))
        points.append(points[0])
        distances = [0.]
        for a, b in zip(points, points[1:]):
            distances.append(distances[-1] + math.dist(a, b))
        self.length = float(layout.get("length_m", distances[-1]))
        if not 600 <= self.length <= 4000:
            raise ValueError("Circuit length must be 600–4000 m")
        scale = self.length / distances[-1]
        origin = tuple((min(axis) + max(axis)) / 2 for axis in zip(*points))
        self.points = [(1060 + (x - origin[0]) * scale, 600 + (z - origin[1]) * scale) for x, z in points]
        self.distances = [d * scale for d in distances]
        self.stations = [i * self.length / math.ceil(self.length / 8)
                         for i in range(math.ceil(self.length / 8))]
        self.validate()

    def position(self, distance):
        d = distance % self.length
        i = min(bisect_right(self.distances, d), len(self.points) - 1)
        a, b = self.points[i - 1:i + 1]
        weight = (d - self.distances[i - 1]) / (self.distances[i] - self.distances[i - 1])
        return ((1 - weight) * a[0] + weight * b[0], (1 - weight) * a[1] + weight * b[1])

    def direction(self, distance):
        ax, az = self.position(distance - 0.4)
        bx, bz = self.position(distance + 0.4)
        return unit(bx - ax, bz - az)

    def offset(self, distance, lateral=0):
        x, z = self.position(distance)
        dx, dz = self.direction(distance)
        return x + dz * lateral, z - dx * lateral

    def validate(self):
        start_dx, start_dz = self.direction(0)
        for distance in range(-90, 91, 5):
            dx, dz = self.direction(distance)
            if dx * start_dx + dz * start_dz < 0.965:
                raise ValueError("Leave at least 90 m of nearly straight road on each side of start/finish")
        samples = [self.position(d) for d in self.stations]
        edges = list(zip(samples, samples[1:] + samples[:1]))

        def side(a, b, q):
            return (b[0] - a[0]) * (q[1] - a[1]) - (b[1] - a[1]) * (q[0] - a[0])

        for i, (a, b) in enumerate(edges):
            for c, d in edges[i + 2:-1 if i == 0 else None]:
                if (side(a, b, c) * side(a, b, d) < 0 and side(c, d, a) * side(c, d, b) < 0):
                    raise ValueError("The centerline intersects itself")


def pit_offset(distance, width):
    return (width / 2 + 6) * min(1, (90 - abs(distance)) / 30)


def build_route(circuit):
    stations = circuit.stations
    count = len(stations)
    first, second = (round(frac * count) for frac in circuit.sectors)
    boundary = round(80 * count / circuit.length)
    if first < boundary + 2 or second > count - boundary - 2:
        raise ValueError("Keep the timing splits outside the 80 m start/finish area")
    markers = {
        0: (6, 255, 0), boundary: (13, 255, 0),
        (boundary + first) // 2: (10, 0, 0), first: (2, 255, 0),
        (first + second) // 2: (10, 1, 0), second: (2, 255, 1),
        (second + count - boundary) // 2: (10, 2, 0), count - boundary: (12, 255, 0),
    }
    main = [(d, 0., *markers.get(i, (0, 255, 0))) for i, d in enumerate(stations)]
    pit = []
    for i, d in enumerate(range(-90, 91, 5)):
        slots = 5 <= i <= 31 and i % 2 == 1 and i != 17
        code = {1: 5, 3: 14, 18: 6, 33: 15, 35: 11}.get(i, 3 if slots else 0)
        pit.append((d, pit_offset(d, circuit.width), code, (i - 5) // 2 if code == 3 else 255, int(code == 3)))
    auxiliary = [(d, 0., 0, 1, 0) for d in stations[-boundary:] + stations[:boundary + 1]]
    half = circuit.width / 2
    # The main route's outer lanes frame the drivable ribbon instead of collapsing onto its center.
    groups = ((main, (-half, -half * 0.46, half * 0.32, 0, half), 0x1f, 1),
              (pit, (0, 1.6, 2.8, 2.8), 0x27, 0), (auxiliary, (0, 4.0), 3, 0))
    headers, events, points = bytearray(), bytearray(), bytearray()
    for rows, offsets, mask, loop in groups:
        headers.extend(SECTION.pack(len(rows), mask, loop))
        for i, (distance, _, code, tag, argument) in enumerate(rows):
            dx, dz = circuit.direction(distance)
            lap_distance = circuit.length if loop and i == 0 else distance % circuit.length
            events.extend(EVENT.pack(dz, -dx, lap_distance, code, tag, argument, 0))
        for offset in offsets:
            for distance, lateral, *_ in rows:
                points.extend(POINT.pack(*circuit.offset(distance, lateral + offset)))
    route = MAGIC + headers + events + points
    read_route(route)
    return route


def build_geometry(circuit, work):
    half = circuit.width / 2

    def ribbon(vertices, faces, stations, edges, closed=False):
        start = len(vertices)
        for d in stations:
            for offset in edges(d):
                x, z = circuit.offset(d, offset)
                vertices.append((x, circuit.height, z))
        for i in range(len(stations) if closed else len(stations) - 1):
            a, b = start + 2 * i, start + 2 * ((i + 1) % len(stations))
            faces.append((a, a + 1, b + 1, b))

    road, road_faces = [], []
    ribbon(road, road_faces, circuit.stations, lambda d: (-half, half), closed=True)
    ribbon(road, road_faces, list(range(-85, 86, 5)),
           lambda d: (pit_offset(d, circuit.width) - 3.4, pit_offset(d, circuit.width) + 3.4))
    write_obj(work / "road.obj", road, road_faces)

    marks, mark_faces = [], []
    for side in (-1, 1):
        ribbon(marks, mark_faces, circuit.stations, lambda d: (side * (half - 0.35), side * (half - 0.17)),
               closed=True)
    for i in range(10):
        left = -half + i * circuit.width / 10
        d = -0.65 if i % 2 else 0
        ribbon(marks, mark_faces, [d, d + 0.65], lambda d: (left, left + circuit.width / 10))
    write_obj(work / "markings.obj", marks, mark_faces)

    xs, _, zs = zip(*road)
    xmin, xmax = min(xs) - 40, max(xs) + 40
    zmin, zmax = min(zs) - 40, max(zs) + 40
    cols, rows = math.ceil((xmax - xmin) / 30), math.ceil((zmax - zmin) / 30)
    ground = [(xmin + x * (xmax - xmin) / cols, circuit.height, zmin + z * (zmax - zmin) / rows)
              for z in range(rows + 1) for x in range(cols + 1)]
    stride = cols + 1
    write_obj(work / "ground.obj", ground, ((i, i + 1, i + stride + 1, i + stride)
                                             for i in range(rows * stride) if i % stride != cols))


def preview(circuit, work):
    build_geometry(circuit, work)
    route = build_route(circuit)
    (work / "route.ail").write_bytes(route)
    # A centred line for scripted driving. Repeat across start/finish for lap and ghost checks.
    with (work / "drive-line.txt").open("w", encoding="ascii", newline="\n") as stream:
        for i in range(-15, 2 * len(circuit.stations) + 16):
            d = i * circuit.length / len(circuit.stations)
            x, z = circuit.position(d)
            before, after = circuit.direction(d - 7), circuit.direction(d + 7)
            turn = abs(math.atan2(before[0] * after[1] - before[1] * after[0],
                                  before[0] * after[0] + before[1] * after[1]))
            speed = max(15, min(36, math.sqrt(85 / max(turn, 0.01))))
            stream.write(f"{x:.5f} {z:.5f} {speed:.2f}\n")
    return route


def build(circuit, source, output, work):
    entry = TrackEntry("tqa5", circuit.name, f"{circuit.length / 1000:.3f}", 54)
    tracks = track_catalog((source / "tracks.big").read_bytes(), (entry,), existing=84)
    events = event_catalog((source / "events.big").read_bytes(), (entry,), existing_rounds=14, add_oschersleben=False)
    route = preview(circuit, work)
    track, dma = build_packages((source / "TRACK.JPK").read_bytes(), (source / "DMA1.JPK").read_bytes(),
                                work, route=route, markings=True)
    pack = work / "pack"
    for directory in ("", "tqa2", "tqa3", "tqa4") + (("rain",) if (source / "rain").is_dir() else ()):
        target = pack / directory
        target.mkdir()
        for name in ("TRACK.JPK", "DMA1.JPK"):
            shutil.copyfile(source / directory / name, target / name)
    (pack / "tracks.big").write_bytes(tracks)
    (pack / "events.big").write_bytes(events)
    (pack / entry.slot).mkdir()
    (pack / entry.slot / "TRACK.JPK").write_bytes(track)
    (pack / entry.slot / "DMA1.JPK").write_bytes(dma)
    pack.rename(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("preview", "build"):
        command = commands.add_parser(name, help="export authoring files" if name == "preview" else "build slot tqa5")
        command.add_argument("layout", type=Path, help="circuit JSON file")
        if name == "build":
            command.add_argument("source", type=Path, help="four-course pack built with BuildFoundryOval.py")
        command.add_argument("output", type=Path, help="new directory under an existing parent")
    args = parser.parse_args()
    try:
        circuit = Circuit(json.loads(args.layout.read_text(encoding="utf-8-sig")))
        if args.output.exists():
            raise ValueError("Choose a new output directory")
        with TemporaryDirectory(dir=args.output.parent) as directory:
            work = Path(directory)
            if args.command == "preview":
                folder = work / "preview"
                folder.mkdir()
                preview(circuit, folder)
                folder.rename(args.output.resolve())
            else:
                build(circuit, args.source, args.output.resolve(), work)
    except (OSError, ValueError, TypeError, IndexError, KeyError, struct.error) as error:
        parser.exit(1, f"Circuit build failed: {error}\n")
    print(f"{circuit.name}: {circuit.length:.1f} m, {len(circuit.stations)} main stations -> {args.output}")


if __name__ == "__main__":
    main()
