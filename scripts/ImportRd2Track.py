#!/usr/bin/env python3
"""Build a standalone RD3 PS2 circuit pack from an indexed RD2 layout."""

import argparse
import hashlib
from itertools import pairwise
import json
import math
from pathlib import Path
import re
import struct
from tempfile import TemporaryDirectory

from BuildDtmVariant import read_disc_range
from BuildRoadAmericaMod import (
    A1_RING, ROAD_AMERICA, EVENT_CATALOG_BYTES, EVENT_CATALOG_SECTOR, TRACK_CATALOG_BYTES,
    TRACK_CATALOG_SECTOR, TrackEntry, circuit_payloads, convert_route, event_catalog, read_bigf, track_catalog,
)
from BuildTrackCollisionOverlay import REFERENCE_DIRECTORY_HASH, TRACK_BYTES, TRACK_SECTOR, verify_directory
from BuildTrackGeometryOverlay import DMA_BYTES, DMA_SECTOR
from BuildTrackMapIcons import build_icons
from ModAssets import find_member
from Ps2TrackCollision import Collision, GRID_CELLS, GRID_SIDE, MAX_XZ, neighbors
from Ps2TrackRoute import PIT_STALL_COUNT, read_route
from Rd2AssetCatalog import choose_route, circuits, scan_disc


