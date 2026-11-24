"""Keep existing sound members on the same offsets within disc sectors."""

import struct
import unittest

from BuildRd2Db5Variant import BIGF_ENTRY, SECTOR_SIZE, append_sound_members
from BuildRoadAmericaMod import read_bigf


class SoundLayoutTests(unittest.TestCase):
    def archive(self, base):
        # Cross a sector boundary to detect a repack that shifts existing members.
        archive = bytearray(base + 3000)
        struct.pack_into("<4sII", archive, 0, b"BIGF", 2, base)
        BIGF_ENTRY.pack_into(archive, 0x24, b"stock.ini", 700, 93)
        BIGF_ENTRY.pack_into(archive, 0x24 + BIGF_ENTRY.size, b"stock.msc", 2000, 899)
        archive[base + 93:base + 793] = b"A" * 700
        archive[base + 899:base + 2899] = b"B" * 2000
        return bytes(archive)

    def test_preserves_directory_offsets_and_sector_phase_when_directory_grows(self):
        old_base = 85
        old = self.archive(old_base)
        new = append_sound_members(old, 2, {b"DB5.ini": b"new"})
        entries, new_base = read_bigf(new, 3)
        self.assertEqual(new_base, old_base + SECTOR_SIZE)
        end = 0x24 + 2 * BIGF_ENTRY.size
        self.assertEqual(new[0x24:end], old[0x24:end])
        self.assertEqual(new[new_base:new_base + len(old) - old_base], old[old_base:])
        self.assertEqual(entries, {**read_bigf(old, 2)[0], b"DB5.ini": b"new"})

    def test_leaves_base_in_place_when_directory_fits_and_rejects_collisions(self):
        old = self.archive(256)
        new = append_sound_members(old, 2, {b"DB5.ini": b"new"})
        self.assertEqual(read_bigf(new, 3)[1], 256)
        with self.assertRaisesRegex(ValueError, "already contains stock.INI"):
            append_sound_members(old, 2, {b"stock.INI": b"replacement"})
