"""Fit the DB5's trim, steering wheel, and mirrors to the RD3 cockpit scene."""

import math
import struct
from types import SimpleNamespace

from BuildTrackGeometryOverlay import read_word
from ConvertRd2Db5Cockpit import db5_draw_parts, replace_draw_strips
from Ps2CarModel import UV, VERTEX
from Ps2CockpitModel import cockpit_nodes, cockpit_sections


NO_NODE = 0xffffffff
IDENTITY = struct.pack("<16f", 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)


class Cabin:
    def __init__(self, target):
        self.target = target
        self.sections = cockpit_sections(target)
        table_at, records = cockpit_nodes(target)
        self.names = [name for name, _ in records]
        self.references = dict(records)
        self.scene = read_word(target, 0x20)
        self.header = bytearray(target[:self.scene + 40])
        pos = self.scene + 44 + read_word(target, self.scene + 36)
        self.nodes = []
        for _, refs in records:
            size = 80 + 4 * len(refs)
            self.nodes.append(bytearray(target[pos:pos + size]))
            pos += size
        count = read_word(target, pos)
        if read_word(target, 16) != 1 or pos + 4 + 4 * count != table_at:
            raise ValueError("Expected one cockpit draw list")
        self.draw_list = list(struct.unpack_from(f"<{count}I", target, pos + 4))
        self.draws = [target[a - 40:b] for a, b in self.sections]

    def node(self, name):
        try:
            return self.nodes[self.names.index(name)]
        except ValueError:
            raise ValueError(f"The cockpit template does not contain {name}") from None

    def draw(self, section, mesh, strips):
        start, end = self.sections[section]
        payload, low, high = replace_draw_strips(self.target, start, end, mesh, strips)
        header = bytearray(self.target[start - 40:start])
        struct.pack_into("<6f", header, 8, *low, *high)
        struct.pack_into("<I", header, 36, len(payload))
        return bytes(header + payload)

    def replace(self, name, mesh, strips):
        section, = self.references[name]
        self.draws[section] = self.draw(section, mesh, strips)

    def append(self, name, parent_name, matrix, mesh, strips):
        if name in self.names:
            raise ValueError(f"The cockpit already contains {name}")
        parent = self.node(parent_name)
        index = len(self.nodes)
        sibling = read_word(parent, 4)
        struct.pack_into("<I", parent, 4, index)
        record = (struct.pack("<3I", self.names.index(parent_name), NO_NODE, sibling)
                  + matrix + struct.pack("<2I", 1, len(self.draws)))
        self.names.append(name)
        self.nodes.append(record)
        self.draw_list.append(index)
        self.draws.append(self.draw(1, mesh, strips))

    def encode(self):
        names = b"".join(name.encode("ascii") + b"\0" for name in self.names)
        names += bytes(-len(names) % 4)
        struct.pack_into("<I", self.header, self.scene + 36, len(names))
        for offset in (8, 28):
            struct.pack_into("<I", self.header, offset, len(self.draws))
        output = (bytes(self.header) + names + struct.pack("<I", len(self.nodes)) + b"".join(self.nodes)
                  + struct.pack(f"<{len(self.draw_list) + 1}I", len(self.draw_list), *self.draw_list)
                  + b"".join(self.draws) + bytes(4))
        cockpit_sections(output)
        return output


class Strips:
    def __init__(self):
        self.mesh = bytearray()
        self.strips = []

    def add(self, points, texcoords):
        start = len(self.mesh)
        self.mesh.extend(b"".join(VERTEX.pack(*point) for point in points))
        uv = len(self.mesh)
        self.mesh.extend(b"".join(UV.pack(*point) for point in texcoords))
        self.strips.append(SimpleNamespace(count=len(points), position=start, uv=uv))


