#!/usr/bin/env python3
"""Generate Clio Cup track-selection maps from the routes in a PS2 circuit pack."""

import argparse
import math
from pathlib import Path
import struct

from BuildDtmVariant import read_disc_range
from BuildRoadAmericaMod import repack_jpak, unpack_lzss
from BuildTrackCollisionOverlay import REFERENCE_DIRECTORY_HASH, encode_lzss, encode_lzss_compact, verify_directory
from ModAssets import REFERENCE_PACKAGES, find_member, members
from Ps2TrackRoute import read_route


SELECTOR = (1, 130160, 504061)
LZSS = struct.Struct("<4sII")
TXI_ENTRY = struct.Struct("<32sI4fI")
ATLAS_WIDTH, ATLAS_HEIGHT = 1024, 256
ICON_WIDTH, ICON_HEIGHT = 128, 76
ATLAS_HEADER = 64


def member(archive, name):
    return find_member(archive, name)[0].read(archive)


def route_outline(package):
    main, _, _ = read_route(member(member(package, "osc1.big"), "osc1.ail"))
    start, = (i for i, event in enumerate(main.events) if event[3] == 6)
    if not main.loop or len(main.lanes) < 2:
        raise ValueError("Expected a closed racing route")
    outline = [(a / 2 + c / 2, -(b / 2 + d / 2))
               for (a, b), (c, d) in zip(main.lanes[0], main.lanes[-1], strict=True)]
    return outline[start:] + outline[:start]


