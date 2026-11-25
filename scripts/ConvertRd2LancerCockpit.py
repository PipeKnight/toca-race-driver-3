"""Install the donor Lancer instruments and steering assembly in the RD3 DTM cockpit."""

from collections import Counter
import math
import struct

from BuildTrackGeometryOverlay import read_word, vif_commands
from ConvertRd2Db5Cabin import Cabin, IDENTITY, Strips
from ConvertRd2Db5Cockpit import companion_atlas, embedded_atlas
from Ps2CarModel import UV
from Ps2CockpitModel import cockpit_draw_packets, cockpit_sections
from Rd2Ps2Cockpit import cockpit_group, cockpit_part


# Front rim of the instrument recess in the RD3 DTM cockpit shell.
DTM_STEERING_X = -.2465
DTM_COWL_FRONT_Z = .285
DTM_DISPLAY_Y = .140


def clut_slot(index):
    return (index & ~24) | ((index & 8) << 1) | ((index & 16) >> 1)


def read_tim2(data, size, color_bytes):
    palette_size, pixel_size, header_size, colors = struct.unpack_from("<IIHH", data, 0x84)
    width, height = struct.unpack_from("<HH", data, 0x94)
    if (data[:6] != b"TIM2\x04\x01" or (width, height) != (size, size)
            or (palette_size, pixel_size, header_size, colors) != (256 * color_bytes, size * size, 128, 256)
            or len(data) != 256 + pixel_size + palette_size):
        raise ValueError("Unexpected cockpit TIM2 dimensions or palette")
    palette_at = 256 + pixel_size
    palette = tuple(data[palette_at + start:palette_at + start + color_bytes].ljust(4, b"\x80")
                    for start in (clut_slot(i) * color_bytes for i in range(256)))
    return data[256:palette_at], palette


def limit_palette(indices, palette, start, limit):
    # Keep the most common colors exact and map rare colors to the nearest retained color.
    keys = [value for value, _ in Counter(indices).most_common(limit)]
    colors = [palette[key] for key in keys]
    mapping = {key: start + offset for offset, key in enumerate(keys)}
    for key in set(indices) - mapping.keys():
        mapping[key] = start + min(range(len(colors)), key=lambda i: sum(
            (a - b) ** 2 for a, b in zip(palette[key], colors[i])))
    return bytes(mapping[index] for index in indices), b"".join(colors).ljust(limit * 4, b"\0")