def wheel_shape(image, palette, width, height):
    clut = [palette[i:i + 4] for i in range(0, len(palette), 4)]
    colors = [clut[(i & ~24) | ((i & 8) << 1) | ((i & 16) >> 1)] for i in range(256)]

    def swatch(level):
        candidates = (i for i, pixel in enumerate(image) if colors[pixel][3] == 128)
        index = min(candidates, key=lambda i: sum((c - level)**2 for c in colors[image[i]][:3]))
        return ((index % 128 + .5) / 128, (index // 128 + .5) / 128)

    def circle(angle, radius, z=0):
        return math.cos(angle) * radius, math.sin(angle) * radius, z

    result = Strips()

    def add(points, uv):
        xyz = [(x * width, y * height, (z - y * .36) * width) for x, y, z in points]
        result.add(xyz, (uv,) * len(xyz))

    rubber, alloy, hub = (swatch(level) for level in (30, 115, 50))
    for i in range(24):
        a, b = (math.tau * k / 24 for k in (i, i + 1))
        add([circle(a, 1), circle(a, .82), circle(b, 1), circle(b, .82)], rubber)
        add([circle(a, 1, .08), circle(a, 1), circle(b, 1, .08), circle(b, 1)], rubber)
    for angle in (math.tau / 8, 3 * math.tau / 8, 6 * math.tau / 8):
        x, y = math.cos(angle), math.sin(angle)
        add([(x * r - y * w, y * r + x * w, .015)
             for r, w in ((.10, .063), (.10, -.063), (.85, .107), (.85, -.107))], alloy)
    for i in range(8):
        a, b = (math.tau * k / 8 for k in (i, i + 1))
        add([(0, 0, -.04), circle(a, .24, -.04), circle(b, .24, -.04)], hub)
    return result


def strip_positions(mesh, strip):
    return tuple(VERTEX.iter_unpack(mesh[strip.position:strip.position + strip.count * VERTEX.size]))


def rear_mirror(cabin, mesh, strips):
    face = strip_positions(mesh, strips[-1])
    pivot = tuple(sum(axis) / len(axis) for axis in zip(*face))
    xx = sum((x - pivot[0])**2 for x, _, _ in face)
    xz = sum((x - pivot[0]) * (z - pivot[2]) for x, _, z in face)
    angle = math.atan2(xz, xx)
    cosine, sine = math.cos(angle), math.sin(angle)

    def local(point):
        x, y, z = (v - o for v, o in zip(point, pivot))
        return x * cosine + z * sine, y, -x * sine + z * cosine

    face = tuple(map(local, face))
    left, right = min(p[0] for p in face), max(p[0] for p in face)
    bottom, top = min(p[1] for p in face), max(p[1] for p in face)
    if min(right - left, top - bottom) < .01:
        raise ValueError("Invalid DB5 mirror glass dimensions")
    glass = Strips()
    glass.add(face, [(.01 + .98 * (right - x) / (right - left), .02 + .96 * (top - y) / (top - bottom))
                     for x, y, _ in face])

    mount = Strips()
    for strip in strips[:-1]:
        texcoords = UV.iter_unpack(mesh[strip.uv:strip.uv + strip.count * UV.size])
        mount.add(tuple(map(local, strip_positions(mesh, strip))), texcoords)
    cabin.node("int_rear_mirror_mount")[12:76] = struct.pack(
        "<16f", cosine, 0, sine, 0, 0, 1, 0, 0, -sine, 0, cosine, 0, *pivot, 1)
    cabin.node("int_rear_mirror")[12:76] = IDENTITY
    cabin.replace("int_rear_mirror_mount", mount.mesh, mount.strips)
    cabin.replace("int_rear_mirror", glass.mesh, glass.strips)


def convert_cabin(interior_model, interior_mesh, donor_model, donor_mesh, target, image, palette):
    cabin = Cabin(target)
    parts = db5_draw_parts(interior_model, interior_mesh, {119: 64, 12: 24, 13: 26})
    shell = parts[119][1]
    cabin.replace("int_main_body", interior_mesh, shell[:48])
    rear_mirror(cabin, interior_mesh, shell[48:])
    for side, slot, sign in (("l", 12, -1), ("r", 13, 1)):
        name = side + "_door"
        door = cabin.node(name)
        matrix, strips = parts[slot]
        old = struct.unpack_from("<3f", door, 60)
        new = struct.unpack_from("<3f", matrix, 48)
        cabin.replace(name, interior_mesh, strips)
        door[12:76] = matrix
        child = read_word(door, 4)
        while child != NO_NODE:
            node = cabin.nodes[child]
            current = struct.unpack_from("<3f", node, 60)
            struct.pack_into("<3f", node, 60, *(a + b - c for a, b, c in zip(current, old, new)))
            child = read_word(node, 8)
        # Keep the template's side-mirror reflection states and fit their housings to the DB5 door frame.
        wing = cabin.node(side + "_wing_mirror")
        pose = list(struct.unpack_from("<16f", wing, 12))
        for index in (0, 1, 2, 4, 5, 6, 8, 9, 10):
            pose[index] *= .78
        pose[12:15] = [target - origin for target, origin in zip((sign * .86, .90, .77), new)]
        struct.pack_into("<16f", wing, 12, *pose)

    matrix, (donor_wheel,) = db5_draw_parts(donor_model, donor_mesh, {11: 1})[11]
    points = strip_positions(donor_mesh, donor_wheel)
    width, height = (max(abs(point[axis]) for point in points) for axis in (0, 1))
    wheel = wheel_shape(image, palette, width, height)
    mount = bytearray(matrix)
    struct.pack_into("<f", mount, 56, .10)
    cabin.append("steering_wheel", "int_main_body", mount, wheel.mesh, wheel.strips)
    return cabin.encode()
