"""Regression checks for archive edits using synthetic payloads."""

import random
import struct
import unittest

from BuildRoadAmericaMod import unpack_lzss
from BuildTrackCollisionOverlay import encode_lzss, encode_lzss_compact
from ModAssets import find_member, replace_member


class ModAssetTests(unittest.TestCase):
    def test_equal_lengths_mark_a_raw_jpak_member_even_with_lzss_flag(self):
        package = self.package()
        member, _ = find_member(package, "ONE.DAT")
        self.assertEqual(member.read(package), b"AAAA")

    def test_growing_jpak_member_moves_the_next_entry_and_preserves_its_payload(self):
        package = self.package()
        replacement = bytes(range(80))
        edited = replace_member(package, ["one.dat"], replacement)
        first, _ = find_member(edited, "one.dat")
        second, _ = find_member(edited, "two.dat")
        self.assertEqual(len(edited), len(package))
        self.assertEqual(first.read(edited), replacement)
        self.assertNotEqual(second.offset, find_member(package, "two.dat")[0].offset)
        self.assertEqual(second.read(edited), b"BBBB")

    def test_compact_encoding_round_trips_across_the_ring_boundary(self):
        sample = bytes(random.Random(5).choices(range(9), k=5096)) + b"AABBAAAAABB" * 30
        compact = encode_lzss_compact(sample)
        self.assertLessEqual(len(compact), len(encode_lzss(sample)))
        self.assertEqual(bytes(unpack_lzss(compact, len(sample))), sample)

    @staticmethod
    def package():
        data = bytearray(512)
        struct.pack_into("<4sII", data, 0, b"JPAK", 0, 2)
        struct.pack_into("<8I", data, 32, 96, 4, 128, 4, 0, 0, 1, 0)
        struct.pack_into("<8I", data, 64, 104, 4, 192, 4, 0, 0, 1, 0)
        data[96:104] = b"one.dat\0"
        data[104:112] = b"two.dat\0"
        data[128:132] = b"AAAA"
        data[192:196] = b"BBBB"
        return bytes(data)


if __name__ == "__main__":
    unittest.main()
