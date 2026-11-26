#!/usr/bin/env python3
"""Add the original Foundry Oval demonstration circuit to an expanded PS2 track pack."""

import argparse
import math
from pathlib import Path
from shutil import copyfile
import struct
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from BuildRoadAmericaMod import TrackEntry, event_catalog, track_catalog
from ModAssets import find_member, replace_member
from Ps2TrackCollision import Collision, append_triangles, collision_append, read_triangles
from Ps2TrackRoute import EVENT, MAGIC, POINT, SECTION, read_route
from Ps2TrackScene import Scene, scene_append


CENTER_X, CENTER_Z, HEIGHT = 1060.0, 600.0, 12.0
HALF_STRAIGHT, RADIUS, ROAD_HALF_WIDTH = 100.0, 48.0, 9.0
ARC = math.pi * RADIUS
LENGTH = 4 * HALF_STRAIGHT + 2 * ARC
STATIONS = 72


def position(distance):
    at = distance % LENGTH
    if at < HALF_STRAIGHT:
        return -at, -RADIUS, -1.0, 0.0
    at -= HALF_STRAIGHT
    if at < ARC:
        theta = -math.pi / 2 - at / RADIUS
        return -HALF_STRAIGHT + RADIUS * math.cos(theta), RADIUS * math.sin(theta), math.sin(theta), -math.cos(theta)
    at -= ARC
    if at < 2 * HALF_STRAIGHT:
        return -HALF_STRAIGHT + at, RADIUS, 1.0, 0.0
    at -= 2 * HALF_STRAIGHT
    if at < ARC:
        theta = math.pi / 2 - at / RADIUS
        return HALF_STRAIGHT + RADIUS * math.cos(theta), RADIUS * math.sin(theta), math.sin(theta), -math.cos(theta)
    at -= ARC
    return HALF_STRAIGHT - at, -RADIUS, -1.0, 0.0


def station(distance, lateral=0):
    x, z, dx, dz = position(distance)
    return CENTER_X + x + dz * lateral, CENTER_Z + z - dx * lateral


