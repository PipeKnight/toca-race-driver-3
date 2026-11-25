"""Regression checks for translated RD2 exterior mesh packets."""

import struct
import unittest

from ConvertRd2CarModel import align16, serialize_relocations, translate_vu_banks
from Ps2CarModel import STREAM_HEADER, relocation_table


class Rd2CarMeshTests(unittest.TestCase):
    def test_translate_each_strip_bank_and_keep_the_call_relocation(self):
        for donor, target in ((42, 176), (369, 458), (696, 740)):
            with self.subTest(bank=donor):
                normal = donor + 323
                header = struct.pack("<9I", STREAM_HEADER, donor, donor, donor + 1,
                                     3, normal, 0, 0, 0)
                position = struct.pack("<I9f", 0x68038000 | (donor + 3), *range(9))
                normals = struct.pack("<I9f", 0x68038000 | normal, *range(9, 18))
                call = len(header) + len(position) + len(normals)
                data = header + position + normals + struct.pack("<I", 0x142e0007)
                mesh = serialize_relocations(data.ljust(align16(len(data)), b"\0"), {call: 4}, 0x00400000)
                translated = translate_vu_banks(mesh)

                self.assertEqual(relocation_table(translated), relocation_table(mesh))
                self.assertEqual(struct.unpack_from("<9I", translated),
                                 (STREAM_HEADER, target, target, target + 1, 3, target + 278, 0, 0, 0))
                self.assertEqual(struct.unpack_from("<I", translated, len(header))[0],
                                 0x68038000 | (target + 3))
                self.assertEqual(struct.unpack_from("<I", translated, len(header) + len(position))[0],
                                 0x68038000 | (target + 278))
                self.assertEqual(struct.unpack_from("<I", translated, call)[0], 0x14000007)
                self.assertEqual(translated[len(header) + 4:len(header) + len(position)], position[4:])


if __name__ == "__main__":
    unittest.main()