def digit_atlas(data):
    if (len(data) != 8576 or data[:6] != b"TIM2\x04\x01" or data[0x92:0x98] != b"\x03\x04\x80\x00\x80\x00"
            or struct.unpack_from("<IIHH", data, 0x84) != (128, 8192, 128, 16)):
        raise ValueError("Expected the Lancer's 4-bit digit atlas")
    image = data[256:8448]
    pixels = [index for value in image for index in (value & 15, value >> 4)]
    # Suppress the donor LCD's inactive segments, which otherwise read as solid strokes after downsampling.
    palette = bytearray(data[8448:8512])
    opacity = (0, 0, 128, 112, 80, 48, 12, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    palette[3::4] = bytes(opacity)

    def average(x, y, width, height):
        coverage = sum(opacity[pixels[row * 128 + col]] for row in range(y, y + height)
                       for col in range(x, x + width)) / (width * height)
        alpha = max(0., min(128., (coverage - 12.) * 128. / 85.))
        return 240 + min((0, 2, 3, 4, 5), key=lambda value: abs(alpha - opacity[value]))

    tile = bytearray([240] * 1024)
    for digit in range(10):
        sx, sy = (digit % 6) * 20, (digit // 6) * 30
        x, y = (digit % 4) * 8, (digit // 4) * 10
        for row in range(10):
            for col in range(8):
                first, last = col * 20 // 8, (col + 1) * 20 // 8
                tile[(y + row) * 32 + x + col] = average(sx + first, sy + 3 * row, last - first, 3)
    for row in range(10):
        for col in range(16):
            first, last = col * 42 // 16, (col + 1) * 42 // 16
            tile[(20 + row) * 32 + 16 + col] = average(59 + first, 79 + row * 2, last - first, 2)
    return tile, palette


def combine_atlas(stock, donor, digits):
    stock_pixels, stock_colors = read_tim2(stock, 128, 4)
    wheel_pixels, wheel_colors = read_tim2(donor, 256, 3)
    left, left_colors = limit_palette(stock_pixels[1::2], stock_colors, 0, 128)
    wheel = bytes(wheel_pixels[(row * 256 // 96) * 256 + 2 * col + 1]
                  for row in range(96) for col in range(64))
    screen = bytes(wheel_pixels[(33 + row * 111 // 31) * 256 + 132 + col * 73 // 31]
                   for row in range(32) for col in range(32))
    right, right_colors = limit_palette(wheel + screen, wheel_colors, 128, 112)
    glyphs, digit_colors = digit_atlas(digits)
    right = right[:6144] + b"".join(right[6144 + row:6176 + row] + glyphs[row:row + 32]
                                    for row in range(0, len(glyphs), 32))
    image = b"".join(left[row:row + 64] + right[row:row + 64] for row in range(0, len(left), 64))
    colors = left_colors + right_colors + digit_colors
    palette = b"".join(colors[slot:slot + 4] for slot in (clut_slot(i) * 4 for i in range(256)))
    return image, palette


def fit_stock_atlas(target):
    output = bytearray(target)
    for begin, end in cockpit_sections(target):
        page = None
        for strip in cockpit_draw_packets(target, begin, end):
            for cmd in vif_commands(target, strip.start, strip.uv.payload - 4):
                if cmd.operation == 0x6c and cmd.size == 16:
                    value, address = struct.unpack_from("<QQ", target, cmd.payload)
                    if address == 6:
                        page = value & 0x3fff
            if page != 0x3180:
                continue
            for offset in range(strip.uv.payload, strip.uv.payload + strip.uv.size, UV.size):
                u, v = UV.unpack_from(target, offset)
                UV.pack_into(output, offset, max(0, min(1, u)) * (63 / 128) + .5 / 128, v)
    return output


def close_wheel_rim(wheel, strips):
    """Join the open donor rim with a rounded extension matching its two ends."""
    first_points, first_uvs = strips[0]
    tip = first_points[0]
    heading = math.atan2(tip[1], tip[0])
    vertices = {(point, uv) for points, texcoords in strips for point, uv in zip(points, texcoords)}
    right = sorted(((point, uv) for point, uv in vertices if point[0] > 0
                    and abs(uv[0] - first_uvs[0][0]) < 1e-5
                    and abs(math.atan2(point[1], point[0]) - heading) < .025), key=lambda pair: pair[1][1])
    left_side = {point for point, _ in vertices if point[0] < 0 and point[1] > .07}
    if len(right) != 5 or not left_side or not .70 <= heading <= .80:
        raise ValueError("Expected two exposed ends on the Lancer steering rim")
    rings = []
    for point, uv in right:
        x, y, z = point
        reflection = (-x, y, z)
        end = min(left_side, key=lambda candidate: math.dist(candidate, reflection))
        if math.dist(end, reflection) > .003:
            raise ValueError("The Lancer steering rim ends do not match")
        center_x = (x + end[0]) * .5
        radius = math.hypot(x - center_x, y)
        angle = math.atan2(y, x - center_x)
        points = [point]
        for step in range(1, 12):
            turn = angle + (math.pi - 2 * angle) * step / 12
            points.append((center_x + radius * math.cos(turn), radius * math.sin(turn), z))
        points.append(end)
        rings.append((points, wheel_uv(*uv)))

    for (near, near_uv), (far, far_uv) in zip(rings, rings[1:] + rings[:1]):
        wheel.add(tuple(point for pair in zip(near, far) for point in pair), (near_uv, far_uv) * len(near))


def wheel_uv(u, v):
    return u + .5, (.5 + 95 * v) / 128


def add_instruments(cabin, donor_cockpit, steering_x):
    material, face = cockpit_group(donor_cockpit, 1)
    overlay_material, overlay = cockpit_group(donor_cockpit, 4)
    if material != "gen02" or overlay_material != "gen02" or len(face) != 1 or len(overlay) != 1:
        raise ValueError("Unexpected Lancer instrument material or strip count")
    face_points, face_uv = face[0]
    plane, _ = overlay[0]
    if len(plane) != 4 or max(z for _, _, z in plane) - min(z for _, _, z in plane) > .001:
        raise ValueError("Expected the Lancer's flat digital display overlay")
    xmin, ymin, zmin = (min(axis) for axis in zip(*plane))
    xmax, ymax, _ = (max(axis) for axis in zip(*plane))
    if abs((xmin + xmax) * .5 - steering_x) > .004:
        raise ValueError("The Lancer display does not line up with the steering column")
    # Mount the face just in front of the cowl and below the top of the rim.
    # Apply the same translation to the digits and units to retain their glass clearance.
    mount = bytearray(IDENTITY)
    face_z = face_points[0][2]
    struct.pack_into("<3f", mount, 48, DTM_STEERING_X - steering_x,
                     DTM_DISPLAY_Y - .5 * (ymin + ymax), DTM_COWL_FRONT_Z - .007 - face_z)
    display = Strips()
    display.add(face_points, (((64.5 + 31 * (u * 256 - 132) / 73) / 128,
                              (96.5 + 31 * (v * 256 - 33) / 111) / 128) for u, v in face_uv))
    cabin.append("evo_speed_display", "int_main_body", mount, display.mesh, display.strips)
    width, height = xmax - xmin, ymax - ymin

    def quad(left, right, bottom, top, box):
        x0, x1 = xmin + width * left, xmin + width * right
        y0, y1 = ymin + height * bottom, ymin + height * top
        u0, v0, u1, v1 = (p / 128 for p in box)
        return (((x0, y1, zmin), (x0, y0, zmin), (x1, y1, zmin), (x1, y0, zmin)),
                ((u0, v0), (u0, v1), (u1, v0), (u1, v1)))

    for slot in range(3):
        digit = Strips()
        digit.add(*quad(.12 + slot * .25, .36 + slot * .25, .39, .88, (126.5, 127.5, 127.5, 127.5)))
        cabin.append(f"evo_speed_digit{slot}", "int_main_body", mount, digit.mesh, digit.strips)
        packet = bytearray(cabin.draws[-1])
        draw = next(cockpit_draw_packets(packet, 40, len(packet)))
        if (packet[60:72] != bytes(12) or draw.uv.payload != 236
                or read_word(packet, draw.uv.payload - 4) != 0x74040108):
            raise ValueError("Unexpected Lancer speed digit draw layout")
        struct.pack_into("<3I", packet, 60, 0x5645, 0x374f, slot)
        cabin.draws[-1] = packet

    units = Strips()
    units.add(*quad(.23, .77, .08, .30, (112.5, 116.5, 127.5, 125.5)))
    cabin.append("evo_speed_units", "int_main_body", mount, units.mesh, units.strips)


def convert_wheel(donor_cockpit, donor_texture, donor_digits, target, target_archive, target_atlas):
    matrix, material, source = cockpit_part(donor_cockpit, 20)
    if material != "gen02" or len(source) != 20:
        raise ValueError("Unexpected Lancer steering wheel material or strip count")
    steering_x, _, steering_z = struct.unpack_from("<3f", matrix, 48)
    mount = bytearray(matrix)
    struct.pack_into("<f", mount, 48, DTM_STEERING_X)
    wheel = Strips()
    column = Strips()
    for points, texcoords in source:
        if any(not 0 <= u < .5 or not 0 <= v <= 1 for u, v in texcoords):
            raise ValueError("The Lancer steering wheel uses texture coordinates outside its atlas region")
        end = max(z for _, _, z in points)
        if end > .15 and max(math.hypot(x, y) for x, y, _ in points) < .021:
            start = min(z for _, _, z in points)
            forward_z, = struct.unpack_from("<f", matrix, 40)
            if end - start < .05 or forward_z < .5 or steering_z >= DTM_COWL_FRONT_Z:
                raise ValueError("Unexpected Lancer steering column dimensions")
            attached_end = (DTM_COWL_FRONT_Z - steering_z) / forward_z
            scale = (attached_end - start) / (end - start)
            stretched = tuple((x, y, start + (z - start) * scale) for x, y, z in points)
            column.add(stretched, (wheel_uv(.12, .92),) * len(points))
        else:
            wheel.add(points, (wheel_uv(u, v) for u, v in texcoords))
    if len(column.strips) != 1:
        raise ValueError("The Lancer steering column was not found")
    close_wheel_rim(wheel, source)
    image, palette = combine_atlas(target_atlas, donor_texture, donor_digits)
    cabin = Cabin(fit_stock_atlas(target))
    cabin.append("evo_steering_column", "int_main_body", mount, column.mesh, column.strips)
    cabin.append("steering_wheel", "int_main_body", mount, wheel.mesh, wheel.strips)
    add_instruments(cabin, donor_cockpit, steering_x)
    return embedded_atlas(cabin.encode(), image, palette), companion_atlas(target_archive, image, palette)
