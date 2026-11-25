"""Exercise the CP3D packet reader and cockpit palette conversion."""

import struct
from types import SimpleNamespace
import unittest

from ConvertRd2LancerCockpit import close_wheel_rim, clut_slot, combine_atlas
from Rd2Ps2Cockpit import draw_strips


def cockpit_packet(kind, following):
    def vif(op, count, data=b""):
        return struct.pack("<I", op << 24 | count << 16) + data + bytes(-len(data) % 4)

    points = ((0., 0., 0.), (1., 0., 0.), (0., 1., 0.))
    uvs = ((0., 0.), (.25, 0.), (0., 1.))
    commands = (vif(0x6c, 2, struct.pack("<8I", 3, 302, 0, 12, 0, 0, 1, 2))
                + vif(0x68, 3, b"".join(struct.pack("<3f", *point) for point in points))
                + vif(0x6e, 3, b"\x80" * 12)
                + vif(0x64, 3, b"".join(struct.pack("<2f", *uv) for uv in uvs))
                + vif(0x69, 3, bytes(18)) + vif(0x17, 0))
    commands += bytes(-(12 + len(commands)) % 16)
    length = (len(commands) - 4) // 16
    return struct.pack("<3I", kind << 28 | length, following, 0) + commands, (points, uvs)


def tim2(size, color):
    head = bytearray(256)
    head[:6] = b"TIM2\x04\x01"
    struct.pack_into("<IIHH", head, 0x84, 256 * len(color), size * size, 128, 256)
    struct.pack_into("<HH", head, 0x94, size, size)
    return bytes(head) + b"\x01" * (size * size) + bytes(len(color)) + color + bytes(254 * len(color))


def digits_tim2():
    head = bytearray(256)
    head[:6] = b"TIM2\x04\x01"
    struct.pack_into("<IIHH", head, 0x84, 128, 8192, 128, 16)
    head[0x92:0x98] = b"\x03\x04\x80\x00\x80\x00"
    return bytes(head) + b"\x22" * 8192 + bytes(8) + b"\x08\x09\x0a\x80" + bytes(116)


class Rd2Ps2CockpitTests(unittest.TestCase):
    def test_cp3d_packet_preserves_positions_and_texture_coordinates(self):
        packet, strip = cockpit_packet(6, 0)
        data = bytes(0x140) + packet
        self.assertEqual(tuple(draw_strips(data, 0x140, len(data))), (strip,))

    def test_cp3d_packet_reader_rejects_cyclic_links(self):
        packet, _ = cockpit_packet(2, 0x140)
        data = bytes(0x140) + packet
        with self.assertRaisesRegex(ValueError, "draw chain"):
            tuple(draw_strips(data, 0x140, len(data)))

    def test_wheel_atlas_expands_rgb_palette_and_keeps_the_two_halves_separate(self):
        stock = bytes((50, 100, 150, 64))
        donor = bytes((200, 180, 160))
        pixels, palette = combine_atlas(tim2(128, stock), tim2(256, donor), digits_tim2())
        self.assertEqual(pixels[:96 * 128], (bytes(64) + b"\x80" * 64) * 96)
        self.assertEqual(pixels[96 * 128:97 * 128], bytes(64) + b"\x80" * 32 + b"\xf2" * 32)
        self.assertEqual(pixels[-32:], b"\xf0" * 32)
        self.assertEqual(palette[:4], stock)
        at = clut_slot(128) * 4
        self.assertEqual(palette[at:at + 4], donor + b"\x80")
        at = clut_slot(242) * 4
        self.assertEqual(palette[at:at + 4], b"\x08\x09\x0a\x80")

    def test_upper_rim_joins_the_actual_open_endpoints(self):
        right = tuple((.10 - i * .004, .10 - i * .004, .001 * i) for i in range(5))
        left = tuple((-x - .002, y, z) for x, y, z in right)
        uvs = tuple((.20, .80 + .04 * i) for i in range(5))
        strips = []
        wheel = SimpleNamespace(add=lambda points, texcoords: strips.append((points, texcoords)))
        close_wheel_rim(wheel, ((right, uvs), (left, uvs)))
        self.assertEqual(len(strips), 5)
        for i, (points, texcoords) in enumerate(strips):
            following = (i + 1) % len(right)
            self.assertEqual(points[:2], (right[i], right[following]))
            self.assertEqual(points[-2:], (left[i], left[following]))
            self.assertEqual(len(points), len(texcoords))
        self.assertGreater(max(point[1] for point in strips[0][0]), .14)


if __name__ == "__main__":
    unittest.main()
