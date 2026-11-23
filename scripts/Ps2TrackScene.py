"""Inspect PS2 track materials and add authored OBJ triangles using a local material."""

from dataclasses import dataclass
import math
import struct

from BuildTrackGeometryOverlay import FOOTER, RELOCATION, TARGET_NODE_BYTES, VERTEX, WORD, read_word, vif_commands
from Ps2TrackCollision import read_triangles


ROOT_BYTES = 0x20
CHILD_FIELDS = range(0x50, 0x60, 4)
HEADER_OPERATIONS = (0x6C,) * 8 + (0x74, 0x6E, 0x68, 0x10, 0x17)
TRIANGLE_VERTICES = 3
FLUSHE = WORD.pack(0x10000000)
MSCNT = WORD.pack(0x17000000)


@dataclass(frozen=True)
class Material:
    root: int
    leaf: int
    prefix: bytes
    colors: bytes
    uv_word: int
    color_word: int
    position_word: int
    gif: int


class Scene:
    def __init__(self, data):
        count, self.size, self.base = FOOTER.unpack_from(data, len(data) - FOOTER.size)
        if not self.size or self.size % 16 or self.size + count * RELOCATION.size + FOOTER.size != len(data):
            raise ValueError("Invalid PS2 scene envelope")
        self.data = data
        self.rows = tuple(RELOCATION.iter_unpack(data[self.size:-FOOTER.size]))
        self.relocations = dict(self.rows)
        if (len(self.relocations) != count or any(offset % 4 or offset + 4 > self.size for offset in self.relocations)
                or self.relocations.get(0) != 0):
            raise ValueError("Invalid PS2 scene relocations")
        self.roots = []
        address = self.word(0)
        seen = set()
        while address:
            root = address - self.base
            if root in seen or not 0 <= root <= self.size - ROOT_BYTES:
                raise ValueError("Invalid PS2 scene root chain")
            if any(self.relocations.get(root + field) != 0 for field in (4, 8, 24)):
                raise ValueError("Invalid PS2 scene root pointer")
            seen.add(root)
            self.roots.append(root)
            address = self.word(root + 24)
        if not self.roots:
            raise ValueError("PS2 scene contains no display-list roots")

    def word(self, offset):
        return read_word(self.data, offset)

    def leaves(self, root):
        pending = [self.word(root + 4) - self.base]
        seen = set()
        while pending:
            node = pending.pop()
            if node in seen:
                continue
            if not 0 <= node <= self.size - TARGET_NODE_BYTES or self.relocations.get(node) != 3:
                raise ValueError("Unexpected PS2 scene node")
            seen.add(node)
            flag = self.word(node + 0x60)
            if flag == 1:
                yield node
                continue
            if flag != 0:
                raise ValueError("Unexpected PS2 scene node flags")
            for field in CHILD_FIELDS:
                child = self.word(node + field)
                if child:
                    if self.relocations.get(node + field) != 0:
                        raise ValueError("Invalid PS2 scene child pointer")
                    pending.append(child - self.base)

    def material(self, root, leaf):
        tag = self.word(leaf)
        packet_address = self.word(leaf + 4)
        packet = packet_address - self.base
        length = (tag & 0xffff) * 16
        if ((tag >> 28) & 7 != 3 or not 0 <= packet < packet + length <= self.size
                or self.word(leaf + 0x40) != length or self.word(leaf + 0x48) != packet_address
                or self.relocations.get(leaf + 0x48) != 0):
            raise ValueError("Unsupported material DMA leaf")
        commands = []
        for command in vif_commands(self.data, packet, packet + length):
            if command.operation == 0x10 and not commands:
                continue
            if command.operation:
                commands.append(command)
            if command.operation == 0x17 or len(commands) > len(HEADER_OPERATIONS):
                break
        if tuple(c.operation for c in commands) != HEADER_OPERATIONS:
            raise ValueError("Unsupported first material VIF batch")
        descriptor, *registers, uv, color, position, _, _ = commands
        bank, vertices, layout, _ = struct.unpack_from("<4I", self.data, descriptor.payload)
        gif = registers[-1].payload
        giftag, gif_registers = struct.unpack_from("<2Q", self.data, gif)
        if (descriptor.immediate != 0x8000 or descriptor.count != 1
                or bank not in (0x100, 0x200, 0x300) or layout != bank + 7
                or [command.immediate for command in registers] != list(range(bank, bank + 7))
                or any(command.count != 1 for command in registers)
                or not 3 <= vertices <= 255 or (giftag & 0x7fff) != vertices
                or not giftag & (1 << 46) or giftag >> 47 & 7 != 4 or gif_registers != 0x512
                or [uv.immediate, color.immediate, position.immediate] != [bank + i for i in (7, 8, 9)]
                or any(command.count != vertices for command in (uv, color, position))
                or any(packet <= offset < position.payload + position.size for offset, _ in self.rows)):
            raise ValueError("Unsupported textured strip layout")
        header_at = descriptor.payload - 4
        before_attributes = self.data[header_at:uv.payload - 4]
        colors = self.data[color.payload:color.payload + 12]
        return Material(root, leaf, before_attributes, colors,
                        self.word(uv.payload - 4), self.word(color.payload - 4),
                        self.word(position.payload - 4), gif - header_at)


