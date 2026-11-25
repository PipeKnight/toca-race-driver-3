"""Regression checks for translated RD2 exterior mesh packets."""

import struct
import unittest

from BuildTrackGeometryOverlay import vif_commands
from ConvertRd2CarModel import align16, serialize_relocations, split_triple_pass_strip, translate_vu_banks
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

    def test_split_triple_pass_strip_preserves_attributes_and_three_gif_tags(self):
        bank, count = 42, 30
        uv, normal = bank + 9, bank + 326 - count
        second, third = bank + 3 * count + 12, bank + 6 * count + 15
        header = struct.pack("<9I", STREAM_HEADER, bank, bank + 2, uv, count, normal, third, second, 0)
        gif = struct.pack("<QQ", 0x302e4000_00000000 | count, 0x512)
        first_pass = struct.pack("<I", 0x6c010000 | bank + 8) + gif
        reflection = struct.pack("<4Q", 0x1000000000000001, 0xe, 0x101, 7)
        passes = b"".join(struct.pack("<I", 0x6c030000 | address - 3) + reflection + gif
                          for address in (second, third))
        texcoords = struct.pack("<I60f", 0x641e0000 | uv, *range(60))
        positions = struct.pack("<I90f", 0x681e0000 | uv + 2, *range(90))
        normals = struct.pack("<I90f", 0x681e0000 | normal, *range(90, 180))
        call = struct.pack("<I", 0x142e0003)
        mesh = header + first_pass + passes + texcoords + positions + normals + call

        pieces = split_triple_pass_strip(mesh, 0, list(vif_commands(mesh, 0, len(mesh))))

        self.assertEqual(len(pieces), 2)
        for part, first, vertices in zip(pieces, (0, 22), (24, 8)):
            with self.subTest(first_vertex=first):
                fields = struct.unpack_from("<9I", part)
                self.assertEqual(fields[4:8], (vertices, bank + 326 - vertices,
                                               bank + 6 * vertices + 15, bank + 3 * vertices + 12))
                _, draw, reflected, reflected_final, tex, pos, norm, execute = vif_commands(part, 0, len(part))
                self.assertEqual([reflected.immediate, reflected_final.immediate], [fields[7] - 3, fields[6] - 3])
                for command in (draw, reflected, reflected_final):
                    self.assertEqual(struct.unpack_from("<QQ", part, command.payload + command.size - 16),
                                     (0x302e4000_00000000 | vertices, 0x512))
                for command, stride, offset in ((tex, 2, 0), (pos, 3, 0), (norm, 3, 90)):
                    self.assertEqual(struct.unpack_from(f"<{vertices * stride}f", part, command.payload),
                                     tuple(range(offset + first * stride, offset + (first + vertices) * stride)))
                self.assertEqual(part[execute.payload - 4:execute.payload], call)


if __name__ == "__main__":
    unittest.main()