def segment_distance(x, y, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    length_squared = dx * dx + dy * dy
    along = min(1, max(0, ((x - ax) * dx + (y - ay) * dy) / length_squared)) if length_squared else 0
    return math.hypot(x - ax - along * dx, y - ay - along * dy)


def render_icon(outline, palette):
    left, right = min(x for x, _ in outline), max(x for x, _ in outline)
    top, bottom = min(y for _, y in outline), max(y for _, y in outline)
    if min(right - left, bottom - top) < 1:
        raise ValueError("Invalid track map bounds")
    width, height = ICON_WIDTH, ICON_HEIGHT
    scale = min((width - 20) / (right - left), (height - 20) / (bottom - top))
    points = [((x - (left + right) / 2) * scale + width / 2,
               (y - (top + bottom) / 2) * scale + height / 2) for x, y in outline]
    sx, sy = points[0]
    before = next(point for point in reversed(points) if math.dist(point, points[0]) >= 5)
    after = next(point for point in points if math.dist(point, points[0]) >= 5)
    dx, dy = after[0] - before[0], after[1] - before[1]
    distance = math.hypot(dx, dy)
    if distance < 1:
        raise ValueError("The route reverses at the timing line")
    dx, dy = dx / distance, dy / distance
    segments = list(zip(points, points[1:] + points[:1]))
    # Position the direction arrow beside the timing line on the clearer side.
    sides = [(sx - dy * side * 8, sy + dx * side * 8) for side in (-1, 1)]
    x, y = max(sides, key=lambda p: min(segment_distance(*p, *a, *b) for a, b in segments))
    tip = x + dx * 7, y + dy * 7
    arrow = [((x - dx * 7, y - dy * 7), tip)]
    for side in (-1, 1):
        arrow.append(((tip[0] - dx * 5 - dy * side * 2.5, tip[1] - dy * 5 + dx * side * 2.5), tip))

    distances = [math.inf] * (width * height)
    for layer in (segments, arrow):
        for (ax, ay), (bx, by) in layer:
            for iy in range(max(0, math.floor(min(ay, by) - 5)), min(height, math.ceil(max(ay, by) + 5))):
                for ix in range(max(0, math.floor(min(ax, bx) - 5)), min(width, math.ceil(max(ax, bx) + 5))):
                    px, py = ix + .5, iy + .5
                    if layer is segments and (px - sx)**2 + (py - sy)**2 < 5:
                        continue
                    i = iy * width + ix
                    distances[i] = min(distances[i], segment_distance(px, py, ax, ay, bx, by))

    swatches = tuple((round(gray * min(alpha, 128) / 128), min(alpha, 128)) for gray, _, _, alpha in palette)
    raster = bytearray()
    for distance in distances:
        white = round(255 * min(1, max(0, 2 - distance)))
        alpha = round(128 * min(1, max(0, (4 - distance) / 1.5)))
        raster.append(min(range(256), key=lambda i: (swatches[i][0] - white)**2 + (swatches[i][1] - alpha)**2))
    return raster


def fit_selector_extent(packed, rebuilt, stored):
    """Fill the disc extent with complete LZSS tokens and decoded JPAK tail padding."""
    if len(packed) == stored:
        return packed, len(rebuilt)
    if len(packed) > stored:
        raise ValueError(f"Track selector needs {len(packed) + LZSS.size} compressed bytes")
    offset = written = 0
    while written < len(rebuilt):
        prefix, expanded = offset, written
        flags = packed[offset]
        offset += 1
        for bit in range(8):
            if written == len(rebuilt):
                break
            if flags & (1 << bit):
                written += 1
                offset += 1
            else:
                written += (packed[offset + 1] & 15) + 3
                offset += 2

    # Re-encode the last flag group with literals. Every further byte supplies
    # archive padding, so the streaming reader consumes the complete extent.
    groups, extra = divmod(stored - prefix, 9)
    backreference = extra == 1
    if backreference:
        groups -= 1
    remaining = 8 * groups + max(0, extra - 1)
    if remaining < len(rebuilt) - expanded:
        raise ValueError("Track selector has too little space to complete its compression stream")
    tail = rebuilt[expanded:].ljust(remaining, b"\0")
    result = bytearray(packed[:prefix])
    for i in range(0, len(tail), 8):
        chunk = tail[i:i + 8]
        result.append((1 << len(chunk)) - 1)
        result.extend(chunk)
    if backreference:
        # A group with seven zero literals and a reference to the first three
        # of them occupies ten bytes, consuming the spare byte exactly.
        ring = (0xFEE + expanded + len(tail)) & 0xFFF
        result.extend((0x7f, 0, 0, 0, 0, 0, 0, 0, ring & 255, (ring >> 4) & 0xf0))
    return result, expanded + len(tail) + (10 if backreference else 0)


def build_icons(disc, pack):
    verify_directory(disc / "RDH.DIR", REFERENCE_DIRECTORY_HASH)
    original = read_disc_range(disc, *SELECTOR)
    magic, stored, expanded = LZSS.unpack_from(original)
    if magic != b"LZSS" or stored != len(original) or expanded != 1001152:
        raise ValueError("Unexpected Clio Cup track selector archive")
    archive = bytes(unpack_lzss(original[LZSS.size:], expanded))
    index = bytearray(member(archive, "TrackMaps.txi"))
    texture = bytearray(member(archive, "TrackMaps0.tex"))
    if (index[:12] != struct.pack("<4sII", b"txi2", 1, 9)
            or len(index) != 28 + 9 * TXI_ENTRY.size
            or texture[:4] != b"TIM2" or len(texture) != ATLAS_HEADER + ATLAS_WIDTH * ATLAS_HEIGHT + 1024
            or struct.unpack_from("<HH", texture, 36) != (ATLAS_WIDTH, ATLAS_HEIGHT)):
        raise ValueError("Unexpected track map atlas layout")
    for _, _, _, _, _, end_v, palette_index in TXI_ENTRY.iter_unpack(index[28:]):
        if end_v > (ATLAS_HEIGHT - ICON_HEIGHT) / ATLAS_HEIGHT or palette_index:
            raise ValueError("The stock maps overlap the generated atlas row")
    entries = {m.name.lower() for m in members((pack / "tracks.big").read_bytes())}
    ids = [f"tqa{i}" for i in range(1, 6) if f"tqa{i}.ini" in entries]
    if not ids:
        raise ValueError("The pack has no imported track entries")
    clut = tuple(struct.iter_unpack("<4B", texture[-1024:]))
    palette = [clut[(i & ~24) | ((i & 8) << 1) | ((i & 16) >> 1)] for i in range(256)]
    routes = [("osc1", read_disc_range(disc, *REFERENCE_PACKAGES["oschersleben-track"]))]
    for track in ids:
        source = pack if track == "tqa1" else pack / track
        routes.append((track, (source / "TRACK.JPK").read_bytes()))
    y = ATLAS_HEIGHT - ICON_HEIGHT
    for i, (track, package) in enumerate(routes):
        image = render_icon(route_outline(package), palette)
        x = i * (ICON_WIDTH + 8)
        for row in range(ICON_HEIGHT):
            at = ATLAS_HEADER + (y + row) * ATLAS_WIDTH + x
            texture[at:at + ICON_WIDTH] = image[row * ICON_WIDTH:(row + 1) * ICON_WIDTH]
        index.extend(TXI_ENTRY.pack(f"tm_{track}".encode("ascii"), 0, x / ATLAS_WIDTH, y / ATLAS_HEIGHT,
                                    (x + ICON_WIDTH) / ATLAS_WIDTH, 1., 0))
    struct.pack_into("<I", index, 8, 9 + len(routes))
    rebuilt = bytes(repack_jpak(archive, 18, {b"TrackMaps.txi": index, b"TrackMaps0.tex": texture}))
    packed = encode_lzss(rebuilt)
    if len(packed) + LZSS.size > stored:
        packed = encode_lzss_compact(rebuilt)
    payload, size = fit_selector_extent(packed, rebuilt, stored - LZSS.size)
    if len(payload) != stored - LZSS.size or size > 1 << 20:
        raise ValueError("Track selector exceeds the supported archive extent")
    return LZSS.pack(b"LZSS", stored, size) + payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disc", type=Path, required=True, help="mounted or extracted SLUS-21182 disc")
    parser.add_argument("--pack", type=Path, required=True, help="existing PS2 circuit pack")
    args = parser.parse_args()
    output = args.pack / "TS_RCCUF.LZS"
    try:
        if output.exists():
            raise ValueError("Choose a pack without an existing TS_RCCUF.LZS")
        data = build_icons(args.disc, args.pack)
        with output.open("xb") as stream:
            stream.write(data)
    except (OSError, ValueError, struct.error) as error:
        parser.exit(1, f"Track map build failed: {error}\n")
    print(output)


if __name__ == "__main__":
    main()
