"""Check indexed car body pages interleaved with mechanical textures."""

import struct
import unittest

from ConvertRd2CarModel import serialize_relocations
from Ps2CarTexture import TEXTURE_ROW_SIZE, UPLOAD_HEADER, body_uploads


class BodyPageTests(unittest.TestCase):
    def test_finds_livery_pages_after_an_unrelated_glass_descriptor(self):
        base, header, table = 0x8bd0bc0, 0x10, 0x20
        names = (b"vc_0_04", b"vc_0_02", b"vc_0_01", b"Etype_06", b"vc_0_03", b"dia_01")
        start = table + len(names) * TEXTURE_ROW_SIZE
        data = bytearray(start)
        entries = {0: 3, header + 4: 0, header + 8: 0}
        struct.pack_into("<3I", data, header, len(names), base + table, base + start)
        for index, name in enumerate(names):
            record = table + index * TEXTURE_ROW_SIZE
            struct.pack_into("<Q", data, record, (0x13 << 20) | (4 << 26) | (4 << 30))
            data[record + 0xec:record + 0xec + len(name)] = name
            for field, dimensions in ((0xcc, (8, 8)), (0xe8, (16, 16))):
                width, height = dimensions
                size = width * height * 4
                data.extend(UPLOAD_HEADER.pack(0x4000000000000001, 0xeeee, 0, 0x50, 0, 0x51,
                                               width | height << 32, 0x52, 0, 0x53, 2 << 58 | size // 16, 0))
                struct.pack_into("<I", data, record + field, base + len(data))
                entries[record + field] = 0
                data.extend(bytes([index]) * size)
        blob = serialize_relocations(data, entries, base)
        pages = body_uploads(blob)
        self.assertEqual({name: blob[bitmap.offset] for name, (bitmap, _) in pages.items()},
                         {b"04": 0, b"02": 1, b"01": 2, b"03": 4})


if __name__ == "__main__":
    unittest.main()
