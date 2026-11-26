#!/usr/bin/env python3
"""Build an original circuit from a closed two-dimensional centerline."""

import argparse
from bisect import bisect_right
import json
import math
from pathlib import Path
import struct
from tempfile import TemporaryDirectory

from BuildFoundryOval import build_packages, copy_circuit_files, write_obj
from BuildRoadAmericaMod import TrackEntry, event_catalog, track_catalog
from BuildTrackMapIcons import build_icons
from Ps2TrackRoute import EVENT, MAGIC, PIT_STALL_COUNT, POINT, SECTION, read_route

PIT_HALF_WIDTH = 3.4
GRID_APPROACH_METRES = 176


def unit(x, z):
    length = math.hypot(x, z)
    if length < 1e-6:
        raise ValueError("Coincident points or a reversal in the centerline")
    return x / length, z / length


def side(a, b, p):
    return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])


def closed_edges(points):
    return list(zip(points, points[1:] + points[:1]))


def edges_touch(a, b, c, d):
    if any(max(a[i], b[i]) < min(c[i], d[i]) or max(c[i], d[i]) < min(a[i], b[i]) for i in (0, 1)):
        return False
    return side(a, b, c) * side(a, b, d) <= 0 and side(c, d, a) * side(c, d, b) <= 0


def simple_loop(edges, label):
    for i, (a, b) in enumerate(edges):
        for c, d in edges[i + 2:-1 if i == 0 else None]:
            if edges_touch(a, b, c, d):
                raise ValueError(f"{label} intersects itself near station {i}")


def validate_ribbon(left, right, label, *, closed):
    count = len(left)
    for i in range(count if closed else count - 1):
        j = (i + 1) % count
        # The generated OBJ uses one diagonal per segment. Both faces must retain the same winding.
        if side(left[i], right[i], right[j]) <= 1e-6 or side(left[i], right[j], left[j]) <= 1e-6:
            raise ValueError(f"{label} folds near station {i}; increase the bend radius or narrow the road")
    if closed:
        left_edges, right_edges = closed_edges(left), closed_edges(right)
        simple_loop(left_edges, f"{label} left edge")
        simple_loop(right_edges, f"{label} right edge")
        for i, (a, b) in enumerate(left_edges):
            if any(edges_touch(a, b, c, d) for c, d in right_edges):
                raise ValueError(f"{label} edges cross near station {i}; separate nearby parts of the circuit")
    else:
        simple_loop(closed_edges(left + right[::-1]), label)


class Circuit:
    def __init__(self, layout):
        self.name = layout["name"]
        if (not isinstance(self.name, str) or not 1 <= len(self.name) <= 48
                or not self.name.isascii() or not self.name.isprintable() or any(c in self.name for c in ";#[]")):
            raise ValueError("Use a printable ASCII circuit name of 1–48 characters")
        self.width = float(layout["road_width_m"])
        self.height = float(layout.get("height_m", 12))
        self.perimeter_wall = float(layout.get("perimeter_wall_m", 0))
        self.sectors = tuple(map(float, layout.get("sectors", (1 / 3, 2 / 3))))
        if not 8 <= self.width <= 24 or not -100 <= self.height <= 500:
            raise ValueError("Road width must be 8–24 m and height must be -100–500 m")
        if not 0 <= self.perimeter_wall <= 1.9:
            raise ValueError("Perimeter wall height must be 0–1.9 m")
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
        simple_loop(closed_edges([self.position(d) for d in self.stations]), "The centerline")
        half = self.width / 2
        left = [self.offset(d, -half) for d in self.stations]
        right = [self.offset(d, half) for d in self.stations]
        validate_ribbon(left, right, "The racing surface", closed=True)
        pit_stations = range(-85, 86, 5)
        left = [self.offset(d, pit_inner_edge(d, self.width)) for d in pit_stations]
        right = [self.offset(d, pit_offset(d, self.width) + PIT_HALF_WIDTH) for d in pit_stations]
        validate_ribbon(left, right, "The pit lane", closed=False)


def pit_offset(distance, width):
    return (width / 2 + 6) * min(1, (90 - abs(distance)) / 30)


def pit_inner_edge(distance, width):
    standard = pit_offset(distance, width) - PIT_HALF_WIDTH
    # The entry gate needs to accept a car as it finishes moving across from the main road.
    if -65 <= distance <= -50:
        clearance = 0.4 + max(0, distance + 55) / 5
    elif -50 < distance < -45:
        clearance = 1.4 + (distance + 50) * 1.2 / 5
    else:
        return standard
    return min(standard, width / 2 + clearance)