def scene_info(args):
    scene = Scene(args.input.read_bytes())
    x, z = args.near
    if not all(math.isfinite(v) for v in (x, z)):
        raise ValueError("Expected finite X/Z search coordinates")
    print(f"{'Root':>10} {'Material leaf':>14} {'Distance in X/Z':>17}")
    for root in scene.roots:
        supported = []
        for leaf in scene.leaves(root):
            try:
                scene.material(root, leaf)
            except ValueError:
                continue
            xmin, _, zmin = VERTEX.unpack_from(scene.data, leaf + 0x20)
            xmax, _, zmax = VERTEX.unpack_from(scene.data, leaf + 0x30)
            distance = math.hypot(max(xmin - x, 0, x - xmax), max(zmin - z, 0, z - zmax))
            supported.append((distance, leaf))
        if supported:
            distance, leaf = min(supported)
            print(f"{root:#10x} {leaf:#14x} {distance:15.2f} m")


def triangle_batch(material, vertices, low, high, rgb):
    batch = bytearray(material.prefix)
    WORD.pack_into(batch, 8, TRIANGLE_VERTICES)
    tag = read_word(batch, material.gif)
    WORD.pack_into(batch, material.gif, (tag & ~0x7fff) | TRIANGLE_VERTICES)
    uv = bytearray()
    for x, _, z in vertices:
        s = (x - low[0]) / (high[0] - low[0]) if high[0] != low[0] else 0
        t = (z - low[2]) / (high[2] - low[2]) if high[2] != low[2] else 0
        uv.extend(struct.pack("<2f", s, t))
    colors = material.colors if rgb is None else b"".join(bytes((*rgb, alpha)) for alpha in material.colors[3::4])
    positions = b"".join(VERTEX.pack(*point) for point in vertices)
    for command, payload in ((material.uv_word, uv), (material.color_word, colors), (material.position_word, positions)):
        batch.extend(WORD.pack((command & ~0xff0000) | (TRIANGLE_VERTICES << 16)))
        batch.extend(payload)
    batch.extend(FLUSHE + MSCNT)
    # Finish the previous triangle before reusing its VU buffer.
    batch = FLUSHE + batch
    return batch + bytes(-len(batch) % 16)


def scene_append(args):
    scene = Scene(args.input.read_bytes())
    if args.root not in scene.roots or args.leaf not in scene.leaves(args.root):
        raise ValueError("Material leaf is not in the selected scene root")
    material = scene.material(args.root, args.leaf)
    vertices, faces = read_triangles(args.obj)
    if args.rgb is not None and not all(0 <= channel <= 255 for channel in args.rgb):
        raise ValueError("Expected RGB values from 0 through 255")
    if not math.isfinite(args.offset_y):
        raise ValueError("Expected a finite Y offset")
    vertices = [(x, y + args.offset_y, z) for x, y, z in vertices]
    if not all(math.isfinite(v) and abs(v) <= 100000 for point in vertices for v in point):
        raise ValueError("Invalid authored scene coordinate")
    vertices = [VERTEX.unpack(VERTEX.pack(*point)) for point in vertices]
    used = {index for face in faces for index in face}
    low = tuple(min(vertices[i][axis] for i in used) for axis in range(3))
    high = tuple(max(vertices[i][axis] for i in used) for axis in range(3))
    packet = bytearray()
    for face in faces:
        points = tuple(vertices[index] for index in face)
        if len(set(points)) != 3:
            raise ValueError("An OBJ face repeats a vertex")
        packet.extend(triangle_batch(material, points, low, high, args.rgb))
        if len(packet) // 16 > 0xffff:
            raise ValueError("The authored mesh exceeds a single PS2 DMA leaf")
    packet_at = scene.size
    leaf_at = packet_at + len(packet)
    root_at = leaf_at + TARGET_NODE_BYTES
    leaf = bytearray(scene.data[material.leaf:material.leaf + TARGET_NODE_BYTES])
    WORD.pack_into(leaf, 0, (read_word(leaf, 0) & ~0xffff) | (len(packet) // 16))
    WORD.pack_into(leaf, 4, scene.base + packet_at)
    WORD.pack_into(leaf, 0x40, len(packet))
    WORD.pack_into(leaf, 0x48, scene.base + packet_at)
    VERTEX.pack_into(leaf, 0x20, *low)
    VERTEX.pack_into(leaf, 0x30, *high)
    root = bytearray(scene.data[material.root:material.root + ROOT_BYTES])
    WORD.pack_into(root, 0, len(packet))
    WORD.pack_into(root, 4, scene.base + leaf_at)
    WORD.pack_into(root, 8, scene.base + packet_at)
    result = bytearray(scene.data[:scene.size])
    WORD.pack_into(result, material.root + 24, scene.base + root_at)
    result.extend(packet + leaf + root)
    rows = list(scene.rows)
    for old, new, length in ((material.leaf, leaf_at, TARGET_NODE_BYTES), (material.root, root_at, ROOT_BYTES)):
        rows.extend((new + i, scene.relocations[old + i]) for i in range(0, length, 4)
                    if old + i in scene.relocations)
    size = len(result)
    result.extend(b"".join(RELOCATION.pack(*row) for row in rows))
    result.extend(FOOTER.pack(len(rows), size, scene.base))
    with args.output.open("xb") as stream:
        stream.write(result)
