"""Regression checks for transferring door UVs without moving the door skins."""

import struct
import unittest
from unittest.mock import patch

from BuildRd2Db5Variant import verify_wheel_lods
from ConvertRd2Db5Doors import paint_uv


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