def describe_slot(disc, code, route, name=None):
    main, pit, _ = read_route(route)
    center = main.lanes[3]
    pit_center = pit.lanes[2][len(pit.events) // 2]
    index = min(range(len(center)), key=lambda i: math.dist(center[i], pit_center))
    before, after = center[index - 1], center[(index + 1) % len(center)]
    ax, az = after[0] - before[0], after[1] - before[1]
    bx, bz = pit_center[0] - center[index][0], pit_center[1] - center[index][1]
    side = "RIGHT" if ax * bz - az * bx >= 0 else "LEFT"
    # The first AID distance can be zero and the closing segment still counts.
    distance = math.fsum(math.dist(a, b) for a, b in zip(center, center[1:] + center[:1], strict=True)) / 1000
    if not 0.1 <= distance <= 100:
        raise ValueError(f"Invalid circuit length for {code}")
    catalog = read_disc_range(disc, 1, TRACK_CATALOG_SECTOR, TRACK_CATALOG_BYTES)
    members, _ = read_bigf(catalog, 80)
    indices = {int(match[1]) for data in members.values()
               if (match := re.search(rb"(?mi)^HOFIndex\s*=\s*(\d+)", data))}
    record = next((i for i in range(128) if i not in indices), None)
    if record is None:
        raise ValueError("No free RD3 circuit record index")
    known = {course.donor_prefix: course.name for course in (ROAD_AMERICA, *A1_RING)}
    title = name or known.get(code, f"RD2 {code.upper()}")
    if (not 1 <= len(title) <= 48 or not title.strip() or not title.isascii()
            or not title.isprintable() or any(c in title for c in ";#[]")):
        raise ValueError("Use a printable ASCII circuit name of 1–48 characters without INI delimiters")
    return catalog, TrackEntry("tqa1", title, f"{distance:.3f}", record, pit_side=side)


def build(donor, reference, layout, code, scene_number, output, name=None):
    verify_directory(reference / "RDH.DIR", REFERENCE_DIRECTORY_HASH)
    choices = layout["scenes"]
    if scene_number is None and len(choices) != 1:
        raise ValueError(f"{code} has {len(choices)} scenes. Choose a scene number from catalog output")
    index = 1 if scene_number is None else scene_number
    if not 1 <= index <= len(choices):
        raise ValueError(f"Scene number for {code} must be between 1 and {len(choices)}")
    scene = choices[index - 1]
    aid = choose_route(donor, code, layout["routes"], scene)
    route = convert_route(aid)
    catalog, entry = describe_slot(reference, code, route, name)
    original = read_disc_range(reference, 1, TRACK_SECTOR, TRACK_BYTES)
    original_scene = read_disc_range(reference, 1, DMA_SECTOR, DMA_BYTES)
    payloads = circuit_payloads(donor, scene, code, original, original_scene, route)
    events = read_disc_range(reference, 1, EVENT_CATALOG_SECTOR, EVENT_CATALOG_BYTES)
    with TemporaryDirectory(dir=output.parent) as stage:
        pack = Path(stage) / "circuit"
        pack.mkdir()
        for filename, data in payloads.items():
            (pack / filename).write_bytes(data)
        (pack / "tracks.big").write_bytes(track_catalog(catalog, (entry,)))
        # Only one donor scene was selected, so register one weather choice for it.
        (pack / "events.big").write_bytes(event_catalog(events, (entry,), add_oschersleben=True,
                                                         rainy_slots=(b"osc1",)))
        (pack / "TS_RCCUF.LZS").write_bytes(build_icons(reference, pack))
        pack.rename(output.resolve())
    return entry


def check_ground(mesh, routes):
    if not all(math.isfinite(value) for value in mesh.lower) or not all(
            math.isfinite(span) and span > 0 for span in mesh.spans):
        raise ValueError("Invalid collision bounds")
    vertices = tuple(mesh.world(vertex) for vertex in mesh.vertices)
    for name, lane in routes.items():
        gaps = []
        for station, (x, z) in enumerate(lane):
            column = int((x - mesh.lower[0]) * (MAX_XZ + 1) / mesh.spans[0]) >> 16
            row = int((z - mesh.lower[2]) * (MAX_XZ + 1) / mesh.spans[2]) >> 16
            faces = set()
            if 0 <= column < GRID_SIDE and 0 <= row < GRID_SIDE:
                for cell in neighbors(row * GRID_SIDE + column):
                    first, ref = mesh.starts[cell]
                    last, end_ref = mesh.starts[min(cell + 1, GRID_CELLS - 1)]
                    faces.update(range(first, last))
                    faces.update(mesh.references[ref:end_ref])
            for index in faces:
                a, b, c = (vertices[i] for i in mesh.triangles[index])
                ab = (b[0] - a[0], b[2] - a[2])
                bc = (c[0] - b[0], c[2] - b[2])
                ca = (a[0] - c[0], a[2] - c[2])
                area = ab[1] * bc[0] - ab[0] * bc[1]
                if area > 1e-5 and all(dz * (x - point[0]) - dx * (z - point[2]) >= -1e-4
                                       for point, (dx, dz) in zip((a, b, c), (ab, bc, ca))):
                    break
            else:
                gaps.append(station)
        yield name, gaps


def check_ground_segments(mesh, routes, closed=()):
    fractions = (0.25, 0.5, 0.75)
    samples = {}
    for name, lane in routes.items():
        points = tuple(lane)
        if name in closed:
            points += points[:1]
        samples[name] = [(x0 + (x1 - x0) * fraction, z0 + (z1 - z0) * fraction)
                         for (x0, z0), (x1, z1) in pairwise(points) for fraction in fractions]
    return {name: sorted({index // len(fractions) for index in gaps})
            for name, gaps in check_ground(mesh, samples)}


def audit_pack(pack, slot, weather="sunny"):
    root = pack if slot == "tqa1" else pack / slot
    if weather == "rain":
        root = root / "rain"
    data = (root / "TRACK.JPK").read_bytes()
    nested = find_member(data, "osc1.big")[0].read(data)
    main, pit, grid = read_route(find_member(nested, "osc1.ail")[0].read(nested))
    mesh = Collision(find_member(data, "col.col")[0].read(data))
    lanes = {"main": main.lanes[3], "pit": pit.lanes[2], "grid_left": grid.lanes[0], "grid_right": grid.lanes[1]}
    sectors = [(i, round(event[2], 2), event[5]) for i, event in enumerate(main.events) if event[3] == 2]
    stall_starts = {event[4]: i for i, event in enumerate(pit.events) if event[3:6:2] == (3, 1)}
    stall_ends = {event[4]: i for i, event in enumerate(pit.events) if event[3] == 4}
    stall_paths = {tag: pit.lanes[3][start:stall_ends[tag] + 1]
                   for tag, start in stall_starts.items() if stall_ends.get(tag, -1) > start}
    stall_gaps = dict(check_ground(mesh, stall_paths))
    stall_segment_gaps = check_ground_segments(mesh, stall_paths)
    return {
        "slot": slot,
        "weather": weather,
        "track_archive_sha256": hashlib.sha256(data).hexdigest(),
        "stations": {route.label: len(route.events) for route in (main, pit, grid)},
        "sector_markers": [{"station": i, "distance_m": distance, "argument": argument}
                           for i, distance, argument in sectors],
        "pit_entry_markers_m": [round(event[2], 2) for event in main.events if event[3] in (1, 3)],
        "pit_stall_tags": sorted(stall_starts),
        "unassigned_rd3_pit_stalls": sorted(set(range(PIT_STALL_COUNT)) - stall_paths.keys()),
        "pit_stalls_without_end_marker": sorted(stall_starts.keys() - stall_paths.keys()),
        "pit_stalls_without_upward_collision": sorted(tag for tag in stall_paths
                                                       if stall_gaps[tag] or stall_segment_gaps[tag]),
        "collision_triangles": len(mesh.triangles),
        "route_stations_without_upward_collision": dict(check_ground(mesh, lanes)),
        "route_segments_without_upward_collision": check_ground_segments(mesh, lanes, {"main"} if main.loop else ()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    catalog = commands.add_parser("catalog", help="list layouts, route archives, and indexed scenes")
    convert = commands.add_parser("build", help="build a playable single-layout pack for a compatible donor")
    audit = commands.add_parser("audit", help="check route markers and collision in a built circuit pack")
    audit.add_argument("pack", type=Path)
    audit.add_argument("--slot", choices=("tqa1", "tqa2", "tqa3", "tqa4", "tqa5"), default="tqa1")
    audit.add_argument("--weather", choices=("sunny", "rain"), default="sunny")
    for command in (catalog, convert):
        command.add_argument("--rd2-disc", type=Path, required=True)
    convert.add_argument("layout", type=str.lower)
    convert.add_argument("--scene", type=int, help="one-based scene number printed by catalog")
    convert.add_argument("--name", help="optional display name")
    convert.add_argument("--disc", type=Path, required=True, help="mounted or extracted RD3 disc")
    convert.add_argument("--output", type=Path, required=True, help="new directory for the generated pack")
    args = parser.parse_args()
    try:
        if args.command == "audit":
            print(json.dumps(audit_pack(args.pack, args.slot, args.weather), indent=2))
            return
        layouts = circuits(scan_disc(args.rd2_disc))
        if args.command == "catalog":
            for code, layout in layouts.items():
                scenes = ", ".join(f"{index}=HUG {p.hug} sector {p.sector}"
                                   for index, p in enumerate(layout["scenes"], 1))
                print(f"{code}: {len(layout['routes'])} route archives, scenes {scenes}")
            return
        if args.layout not in layouts or re.fullmatch(r"[a-z0-9]+", args.layout) is None:
            raise ValueError(f"Unknown supported scene ID {args.layout!r}; use catalog to list IDs")
        if args.output.exists():
            raise ValueError("Choose a new output directory")
        track = build(args.rd2_disc, args.disc, layouts[args.layout], args.layout, args.scene, args.output, args.name)
    except (OSError, ValueError, struct.error, KeyError, IndexError, StopIteration) as error:
        parser.exit(1, f"RD2 circuit import failed: {error}\n")
    print(f"{track.name} ({track.km} km) -> {args.output}")


if __name__ == "__main__":
    main()
