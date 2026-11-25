"""Copy PS2 indexed car body textures into an existing upload layout."""

from dataclasses import dataclass
import struct

from Ps2CarModel import relocation_table


BODY_PAGES = {b"01", b"02", b"03", b"04"}
TEXTURE_ROW_SIZE = 0x170
UPLOAD_HEADER = struct.Struct("<12Q")


@dataclass(frozen=True)
class ImageUpload:
    offset: int
    width: int
    height: int

    @property
    def size(self):
        return self.width * self.height * 4

    @property
    def end(self):
        return self.offset + self.size


def image_upload(data, offset, payload_start, payload_end):
    start = offset - UPLOAD_HEADER.size
    if start < payload_start or offset % 16 or offset > payload_end:
        raise ValueError("Car texture upload header is outside the pixel payload")
    tag, registers, blit, reg0, position, reg1, region, reg2, direction, reg3, image, _ = (
        UPLOAD_HEADER.unpack_from(data, start)
    )
    if (tag != 0x4000000000000001 or registers != 0xeeee or (reg0, reg1, reg2, reg3) != (0x50, 0x51, 0x52, 0x53)
            or blit >> 56 & 0x3f or position or direction or image >> 58 & 3 != 2):
        raise ValueError("Expected a direct 32-bit GIF car texture upload")
    upload = ImageUpload(offset, region & 0xfff, (region >> 32) & 0xfff)
    if not upload.size or upload.size != (image & 0x7fff) * 16 or upload.end > payload_end:
        raise ValueError("Car texture upload length does not match its dimensions")
    return upload


def body_uploads(data):
    payload, base, relocations = relocation_table(data)
    if relocations.get(0) == 3:
        header = 0x10
    elif relocations.get(0x10) == 3:
        header = 0x20
    else:
        raise ValueError("Expected a PS2 car texture DMA reference in the archive header")
    count, table, upload_start = struct.unpack_from("<3I", data, header)
    table -= base
    upload_start -= base
    if (count < len(BODY_PAGES) or table != header + 16 or relocations.get(header + 4) != 0
            or relocations.get(header + 8) != 0 or not table + count * TEXTURE_ROW_SIZE <= upload_start < payload):
        raise ValueError("Invalid PS2 car texture table")

    groups = {}
    for record in range(table, table + count * TEXTURE_ROW_SIZE, TEXTURE_ROW_SIZE):
        name = bytes(data[record + 0xec:record + TEXTURE_ROW_SIZE]).split(b"\0", 1)[0]
        prefix, _, suffix = name.rpartition(b"_")
        if prefix and suffix in BODY_PAGES:
            groups.setdefault(prefix.lower(), []).append((suffix, record))
    matches = [rows for rows in groups.values()
               if len(rows) == len(BODY_PAGES) and {suffix for suffix, _ in rows} == BODY_PAGES]
    if len(matches) != 1:
        raise ValueError("Expected one group of four numbered car body pages")

    pages = {}
    last = upload_start
    for suffix, record in matches[0]:
        tex0 = struct.unpack_from("<Q", data, record)[0]
        if tex0 >> 20 & 0x3f != 0x13 or tex0 >> 51 & 0xf:
            raise ValueError("Expected four distinct 8-bit body pages with 32-bit palettes")
        if relocations.get(record + 0xcc) != 0 or relocations.get(record + 0xe8) != 0:
            raise ValueError("Missing car texture or palette relocation")
        pixels = struct.unpack_from("<I", data, record + 0xcc)[0] - base
        palette = struct.unpack_from("<I", data, record + 0xe8)[0] - base
        bitmap = image_upload(data, pixels, last, payload)
        colors = image_upload(data, palette, bitmap.end, payload)
        # The 32-bit transfer carries the packed bytes for an 8-bit texture.
        width, height = 1 << (tex0 >> 26 & 0xf), 1 << (tex0 >> 30 & 0xf)
        if bitmap.size != width * height or (colors.width, colors.height) != (16, 16):
            raise ValueError("Indexed body page dimensions do not match its upload and palette")
        pages[suffix] = (bitmap, colors)
        last = colors.end
    return pages


def copy_body_pages(source, target):
    """Copy pixels and palette entries by page suffix while retaining target DMA and palette state."""
    source_pages = body_uploads(source)
    output = bytearray(target)
    for name, uploads in body_uploads(target).items():
        for donor, destination in zip(source_pages[name], uploads):
            if (donor.width, donor.height) != (destination.width, destination.height):
                raise ValueError(f"Body texture page {name.decode('ascii')} has incompatible dimensions")
            output[destination.offset:destination.end] = source[donor.offset:donor.end]
    return bytes(output)
