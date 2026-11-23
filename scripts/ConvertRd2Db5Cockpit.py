"""Convert the RD2 DB5 cockpit shell and embedded atlas for the RD3 DTM template."""

from itertools import islice
import math
import struct

from BuildRoadAmericaMod import read_bigf, repack_bigf
from BuildTrackGeometryOverlay import read_word
from Ps2CarModel import UV, VERTEX, mesh_packets, model_sections, relocation_table
from Ps2CarTexture import image_upload
from Ps2CockpitModel import cockpit_draw_packets, cockpit_nodes, cockpit_sections


def db5_draw_parts(model, mesh, expected):
    _, base, _, sections = model_sections(model)
    mesh_base, packets = mesh_packets(mesh)
    start, end = sections[0]
    first, last = (address - base for address in struct.unpack_from("<2I", model, start + 0x24))
    parts = {}
    for slot, count in expected.items():
        part = first + slot * 0x30
        if not start <= first <= part <= last - 0x30 <= end - 0x30 or read_word(model, part) != 0:
            raise ValueError(f"Missing DB5 cockpit part {slot}")
        draw = read_word(model, part + 8) - base
        if not last <= draw <= end - 0x98:
            raise ValueError(f"Invalid DB5 cockpit descriptor for part {slot}")
        ref = (read_word(model, draw + 0x94) & 0x7fffffff) - base
        strips = []
        while start <= ref <= end - 16 and read_word(model, ref) >> 28 & 7 == 3:
            command, address = struct.unpack_from("<2I", model, ref)
            begin = address - mesh_base
            finish = begin + (command & 0xffff) * 16
            strips.extend(packet for packet in packets if begin <= packet.position < finish)
            ref += 16
        if len(strips) != count or not all(strip.triangle_strip for strip in strips):
            raise ValueError(f"Unexpected strip table for DB5 cockpit part {slot}")
        # RD2 uses the last matrix word for a draw index, whereas PS2M stores an affine transform.
        matrix = model[draw + 0x20:draw + 0x5c] + struct.pack("<f", 1.0)
        if not all(map(math.isfinite, struct.unpack("<16f", matrix))):
            raise ValueError(f"Non-finite DB5 cockpit transform for part {slot}")
        parts[slot] = matrix, strips
    return parts


def db5_shell_packets(model, mesh):
    return db5_draw_parts(model, mesh, {119: 64})[119][1]


def convert_shell(model, mesh, target):
    strips = db5_shell_packets(model, mesh)
    begin, end = cockpit_sections(target)[0]
    payload, low, high = replace_draw_strips(target, begin, end, mesh, strips)
    header = bytearray(target[:begin])
    struct.pack_into("<6f", header, begin - 32, *low, *high)
    struct.pack_into("<I", header, begin - 4, len(payload))
    return bytes(header + payload + target[end:])


def replace_draw_strips(target, begin, end, mesh, strips):
    templates = tuple(islice(cockpit_draw_packets(target, begin, end), 4))
    if (len(templates) != 4
            or tuple(read_word(target, packet.start + 4) for packet in templates)
            != (0x100, 0x200, 0x300, 0x100)
            or tuple(read_word(target, packet.start + 12) for packet in templates)
            != (0x108, 0x201, 0x301, 0x101)):
        raise ValueError("Missing RD3 cockpit shell draw templates")

    payload = bytearray()
    positions = []
    for index, strip in enumerate(strips):
        # The first draw initializes the material; subsequent strips rotate through the three VU buffers.
        packet = templates[1 + (index - 1) % 3] if index else templates[0]
        offset = packet.start
        tag, uv, color, vertex, draw = packet.tag, packet.uv, packet.color, packet.vertex, packet.draw
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
    return payload, low, high


