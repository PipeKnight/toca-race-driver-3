"""Regression checks for repainting the DB5 without moving the door skins."""

import math
import struct
import unittest
from unittest.mock import patch

from BuildRd2Db5Variant import verify_wheel_lods
from ConvertRd2Db5Doors import BODY_TEX0, UV, VERTEX, DoorStreams, paint_doors, paint_normal, paint_uv
from Ps2CarModel import MeshPacket


class DoorPaintTests(unittest.TestCase):
    def test_project_paint_across_the_door_thickness(self):
        paint = (((0.025, 0., 0.), (.1, .7)), ((-0.018, 0., 1.), (.5, .7)),
                 ((-0.040, 1., 0.), (.1, .9)), ((0.012, 1., 1.), (.5, .9)))
        u, v = paint_uv(.5, .5, paint)
        self.assertAlmostEqual(u, .3)
        self.assertAlmostEqual(v, .8)
        # The two shell surfaces differ in X, but meet the same UV at a shared Y/Z corner.
        u, v = paint_uv(0., 1., paint)
        self.assertAlmostEqual(u, .5, places=3)
        self.assertAlmostEqual(v, .7, places=3)

    def test_paint_normal_is_normalized_after_blending(self):
        samples = (((0., -.1, 0.), (1., 0., 0.)), ((0., .1, 0.), (.6, .8, 0.)))
        normal = paint_normal(0., 0., samples)
        self.assertAlmostEqual(math.hypot(*normal), 1.)
        self.assertAlmostEqual(normal[1] / normal[0], .5)

    def test_rebinds_inward_trim_normals_on_both_sides_without_moving_vertices(self):
        mesh = bytearray(320)
        groups = []
        for offset, side in ((0, -1), (160, 1)):
            inner = MeshPacket(offset + 32, offset + 44, offset + 56, 1, True)
            outer = MeshPacket(offset + 72, offset + 96, offset + 120, 2, True)
            VERTEX.pack_into(mesh, inner.position, 0., 0., 0.)
            VERTEX.pack_into(mesh, inner.normal, -side, 0., 0.)
            for i, normal in enumerate(((side, 0., 0.), (-side, 0., 0.))):
                VERTEX.pack_into(mesh, outer.position + i * 12, 0., float(i), 0.)
                VERTEX.pack_into(mesh, outer.normal + i * 12, *normal)
                UV.pack_into(mesh, outer.uv + i * 8, .25, .75)
            groups.append(DoorStreams([inner], [outer], [offset, offset + 8, offset + 16], (), None, None, []))
        with patch("ConvertRd2Db5Doors.door_streams", return_value=iter(groups)):
            repainted = paint_doors(b"", mesh, b"")
        for side, door in zip((-1, 1), groups, strict=True):
            inner, = door.trim
            outer, = door.paint
            self.assertEqual(tuple(struct.unpack_from("<Q", repainted, at)[0] for at in door.trim_textures), BODY_TEX0)
            self.assertEqual(UV.unpack_from(repainted, inner.uv), (.25, .75))
            self.assertEqual(VERTEX.unpack_from(repainted, inner.normal), (side, 0., 0.))
            self.assertEqual(repainted[inner.position:inner.normal], mesh[inner.position:inner.normal])
            self.assertEqual(repainted[outer.position:outer.uv + 2 * UV.size],
                             mesh[outer.position:outer.uv + 2 * UV.size])

    def test_class_doors_use_the_panel_texture_and_keep_the_reflection_packet_size(self):
        mesh = bytearray(400)
        groups = []
        textures = (0x2007e085e131349c, 0x2007f085e1313a0e, 0x20000085e1310080)
        for offset, side in ((0, -1), (200, 1)):
            trim = MeshPacket(offset + 0x80, offset + 0x8c, offset + 0x98, 1, True)
            paint = MeshPacket(offset + 0xa0, offset + 0xac, offset + 0xb8, 1, True)
            VERTEX.pack_into(mesh, paint.normal, side, 0., 0.)
            UV.pack_into(mesh, paint.uv, .5, .75)
            mesh[offset + 32:offset + 64] = bytes(range(32))
            struct.pack_into("<QQ", mesh, offset + 80, 0x312e400000008001, 0x512)
            groups.append(DoorStreams([trim], [paint], [offset, offset + 8, offset + 16],
                                      textures, offset + 96, offset + 32, [offset + 80]))
        with patch("ConvertRd2Db5Doors.door_streams", return_value=iter(groups)):
            actual = paint_doors(b"", mesh, b"", (1,))
        for offset in (0, 200):
            self.assertEqual(struct.unpack_from("<3Q", actual, offset), textures)
            self.assertEqual(actual[offset + 96:offset + 128], mesh[offset + 32:offset + 64])
            self.assertEqual(struct.unpack_from("<QQ", actual, offset + 80), (0x312e400000008001, 0xd12))


class WheelLodTests(unittest.TestCase):
    def test_bundle_rejects_wheel_pivot_changes_and_matrix_slot_changes(self):
        slots = (42, 48, 54, 60, 46, 52, 58, 64)
        size, base = 0x800, 0x1000000
        mesh = bytearray(5 * size)
        table = [[0xffffffff] * 320 for _ in range(5)]
        sections = []
        for lod in range(5):
            start = lod * size
            first = start + 0x40
            draw = first + 0x30 * len(slots)
            sections.append((start, start + size))
            struct.pack_into("<2I", mesh, start + 0x24, base + first, base + draw)
            if lod == 4:
                continue
            for index, slot in enumerate(slots):
                table[lod][slot] = index
                struct.pack_into("<I", mesh, first + index * 0x30 + 8, base + draw + index * 0xa0)
                struct.pack_into("<3fI", mesh, draw + index * 0xa0 + 0x50, 0., 0.25, 1., 3 if index < 4 else 6)
        lod_three = 3 * size + 0x40 + 0x30 * len(slots)
        with patch("BuildRd2Db5Variant.model_sections", return_value=(0, base, {}, sections)), \
                patch("BuildRd2Db5Variant.read_part_map", return_value=table):
            verify_wheel_lods(mesh, b"")
            struct.pack_into("<f", mesh, lod_three + 0x54, 0.26)
            with self.assertRaisesRegex(ValueError, "wheel pivot moves"):
                verify_wheel_lods(mesh, b"")
            struct.pack_into("<f", mesh, lod_three + 0x54, 0.25)
            struct.pack_into("<I", mesh, lod_three + 0x5c, 2)
            with self.assertRaisesRegex(ValueError, "wheel matrix index"):
                verify_wheel_lods(mesh, b"")
