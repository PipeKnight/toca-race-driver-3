"""Build a low-poly RD3 SHD from the dimensions of the RD2 DB5."""

import math
import struct

from BuildTrackGeometryOverlay import read_word
from Ps2CarModel import model_sections


def mesh_record(name, pivot, vertices, faces):
    center = tuple(sum(axis) / len(axis) for axis in zip(*vertices))
    indices, normals = bytearray(), bytearray()
    for i, j, k in faces:
        a, b, c = (vertices[index] for index in (i, j, k))
        ab, ac = (tuple(v - u for u, v in zip(a, p)) for p in (b, c))
        cross = (ab[1]*ac[2] - ab[2]*ac[1], ab[2]*ac[0] - ab[0]*ac[2], ab[0]*ac[1] - ab[1]*ac[0])
        size = math.hypot(*cross)
        if not size:
            raise ValueError("Degenerate shadow triangle")
        # SHD stores the outward normal with the opposite vertex winding.
        if sum(n * (p - middle) for n, p, middle in zip(cross, a, center)) > 0:
            j, k = k, j
            cross = tuple(-n for n in cross)
        indices.extend(struct.pack("<3I", i, j, k))
        normals.extend(struct.pack("<4f", *(-n / size for n in cross), 0.0))
    return (name.encode("ascii").ljust(64, b"\0") + struct.pack("<I4f", len(vertices), *pivot, 1.0)
            + b"".join(struct.pack("<4f", *p, 1.0) for p in vertices) + struct.pack("<I", len(faces))
            + indices + normals)


def linked_rings(rings):
    count = len(rings[0])
    vertices = tuple(p for ring in rings for p in ring)
    faces = [(0, j, j+1) for j in range(1, count-1)]
    for start in range(0, len(vertices) - count, count):
        for i in range(count):
            a, b = start + i, start + (i+1) % count
            faces.extend(((a, b, b+count), (a, b+count, a+count)))
    last = len(vertices) - count
    faces.extend((last, last+j, last+j+1) for j in range(1, count-1))
    return vertices, faces


def build_db5_shadow(model):
    _, base, _, sections = model_sections(model)
    start, end = sections[0]
    first, last = (p - base for p in struct.unpack_from("<2I", model, start+0x24))

    def part(slot):
        at = first + 0x30 * slot
        if not start <= at <= last-0x30 or read_word(model, at):
            raise ValueError(f"Missing DB5 shadow source part {slot}")
        draw = read_word(model, at+8) - base
        if not last <= draw <= end-0x60:
            raise ValueError("Invalid DB5 shadow source transform")
        low = struct.unpack_from("<3f", model, at+0x10)
        high = struct.unpack_from("<3f", model, at+0x20)
        pivot = struct.unpack_from("<3f", model, draw+0x50)
        return low, high, pivot

    front, rear, roof, base_body = (part(slot) for slot in (4, 39, 66, 0))
    low_z, high_z = rear[0][2], front[1][2]
    width = max(front[1][0], rear[1][0], base_body[1][0])
    low_y, high_y = base_body[0][1], max(front[1][1], rear[1][1] * .77)
    if not (4 < high_z-low_z < 5 and .7 < width < 1 and .15 < low_y < .3 and .8 < high_y < 1.1):
        raise ValueError("Unexpected DB5 body dimensions")

    # Taper the front and rear according to the DB5's body, not the DTM bumpers or wing.
    body = []
    for z, breadth, lift, top in ((0, .78, .10, .70), (.12, .96, .04, .86), (.35, .99, 0, .98),
                                  (.65, 1, 0, 1), (.88, .94, .04, .88), (1, .76, .12, .71)):
        at = low_z + (high_z-low_z)*z
        x = width*breadth
        bottom, upper = low_y + lift, low_y + (high_y-low_y)*top
        body.append(((-x*.88, bottom, at), (x*.88, bottom, at), (x, bottom+.10, at),
                     (x*.88, upper, at), (-x*.88, upper, at), (-x, bottom+.10, at)))
    origin = (0, 0, 0)
    records = [mesh_record("shadow_main_body", origin, *linked_rings(body))]

    low, high, _ = roof
    roof_rings = [tuple((x, y, z) for x, z in ((-width, rear_at), (width, rear_at),
                                             (width, front_at), (-width, front_at)))
                  for y, width, rear_at, front_at in
                  ((high_y*.95, .62, low[2]-.40, high[2]+.35),
                   (high[1], high[0]*.9, low[2]+.14, high[2]-.14))]
    records.append(mesh_record("shadow_roof", origin, *linked_rings(roof_rings)))

    for name, mount, tire in (("fl", 42, 46), ("fr", 48, 52), ("bl", 54, 58), ("br", 60, 64)):
        _, _, axle = part(mount)
        lo, hi, _ = part(tire)
        if not (0.5 < abs(axle[0]) < .9 and .2 < axle[1] < .5 and .5 < abs(axle[2]) < 2):
            raise ValueError("Unexpected DB5 wheel position")
        radius_y, radius_z = (hi[1]-lo[1])/2, (hi[2]-lo[2])/2
        pivot = axle if name.startswith("f") else origin
        x0, y0, z0 = (a-b for a, b in zip(axle, pivot))
        rings = [tuple((x0+x, y0+radius_y*math.cos(i*math.tau/8), z0+radius_z*math.sin(i*math.tau/8))
                       for i in range(8)) for x in (lo[0], hi[0])]
        records.append(mesh_record(f"shadow_{name}_alloy", pivot, *linked_rings(rings)))
    return struct.pack("<I", len(records)) + b"".join(records)