def convert_wipers(model, mesh, target):
    """Retarget the DTM node graph to the DB5's two wiper pivots and swept positions."""
    poses = db5_draw_parts(model, mesh, {slot: 20 for slot in (79, 80, 81, 83, 84, 85)})
    scene = read_word(target, 0x20)
    draw_table, names = cockpit_nodes(target)
    sections = cockpit_sections(target)
    right_names = ("r_wiper", "r_wiper_pos3", "r_wiper_pos2", "r_wiper_pos1")
    if (len(sections) != 20 or read_word(target, 28) != 20 or read_word(target, 16) != 1
            or tuple(names[2:6]) != tuple((name, (index,)) for index, name in enumerate(right_names, 1))):
        raise ValueError("Expected the DTM cockpit's single right wiper and three swept positions")
    nodes = []
    pos = scene + 44 + read_word(target, scene + 36)
    for _, refs in names:
        size = 80 + 4 * len(refs)
        nodes.append(bytearray(target[pos:pos + size]))
        pos += size
    if target[pos:draw_table] != struct.pack("<21I", 20, *range(1, 21)):
        raise ValueError("Unexpected DTM cockpit draw list")

    def draw_part(begin, end, strips):
        payload, low, high = replace_draw_strips(target, begin, end, mesh, strips)
        header = bytearray(target[begin - 40:begin])
        struct.pack_into("<6f", header, 8, *low, *high)
        struct.pack_into("<I", header, 36, len(payload))
        return bytes(header + payload)

    draws = [target[begin - 40:end] for begin, end in sections]
    first_left = len(nodes)
    # Keep the DTM animation's three position names; RD2 ends its sweep at pose 2.
    for i, (right_slot, left_slot) in enumerate(zip((79, 81, 81, 80), (83, 85, 85, 84))):
        right_matrix, right_strips = poses[right_slot]
        left_matrix, left_strips = poses[left_slot]
        right = nodes[2 + i]
        right[12:76] = right_matrix
        left = bytearray(right)
        if i == 0:
            parent, child, sibling = struct.unpack_from("<3I", right)
            if (parent, child, sibling) != (1, 3, 6):
                raise ValueError("Unexpected DTM wiper graph links")
            struct.pack_into("<I", right, 8, first_left)
            struct.pack_into("<3I", left, 0, parent, first_left + 1, sibling)
        else:
            next_pose = first_left + i + 1 if i < 3 else 0xffffffff
            struct.pack_into("<3I", left, 0, first_left, 0xffffffff, next_pose)
        left[12:76] = left_matrix
        struct.pack_into("<I", left, 80, len(sections) + i)
        nodes.append(left)
        begin, end = sections[1 + i]
        draws[1 + i] = draw_part(begin, end, right_strips)
        draws.append(draw_part(begin, end, left_strips))

    names = [name for name, _ in names] + [name.replace("r_wiper", "l_wiper") for name in right_names]
    table = b"".join(name.encode("ascii") + b"\0" for name in names)
    table += bytes(-len(table) % 4)
    header = bytearray(target[:scene + 40])
    struct.pack_into("<I", header, scene + 36, len(table))
    for offset in (8, 28):
        struct.pack_into("<I", header, offset, len(draws))
    draw_list = (*range(1, 21), *range(first_left, first_left + 4))
    output = (bytes(header) + table + struct.pack("<I", len(nodes)) + b"".join(nodes)
              + struct.pack("<25I", len(draw_list), *draw_list) + b"".join(draws) + bytes(4))
    cockpit_sections(output)
    return output


# Block and column layouts for PSMCT32 uploads and PSMT8 reads of the same GS pages.
BLOCKS = (
    (0, 1, 4, 5, 16, 17, 20, 21), (2, 3, 6, 7, 18, 19, 22, 23),
    (8, 9, 12, 13, 24, 25, 28, 29), (10, 11, 14, 15, 26, 27, 30, 31),
)
WORDS = ((0, 1, 4, 5, 8, 9, 12, 13), (2, 3, 6, 7, 10, 11, 14, 15))


def rgba_page_offsets(width, height):
    for y in range(height):
        for x in range(width):
            page = (x // 64 + y // 32 * (width // 64)) * 8192
            block = BLOCKS[(y % 32) // 8][(x % 64) // 8] * 256
            yield page + block + ((y & 7) // 2) * 64 + WORDS[y & 1][x & 7] * 4


def indexed_page_offset(x, y, width):
    page = (x // 128 + y // 64 * (width // 128)) * 8192
    block = BLOCKS[(y // 16) & 3][(x // 16) & 7] * 256
    bank = ((y >> 1) & 1) ^ ((y >> 2) & 1)
    word = WORDS[y & 1][(x & 7) ^ (bank << 2)]
    byte = ((x & 8) >> 2) + ((y & 2) >> 1)
    return page + block + ((y & 15) // 4) * 64 + word * 4 + byte


def donor_atlas(source):
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
    for index, address in enumerate(rgba_page_offsets(128, 128)):
        start = pixels.offset + index * 4
        vram[address:address + 4] = source[start:start + 4]

    # A full 256 by 256 atlas would overwrite the next RD3 texture slot.
    image = bytes(vram[indexed_page_offset(x, y, 256)] for y in range(0, 256, 2) for x in range(0, 256, 2))
    return image, source[palette.offset:palette.end]


def embedded_atlas(target, image, palette):
    """Replace the first two PS2M uploads without moving the other GS allocations."""
    scene = read_word(target, 0x20)
    header_size = 0x60

    def upload(at, address, width, height):
        size = width * height * 4
        expected = (1, 0x40000000, 0xeeee, 0, 0, address, 0x50, 0, 0, 0, 0x51, 0,
                    width, height, 0x52, 0, 0, 0, 0x53, 0, size // 16, 0x08000000, 0, 0)
        if at + header_size + size > scene or struct.unpack_from("<24I", target, at) != expected:
            raise ValueError(f"Unexpected DTM cockpit atlas upload at {at:#x}")
        return at + header_size, at + header_size + size

    first, end = upload(0x24, 0x13180, 64, 64)
    clut, finish = upload(end, 0x138bc, 16, 16)
    if len(image) != end - first or len(palette) != finish - clut:
        raise ValueError("The DB5 atlas does not fit the DTM cockpit image and palette uploads")
    vram = bytearray(len(image))
    for i, value in enumerate(image):
        vram[indexed_page_offset(i % 128, i // 128, 128)] = value
    pixels = b"".join(vram[at:at + 4] for at in rgba_page_offsets(64, 64))
    return bytes(target[:first] + pixels + target[end:clut] + palette + target[finish:])


def companion_atlas(target, image, palette):
    entries, base = read_bigf(target, 4)
    atlas = entries[b"int_01.tm2"]
    if len(atlas) != 17664 or atlas[:4] != b"TIM2" or struct.unpack_from("<HH", atlas, 148) != (128, 128):
        raise ValueError("Expected the 128 by 128 DTM cockpit atlas")
    entries[b"int_01.tm2"] = bytes(atlas[:256] + image + palette)
    return bytes(repack_bigf(target, entries, base, base, len(target)))
