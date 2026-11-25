"""Install the donor Lancer steering wheel in the RD3 DTM cockpit."""

from collections import Counter
import math
import struct

from BuildTrackGeometryOverlay import vif_commands
from ConvertRd2Db5Cabin import Cabin, Strips
from ConvertRd2Db5Cockpit import companion_atlas, embedded_atlas
from Ps2CarModel import UV
from Ps2CockpitModel import cockpit_draw_packets, cockpit_sections
from Rd2Ps2Cockpit import cockpit_part


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


def half_atlas(indices, palette, start):
    # Keep the most common colors exact and map rare colors to the nearest retained color.
    keys = [value for value, _ in Counter(indices).most_common(128)]
    colors = [palette[key] for key in keys]
    mapping = {key: start + offset for offset, key in enumerate(keys)}
    for key in set(indices) - mapping.keys():
        mapping[key] = start + min(range(len(colors)), key=lambda i: sum(
            (a - b) ** 2 for a, b in zip(palette[key], colors[i])))
    return bytes(mapping[index] for index in indices), b"".join(colors).ljust(512, b"\0")


def combine_atlas(stock, donor):
    stock_pixels, stock_colors = read_tim2(stock, 128, 4)
    wheel_pixels, wheel_colors = read_tim2(donor, 256, 3)
    left, left_colors = half_atlas(stock_pixels[1::2], stock_colors, 0)
    right, right_colors = half_atlas(b"".join(wheel_pixels[y * 256 + 1:y * 256 + 128:2]
                                             for y in range(1, 256, 2)), wheel_colors, 128)
    image = b"".join(left[row:row + 64] + right[row:row + 64] for row in range(0, len(left), 64))
    colors = left_colors + right_colors
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
        rings.append((points, (uv[0] + .5, uv[1])))

    for (near, near_uv), (far, far_uv) in zip(rings, rings[1:] + rings[:1]):
        wheel.add(tuple(point for pair in zip(near, far) for point in pair), (near_uv, far_uv) * len(near))


def convert_wheel(donor_cockpit, donor_texture, target, target_archive, target_atlas):
    matrix, material, source = cockpit_part(donor_cockpit, 20)
    if material != "gen02" or len(source) != 20:
        raise ValueError("Unexpected Lancer steering wheel material or strip count")
    wheel = Strips()
    for points, texcoords in source:
        if any(not 0 <= u < .5 or not 0 <= v <= 1 for u, v in texcoords):
            raise ValueError("The Lancer steering wheel uses texture coordinates outside its atlas region")
        wheel.add(points, ((u + .5, v) for u, v in texcoords))
    close_wheel_rim(wheel, source)
    image, palette = combine_atlas(target_atlas, donor_texture)
    cabin = Cabin(fit_stock_atlas(target))
    cabin.append("steering_wheel", "int_main_body", matrix, wheel.mesh, wheel.strips)
    return embedded_atlas(cabin.encode(), image, palette), companion_atlas(target_archive, image, palette)