def build_route(circuit):
    stations = circuit.stations
    count = len(stations)
    first, second = (round(frac * count) for frac in circuit.sectors)
    boundary = round(80 * count / circuit.length)
    grid_approach = math.ceil(GRID_APPROACH_METRES * count / circuit.length)
    pit_approach = count - round(96 * count / circuit.length)
    pit_switch = count - round(88 * count / circuit.length)
    if first < boundary + 2 or second > count - grid_approach - 2:
        raise ValueError("Keep the timing splits outside the auxiliary start/finish route")
    markers = {
        0: (6, 255, 0), boundary: (13, 255, 0),
        (boundary + first) // 2: (10, 0, 0), first: (2, 255, 0),
        (first + second) // 2: (10, 1, 0), second: (2, 255, 1),
        (second + count - grid_approach) // 2: (10, 2, 0), pit_approach: (1, 255, 0),
        pit_switch: (3, 255, 1), count - grid_approach: (12, 255, 0),
    }
    if len(markers) != 10:
        raise ValueError("Keep enough space between sector splits and the pit approach")
    main = [(d, 0., *markers.get(i, (0, 255, 0))) for i, d in enumerate(stations)]
    pit_markers = {-55: (5, 255, 0), -50: (14, 255, 0), 0: (6, 255, 0),
                   50: (15, 255, 0), 60: (11, 255, 0), 90: (3, 255, 0)}
    # RD3 assigns teams any of the sixteen stall indices in a full field.
    for stall in range(PIT_STALL_COUNT):
        start = -47 + 6 * stall
        pit_markers[start] = (3, stall, 1)
        pit_markers[start + 4] = (4, stall, 0)
    pit = [(d, pit_offset(d, circuit.width), *pit_markers.get(d, (0, 255, 0)))
           for d in sorted(set(range(-90, 91, 5)) | pit_markers.keys())]
    # The last car of a 20-car grid starts about 156 m before the finish line.
    # Keep both placement lanes on the main road, including through bends.
    auxiliary = [(d, 0., 0, 1, 0) for d in stations[-grid_approach:] + stations[:boundary + 1]]
    half = circuit.width / 2
    # The main route's outer lanes frame the drivable ribbon instead of collapsing onto its center.
    # The pit entry tests lanes 0 and 1 as the two edges of the corridor; lane 2 is its center.
    groups = ((main, (-half, -half * 0.46, half * 0.32, 0, half), 0x1f, 1),
              (pit, (-PIT_HALF_WIDTH, PIT_HALF_WIDTH, 0, 2.8), 0x27, 0),
              (auxiliary, (-half / 3, half / 3), 3, 0))
    headers, events, points = bytearray(), bytearray(), bytearray()
    for rows, offsets, mask, loop in groups:
        headers.extend(SECTION.pack(len(rows), mask, loop))
        for i, (distance, _, code, tag, argument) in enumerate(rows):
            dx, dz = circuit.direction(distance)
            lap_distance = circuit.length if loop and i == 0 else distance % circuit.length
            events.extend(EVENT.pack(dz, -dx, lap_distance, code, tag, argument, 0))
        for lane, offset in enumerate(offsets):
            for distance, lateral, *_ in rows:
                edge = pit_inner_edge(distance, circuit.width) if mask == 0x27 and lane == 0 else lateral + offset
                points.extend(POINT.pack(*circuit.offset(distance, edge)))
    route = MAGIC + headers + events + points
    read_route(route)
    return route


