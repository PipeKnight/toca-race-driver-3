"""Convert the RD2 DB5 cockpit shell and atlas for the RD3 DTM template."""

from collections import defaultdict
from itertools import islice
import math
import struct

from BuildRoadAmericaMod import read_bigf, repack_bigf
from BuildTrackGeometryOverlay import read_word, vif_commands
from Ps2CarModel import UV, VERTEX, mesh_packets, model_sections, relocation_table
from Ps2CarTexture import image_upload
from Ps2CockpitModel import cockpit_sections, cockpit_strips


def db5_shell_packets(model, mesh):
    _, base, _, sections = model_sections(model)
    mesh_base, packets = mesh_packets(mesh)
    start, end = sections[0]
    first, last = (address - base for address in struct.unpack_from("<2I", model, start + 0x24))
    body = first + 119 * 0x30
    if not start <= body < last <= end or read_word(model, body) != 0:
        raise ValueError("Expected the DB5 cockpit shell in part 119")
    draw = read_word(model, body + 8) - base
    if not last <= draw <= end - 0x98:
        raise ValueError("Invalid DB5 cockpit shell descriptor")
    ref = (read_word(model, draw + 0x94) & 0x7fffffff) - base
    strips = []
    while start <= ref <= end - 16 and read_word(model, ref) >> 28 & 7 == 3:
        command, address = struct.unpack_from("<2I", model, ref)
        begin = address - mesh_base
        finish = begin + (command & 0xffff) * 16
        strips.extend(packet for packet in packets if begin <= packet.position < finish)
        ref += 16
    if len(strips) != 64 or not all(strip.triangle_strip for strip in strips):
        raise ValueError("Unexpected DB5 cockpit shell strip table")
    return strips


def convert_shell(model, mesh, target):
    strips = db5_shell_packets(model, mesh)
    begin, end = cockpit_sections(target)[0]
    templates = defaultdict(list)
    offsets = []
    for section, offset, points, _ in cockpit_strips(target):
        if section != 0:
            break
        commands = tuple(islice(vif_commands(target, offset, end), 9))
        templates[len(points)].append((offset, commands))
        offsets.append(offset)
    if not offsets or 4 not in templates:
        raise ValueError("Missing RD3 cockpit shell draw templates")

    payload = bytearray(target[begin:offsets[0]])
    fallback = templates[4][:1]
    positions = []
    for index, strip in enumerate(strips):
        available = templates.get(strip.count, fallback)
        offset, commands = available[index % len(available)]
        tag, uv, color, vertex, draw = commands[4:]
        header = bytearray(target[offset:uv.payload - 4])
        gif_tag = struct.unpack_from("<Q", target, tag.payload)[0]
        struct.pack_into("<I", header, 8, strip.count)
        struct.pack_into("<Q", header, tag.payload - offset, (gif_tag & ~0x7fff) | strip.count)
        payload.extend(header)
        coords = mesh[strip.position:strip.position + strip.count * VERTEX.size]
        texture = mesh[strip.uv:strip.uv + strip.count * UV.size]
        positions.extend(VERTEX.iter_unpack(coords))
        for command, data in ((uv, texture), (color, b"\x80" * (4 * strip.count)), (vertex, coords)):
            word = read_word(target, command.payload - 4)
            payload.extend(struct.pack("<I", (word & 0xff00ffff) | (strip.count << 16)))
            payload.extend(data)
        payload.extend(target[draw.payload - 4:draw.payload])

    if not all(math.isfinite(value) for point in positions for value in point):
        raise ValueError("Non-finite position in the RD2 cockpit shell")
    payload.extend(bytes(-len(payload) % 16))
    low, high = (tuple(function(axis) for axis in zip(*positions)) for function in (min, max))
    header = bytearray(target[:begin])
    struct.pack_into("<6f", header, begin - 32, *low, *high)
    struct.pack_into("<I", header, begin - 4, len(payload))
    return bytes(header + payload + target[end:])


# Block and column layouts for PSMCT32 uploads and PSMT8 reads of the same GS pages.
BLOCKS = (
    (0, 1, 4, 5, 16, 17, 20, 21), (2, 3, 6, 7, 18, 19, 22, 23),
    (8, 9, 12, 13, 24, 25, 28, 29), (10, 11, 14, 15, 26, 27, 30, 31),
)
WORDS = ((0, 1, 4, 5, 8, 9, 12, 13), (2, 3, 6, 7, 10, 11, 14, 15))


def cockpit_atlas(source, target):
    end, base, relocations = relocation_table(source)
    descriptor = 0x20
    if relocations.get(0) != 3 or read_word(source, 0x10) != 1 or read_word(source, 0x14) != base + descriptor:
        raise ValueError("Expected the DB5 high-detail cockpit texture descriptor")
    tex0 = struct.unpack_from("<Q", source, descriptor)[0]
    if ((tex0 >> 20) & 63, (tex0 >> 26) & 15, (tex0 >> 30) & 15) != (19, 8, 8):
        raise ValueError("Expected a 256 by 256 indexed DB5 cockpit texture")
    pixels, palette = (image_upload(source, read_word(source, descriptor + field) - base, descriptor, end)
                       for field in (0xcc, 0xe8))
    if (pixels.width, pixels.height, palette.width, palette.height) != (128, 128, 16, 16):
        raise ValueError("Unexpected DB5 cockpit texture upload sizes")

    vram = bytearray(pixels.size)
    for y in range(128):
        for x in range(128):
            page = (x // 64 + y // 32 * 2) * 8192
            block = BLOCKS[(y % 32) // 8][(x % 64) // 8] * 256
            address = page + block + ((y & 7) // 2) * 64 + WORDS[y & 1][x & 7] * 4
            start = pixels.offset + (y * 128 + x) * 4
            vram[address:address + 4] = source[start:start + 4]

    # Keep the RD3 atlas allocation at 128 by 128 while retaining the donor palette.
    image = bytearray()
    for y in range(0, 256, 2):
        for x in range(0, 256, 2):
            page = (x // 128 + y // 64 * 2) * 8192
            block = BLOCKS[(y // 16) & 3][(x // 16) & 7] * 256
            bank = ((y >> 1) & 1) ^ ((y >> 2) & 1)
            word = WORDS[y & 1][(x & 7) ^ (bank << 2)]
            byte = ((x & 8) >> 2) + ((y & 2) >> 1)
            image.append(vram[page + block + ((y & 15) // 4) * 64 + word * 4 + byte])

    entries, base = read_bigf(target, 4)
    atlas = entries[b"int_01.tm2"]
    if len(atlas) != 17664 or atlas[:4] != b"TIM2" or struct.unpack_from("<HH", atlas, 148) != (128, 128):
        raise ValueError("Expected the 128 by 128 DTM cockpit atlas")
    entries[b"int_01.tm2"] = bytes(atlas[:256] + image + source[palette.offset:palette.end])
    return bytes(repack_bigf(target, entries, base, base, len(target)))