def build_route():
    distances = [i * LENGTH / STATIONS for i in range(STATIONS)]
    # Time Trial advances the ghost recorder at the sector splits before accepting the finish.
    main_codes = {0: (6, 255, 0), 8: (13, 255, 0), 17: (10, 0, 0), 24: (2, 255, 0),
                  36: (10, 1, 0), 48: (2, 255, 1), 54: (10, 2, 0), 64: (12, 255, 0)}
    main = [(s, 0.0, *main_codes.get(i, (0, 255, 0))) for i, s in enumerate(distances)]
    pit = []
    for i, s in enumerate(range(-90, 91, 5)):
        lateral = 14.0 * min(1, (90 - abs(s)) / 30)
        slots = (5 <= i <= 31 and i % 2 == 1) and i != 17
        code = {1: 5, 3: 14, 18: 6, 33: 15, 35: 11}.get(i, 3 if slots else 0)
        pit.append((s, lateral, code, (i - 5) // 2 if code == 3 else 255, int(code == 3)))
    auxiliary = [(s, 0.0, 0, 1, 0) for s in distances[64:] + distances[:9]]
    groups = ((main, [0, 3.1, 5.8, -2.4, 8.1], 0x1f, 1),
              (pit, [0, 1.6, 2.8, 2.8], 0x27, 0), (auxiliary, [0, 4.0], 3, 0))
    headers, events, points = bytearray(), bytearray(), bytearray()
    for rows, offsets, mask, loop in groups:
        headers.extend(SECTION.pack(len(rows), mask, loop))
        for i, (distance, _, code, tag, argument) in enumerate(rows):
            _, _, dx, dz = position(distance)
            lap_distance = LENGTH if loop and i == 0 else distance % LENGTH
            events.extend(EVENT.pack(dz, -dx, lap_distance, code, tag, argument, 0))
        for offset in offsets:
            for distance, lateral, *_ in rows:
                points.extend(POINT.pack(*station(distance, lateral + offset)))
    route = MAGIC + headers + events + points
    read_route(route)
    return route


def write_obj(filename, points, quads):
    with filename.open("w", encoding="ascii", newline="\n") as stream:
        for x, y, z in points:
            stream.write(f"v {x:.7f} {y:.7f} {z:.7f}\n")
        for a, b, c, d in quads:
            for i, j, k in ((a, b, c), (a, c, d)):
                x1, _, z1 = points[i]
                x2, _, z2 = points[j]
                x3, _, z3 = points[k]
                if (z2 - z1) * (x3 - x1) < (x2 - x1) * (z3 - z1):
                    j, k = k, j
                stream.write(f"f {i + 1} {j + 1} {k + 1}\n")


def build_geometry(work):
    road = []
    for i in range(STATIONS):
        for lateral in (-ROAD_HALF_WIDTH, ROAD_HALF_WIDTH):
            x, z = station(i * LENGTH / STATIONS, lateral)
            road.append((x, HEIGHT, z))
    write_obj(work / "road.obj", road,
              ((2*i, 2*i+1, (2*i+3) % len(road), (2*i+2) % len(road)) for i in range(STATIONS)))
    rows, columns = 9, 19
    ground = [(CENTER_X + (x - 9) * 20, HEIGHT, CENTER_Z + (z - 4) * 20)
              for z in range(rows) for x in range(columns)]
    write_obj(work / "ground.obj", ground,
              ((i, i+1, i+columns+1, i+columns) for i in range(len(ground)-columns) if i % columns != columns-1))


def build_packages(track, dma, work, *, route=None, markings=False, textured=True):
    if route is None:
        build_geometry(work)
        route = build_route()
    original_collision = work / "template.col"
    original_collision.write_bytes(find_member(track, "col.col")[0].read(track))
    original_scene = work / "template.dma"
    original_scene.write_bytes(find_member(dma, "trk.dma")[0].read(dma))
    collision = work / "oval.col"
    collision_append(SimpleNamespace(command="collision-build", input=original_collision, output=collision,
                                     obj=work / "ground.obj", surface_from=1598))
    scene = work / "ground.dma"
    # The unmodified Sunny Road America package supplies the local texture and shading state.
    scene_append(SimpleNamespace(command="scene-replace", input=original_scene, output=scene, obj=work / "ground.obj",
                                 root=0x2284, leaf=0x95910, rgb=(88, 125, 95), offset_y=0), textured=textured)
    ground = Scene(scene.read_bytes())
    root, = ground.roots
    leaf, = ground.leaves(root)
    finished = work / "oval.dma"
    scene_append(SimpleNamespace(command="scene-append", input=scene, output=finished, obj=work / "road.obj",
                                  root=root, leaf=leaf, rgb=(135, 135, 148), offset_y=0.017), textured=textured)
    if markings:
        marked = work / "marked.dma"
        scene_append(SimpleNamespace(command="scene-append", input=finished, output=marked,
                                     obj=work / "markings.obj", root=root, leaf=leaf,
                                     rgb=(230, 230, 230), offset_y=0.027), textured=textured)
        finished = marked
    collision_data = collision.read_bytes()
    perimeter = work / "perimeter.obj"
    if perimeter.is_file():
        # Surface 9 is the vertical barrier material in the Road America template.
        vertices, faces = read_triangles(perimeter)
        collision_data = bytes(append_triangles(Collision(collision_data), vertices, faces, 9))
        bounded = work / "bounded.dma"
        scene_append(SimpleNamespace(command="scene-append", input=finished, output=bounded,
                                     obj=perimeter, root=root, leaf=leaf, rgb=(125, 128, 130), offset_y=0), textured=textured)
        finished = bounded
    track = replace_member(track, ["osc1.big", "osc1.ail"], route)
    track = replace_member(track, ["col.col"], collision_data)
    return track, replace_member(dma, ["trk.dma"], finished.read_bytes())


def copy_circuit_files(source, target):
    target.mkdir()
    for name in ("TRACK.JPK", "DMA1.JPK"):
        copyfile(source / name, target / name)
    cameras = source / "replay-cameras.ini"
    if cameras.is_file():
        copyfile(cameras, target / cameras.name)


def build_pack(source, output, work):
    foundry = TrackEntry("tqa4", "Foundry Oval", f"{LENGTH / 1000:.3f}", 36)
    tracks = track_catalog((source / "tracks.big").read_bytes(), (foundry,), existing=83)
    events = event_catalog((source / "events.big").read_bytes(), (foundry,), existing_rounds=13, add_oschersleben=False)
    pack = work / "pack"
    folders = ("", "tqa2", "tqa3") + (("rain",) if (source / "rain").exists() else ())
    for folder in folders:
        copy_circuit_files(source / folder, pack / folder)
    (pack / "tracks.big").write_bytes(tracks)
    (pack / "events.big").write_bytes(events)
    track, dma = build_packages((pack / "TRACK.JPK").read_bytes(), (pack / "DMA1.JPK").read_bytes(), work)
    (pack / foundry.slot).mkdir()
    (pack / foundry.slot / "TRACK.JPK").write_bytes(track)
    (pack / foundry.slot / "DMA1.JPK").write_bytes(dma)
    if output.exists():
        raise ValueError("Choose a new output directory")
    pack.rename(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="unmodified add-on from BuildRoadAmericaMod.py --include-a1-ring")
    parser.add_argument("output", type=Path, help="new directory for the four-course pack")
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError("Choose a new output directory")
        with TemporaryDirectory(dir=args.output.parent) as directory:
            build_pack(args.source, args.output.resolve(), Path(directory))
    except (OSError, ValueError, OverflowError, IndexError, KeyError, struct.error) as error:
        parser.exit(1, f"Foundry Oval setup failed: {error}\n")
    print(f"Added Foundry Oval ({LENGTH:.2f} m) to {args.output}")


if __name__ == "__main__":
    main()