def build_replay_cameras(circuit):
    count = math.ceil(circuit.length / 110)
    width = circuit.width / 2
    lines = []
    for index in range(count):
        distance = index * circuit.length / count
        # Frame the incoming cars from outside the racing and pit lanes.
        lateral = -(width + 10) if index % 2 == 0 else width + 10
        x, z = circuit.offset(distance + 18, lateral)
        target_x, target_z = circuit.position(distance - 12)
        dx, dy, dz = target_x - x, -3.5, target_z - z
        length = math.hypot(dx, dy, dz)
        lines.extend((
            f"[Camera_{index:03}]",
            f"fPositionx={x:.6f}", f"fPositiony={circuit.height + 5:.6f}", f"fPositionz={z:.6f}",
            f"fDirectionx={dx / length:.6f}", f"fDirectiony={dy / length:.6f}", f"fDirectionz={dz / length:.6f}",
            "boPanning=TRUE", "boTracking=FALSE", "boSimulatedHuman=FALSE", "boZooming=FALSE",
            "boCloseFollow=FALSE", "boIgnoreRoll=TRUE", "boIgnoreRotation=FALSE", "boBlackOut=FALSE",
            f"boRaceStart={'TRUE' if index == 0 else 'FALSE'}", "boUseLimits=FALSE",
            "fLeftLimit=-6.283185", "fRightLimit=6.283185", "fPitchOffset=0.000000",
            "fZoom=1.000000", "fZoomInOnCarAmount=0.000000", "fWobble=0.000000", "",
            f"[Activation_Zone_{index:03}]", "uNumCameras=1", f"uCamera000={index}",
            "nCamera000path=-1", "fCamera000selectionprobability=1.000000", "uNumVertices=4",
        ))
        # Short zones across the road let the director switch once per approach.
        center_x, center_z = circuit.position(distance)
        forward_x, forward_z = circuit.direction(distance)
        corners = ((-8, -1), (8, -1), (8, 1), (-8, 1))
        for vertex, (longitudinal, side) in enumerate(corners):
            across = side * (width + 1)
            vx = center_x + forward_x * longitudinal + forward_z * across
            vz = center_z + forward_z * longitudinal - forward_x * across
            lines.extend((f"fVertex{vertex:03}x={vx:.6f}", f"fVertex{vertex:03}z={vz:.6f}"))
        lines.append("")
    lines.extend(("[Cameras]", f"uNumCameras={count}", "", "[Paths]", "uNumPaths=0", "",
                  "[Activation_Zones]", f"uNumActivationZones={count}", "", "[CameraDirector]",
                  "uFileFormatRevision=1", "fFileFormatVersion=1.000000", ""))
    return "\r\n".join(lines).encode("ascii")


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
           lambda d: (pit_inner_edge(d, circuit.width), pit_offset(d, circuit.width) + PIT_HALF_WIDTH))
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
    if circuit.perimeter_wall:
        north = list(range(cols))
        east = [row * stride + cols for row in range(rows)]
        south = [rows * stride + col for col in range(cols, 0, -1)]
        west = [row * stride for row in range(rows, 0, -1)]
        perimeter = north + east + south + west
        vertices = []
        for i in perimeter:
            x, y, z = ground[i]
            vertices.extend(((x, y - 0.2, z), (x, y + circuit.perimeter_wall, z)))
        quads = ((i, (i + 2) % len(vertices), (i + 3) % len(vertices), i + 1)
                 for i in range(0, len(vertices), 2))
        write_obj(work / "perimeter.obj", vertices, quads)


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


def build(circuit, source, output, work, *, disc=None):
    # The generated pit lane uses positive (rightward) lateral offsets.
    entry = TrackEntry("tqa5", circuit.name, f"{circuit.length / 1000:.3f}", 54, pit_side="RIGHT")
    tracks = track_catalog((source / "tracks.big").read_bytes(), (entry,), existing=84)
    events = event_catalog((source / "events.big").read_bytes(), (entry,), existing_rounds=14, add_oschersleben=False)
    route = preview(circuit, work)
    track, dma = build_packages((source / "TRACK.JPK").read_bytes(), (source / "DMA1.JPK").read_bytes(),
                                work, route=route, markings=True)
    pack = work / "pack"
    for directory in ("", "tqa2", "tqa3", "tqa4") + (("rain",) if (source / "rain").is_dir() else ()):
        copy_circuit_files(source / directory, pack / directory)
    (pack / "tracks.big").write_bytes(tracks)
    (pack / "events.big").write_bytes(events)
    (pack / entry.slot).mkdir()
    (pack / entry.slot / "TRACK.JPK").write_bytes(track)
    (pack / entry.slot / "DMA1.JPK").write_bytes(dma)
    (pack / entry.slot / "replay-cameras.ini").write_bytes(build_replay_cameras(circuit))
    if disc is not None:
        (pack / "TS_RCCUF.LZS").write_bytes(build_icons(disc, pack))
    pack.rename(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("preview", "build"):
        command = commands.add_parser(name, help="export authoring files" if name == "preview" else "build slot tqa5")
        command.add_argument("layout", type=Path, help="circuit JSON file")
        if name == "build":
            command.add_argument("source", type=Path, help="four-course pack built with BuildFoundryOval.py")
            command.add_argument("--disc", type=Path, help="RD3 disc directory for track selector icons")
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
                build(circuit, args.source, args.output.resolve(), work, disc=args.disc)
    except (OSError, ValueError, TypeError, IndexError, KeyError, struct.error) as error:
        parser.exit(1, f"Circuit build failed: {error}\n")
    print(f"{circuit.name}: {circuit.length:.1f} m, {len(circuit.stations)} main stations -> {args.output}")


if __name__ == "__main__":
    main()
