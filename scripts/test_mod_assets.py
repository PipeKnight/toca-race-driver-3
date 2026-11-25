"""Regression checks for archive edits using synthetic payloads."""

import csv
from pathlib import Path
import random
import struct
import tempfile
from types import SimpleNamespace
import unittest

from BuildFoundryOval import build_route
from BuildRoadAmericaMod import (
    A1_RING, ROAD_AMERICA, TrackEntry, event_catalog, read_bigf, repack_bigf, track_catalog, unpack_lzss,
)
from BuildTrackCollisionOverlay import encode_lzss, encode_lzss_compact
from BuildTrackGeometryOverlay import FOOTER, RELOCATION, VERTEX as SCENE_VERTEX, vif_commands
from BuildTrackMapIcons import fit_selector_extent
from ConvertRd2CarModel import convert_draw_transforms, convert_textures, serialize_relocations
from ConvertRd2Db5Cockpit import embedded_atlas, replace_draw_strips
from ModAssets import find_member, replace_member
from Ps2CarModel import (
    MeshPacket, UV, lod_packet_ranges, mesh_export, mesh_import, mesh_packets, mesh_replace, part_map_coverage,
)
from Ps2CockpitModel import cockpit_draw_packets
from Ps2TrackCollision import CELL, GRID_CELLS, POLYGON, REFERENCE, TRIANGLE, VERTEX, Collision, collision_append
from Ps2TrackRoute import EVENT, MAGIC, POINT, SECTION, read_route, route_export, route_import
from Ps2TrackScene import Scene, scene_append


class ModAssetTests(unittest.TestCase):
    def test_selector_padding_is_decoded_from_the_full_disc_extent(self):
        archive = b"JPAK" + b"track maps" * 40
        packed = encode_lzss(archive)
        for extra in range(160, 169):
            extent = len(packed) + extra
            padded, expanded = fit_selector_extent(packed, archive, extent)
            self.assertEqual(len(padded), extent)
            self.assertEqual(unpack_lzss(padded, expanded), archive.ljust(expanded, b"\0"))

    def test_cockpit_replacement_rebuilds_the_first_strip_and_rotates_vu_buffers(self):
        word = struct.Struct("<I")

        def packet(bank, count, setup=()):
            stream = bank + len(setup) + 1
            return (struct.pack("<8I", 0x6c018000, bank, count, stream, 0xf5, 0, 0, 0)
                    + b"".join(setup)
                    + struct.pack("<IQQ", 0x6c010000 | (stream - 1), (4 << 47) | count, 0x512)
                    + word.pack(0x74000000 | (count << 16) | stream) + bytes(count * 8)
                    + word.pack(0x6e004000 | (count << 16) | (stream + 1)) + bytes(count * 4)
                    + word.pack(0x68000000 | (count << 16) | (stream + 2)) + bytes(count * 12)
                    + word.pack(0x17000000))

        material = tuple(struct.pack("<IQQ", 0x6c010100 + index, index + 1, 0x0e) for index in range(7))
        target = packet(0x100, 3, material) + b"".join(packet(bank, 3) for bank in (0x200, 0x300, 0x100))
        source = bytearray()
        strips = []
        for index, count in enumerate((7, 4, 5, 3, 8)):
            uv = len(source)
            source.extend(struct.pack("<2f", 0.5, 0.25) * count)
            positions = len(source)
            source.extend(struct.pack("<3f", 1, 2, 3 + index) * count)
            strips.append(SimpleNamespace(count=count, position=positions, uv=uv))

        result, low, high = replace_draw_strips(target, 0, len(target), source, strips)
        packets = list(cockpit_draw_packets(result, 0, len(result)))
        self.assertEqual(result[32:172], target[32:172])  # The first draw retains its GS setup.
        self.assertEqual([word.unpack_from(result, item.start + 4)[0] for item in packets],
                         [0x100, 0x200, 0x300, 0x100, 0x200])
        self.assertEqual([item.vertex.count for item in packets], [7, 4, 5, 3, 8])
        self.assertEqual((low, high), ((1, 2, 3), (1, 2, 7)))
        for old, new in zip(strips, packets):
            self.assertEqual(result[new.vertex.payload:new.vertex.payload + new.vertex.size],
                             source[old.position:old.position + new.vertex.size])
            self.assertEqual(result[new.uv.payload:new.uv.payload + new.uv.size],
                             source[old.uv:old.uv + new.uv.size])
        self.assertEqual(len(result) % 16, 0)
        single = packet(0x100, 3, material)
        rebuilt, _, _ = replace_draw_strips(single, 0, len(single), source, strips[:1])
        self.assertEqual([item.vertex.count for item in cockpit_draw_packets(rebuilt, 0, len(rebuilt))], [7])
        word.pack_into(result, 8, 3)
        with self.assertRaisesRegex(ValueError, "Inconsistent cockpit strip"):
            list(cockpit_draw_packets(result, 0, len(result)))

    def test_cockpit_atlas_replaces_only_the_embedded_image_and_palette(self):
        def upload(address, width, height):
            size = width * height * 4
            return (struct.pack("<6Q", 0x4000000000000001, 0xeeee, address << 32, 0x50, 0, 0x51)
                    + struct.pack("<6Q", width | (height << 32), 0x52, 0, 0x53,
                                  0x0800000000000000 | size // 16, 0)
                    + bytes(size))

        prefix = b"PS2M" + bytes(28) + struct.pack("<I", 0xf3a0)
        reference = prefix + upload(0x13180, 64, 64) + upload(0x138bc, 16, 16)
        reference += b"\xa5" * (0xf3a0 - len(reference)) + b"unchanged scene and draws"
        image = bytearray(128 * 128)
        for x, y, value in ((0, 0, 1), (8, 0, 2), (0, 2, 3), (4, 2, 4), (0, 64, 5)):
            image[y * 128 + x] = value
        palette = bytes(range(256)) * 4

        result = embedded_atlas(reference, image, palette)
        first = len(prefix) + 0x60
        last = first + 0x4000
        expected = bytearray(0x4000)
        expected[:4] = b"\x01\0\x02\0"
        expected[1 + 4 * 4] = 3
        expected[1] = 4
        expected[0x2000] = 5
        self.assertEqual(result[first:last], expected)
        self.assertEqual(result[last + 0x60:last + 0x460], palette)
        self.assertEqual((result[:first], result[last:last + 0x60], result[last + 0x460:]),
                         (reference[:first], reference[last:last + 0x60], reference[last + 0x460:]))
        with self.assertRaisesRegex(ValueError, "does not fit"):
            embedded_atlas(reference, image[:-1], palette)
        with self.assertRaisesRegex(ValueError, "Unexpected DTM cockpit atlas upload"):
            embedded_atlas(reference[:0x38] + bytes(4) + reference[0x3c:], image, palette)

    def test_rd2_class_texture_normalizes_the_embedded_far_texture(self):
        base, target = 0x2e80b80, 0x4bd0b80
        data = bytearray(0x600)
        far_header = 0x300
        struct.pack_into("<I", data, 8, base + far_header)
        relocations = {8: 0, 0x10: 3, far_header: 3}
        for header in (0x20, far_header + 0x10):
            row = header + 0x10
            struct.pack_into("<2I", data, header, 1, base + row)
            struct.pack_into("<I", data, header - 12, base + 0x500)
            struct.pack_into("<I", data, row + 0x38, 8192)
            struct.pack_into("<I", data, row + 0xcc, base + 0x500)
            struct.pack_into("<I", data, row + 0xe8, base + 0x580)
            relocations.update({header + 4: 0, row + 0xcc: 0, row + 0xe8: 0})

        source = serialize_relocations(data, relocations, base)
        result = convert_textures(source, serialize_relocations(data, relocations, target))

        self.assertEqual(struct.unpack_from("<I", result, 8)[0], target + far_header)
        for row in (0x30, far_header + 0x20):
            self.assertEqual(struct.unpack_from("<I", result, row + 0x38)[0], 1)
            self.assertEqual(struct.unpack_from("<I", result, row + 0xe8)[0], target + 0x580)

    def test_rd2_draw_transforms_use_inline_rd3_matrix_slots(self):
        base = 0x123400
        model = bytearray(0x320)
        sections = [(0x38, 0x1a0), (0x1a0, 0x320)]
        high, lower = 0x100, 0x210
        for (start, _), draw in zip(sections, (high, lower)):
            part = start + 0x30
            struct.pack_into("<2I", model, start + 0x24, base + part, base + part + 0x30)
            struct.pack_into("<I", model, part + 8, base + draw)
            struct.pack_into("<2I", model, draw + 0x5c, 1, 0x112e2e2e)
            struct.pack_into("<I", model, draw + 0x94, base + draw + 0x9c)
        struct.pack_into("<I", model, high, 0x10000000)
        struct.pack_into("<I", model, high + 0x10, 0x10000005)
        struct.pack_into("<2I", model, lower, 0x30000005, base + high + 0x20)
        struct.pack_into("<2I", model, lower + 0x10, 0x20000000, base + lower + 0x70)
        composite = 0x2d0
        struct.pack_into("<4I", model, composite, 0x30000005, base + high + 0x20, 0, 0x6c048000)
        entries = {lower: 3, lower + 0x10: 3, lower + 0x90: 3, composite: 3}

        converted, relocations = convert_draw_transforms(model, base, entries, sections)

        for draw in (high, lower):
            self.assertEqual(struct.unpack_from("<8I", converted, draw),
                             (0x10000000, 0, 0, 0, 0x10000005, 0, 0, 0x6c048000))
            self.assertEqual(struct.unpack_from("<I", converted, draw + 0x5c)[0], 2)
        self.assertEqual(relocations, {lower + 0x90: 3, composite: 3})
        self.assertEqual(struct.unpack_from("<I", converted, lower + 0x94)[0], base + lower + 0x9c)
        self.assertEqual(struct.unpack_from("<I", converted, composite + 4)[0], base + lower + 0x20)

    def test_foundry_route_has_ordered_sector_splits_for_ghost_recording(self):
        main, _, _ = read_route(build_route())
        self.assertEqual(main.events[0][3], 6)
        splits = [(index, event[5]) for index, event in enumerate(main.events) if event[3] == 2]
        self.assertEqual(splits, [(24, 0), (48, 1)])
        self.assertEqual([event[4] for event in main.events if event[3] == 10], [0, 1, 2])

    def test_route_csv_preserves_lanes_and_verifies_the_auxiliary_span(self):
        header = MAGIC + SECTION.pack(4, 1, 1) + SECTION.pack(2, 0x21, 0) + SECTION.pack(3, 3, 0)
        events = b"".join(EVENT.pack(1, -0.0, distance, code, 255, 0, 0) for distance, code in
                          ((100, 6), (15, 13), (60, 0), (80, 12), (90, 0), (5, 0), (80, 0), (100, 0), (15, 0)))
        points = b"".join(POINT.pack(-i - 0.125, i + 0.75) for i in range(14))
        original = header + events + points
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source, table = work / "source.ail", work / "stations.csv"
            output = work / "roundtrip.ail"
            source.write_bytes(original)
            route_export(SimpleNamespace(input=source, output=table))
            args = SimpleNamespace(input=source, csv=table, output=output, resize=False)
            route_import(args)
            self.assertEqual(output.read_bytes(), original)
            with table.open(newline="", encoding="utf-8") as stream:
                reader = csv.DictReader(stream)
                fields = reader.fieldnames
                rows = list(reader)

            def write_table():
                with table.open("w", newline="", encoding="utf-8") as stream:
                    writer = csv.DictWriter(stream, fields)
                    writer.writeheader()
                    writer.writerows(rows)

            self.assertEqual(rows[0]["x5"], "")
            self.assertEqual(float(rows[4]["x5"]), -6.125)
            rows[4]["x5"] = "-5.5"
            rows[1]["code"], rows[2]["code"] = rows[2]["code"], rows[1]["code"]
            write_table()
            args.output = work / "edited.ail"
            with self.assertRaisesRegex(ValueError, "do not span"):
                route_import(args)
            self.assertFalse(args.output.exists())
            rows[1]["code"], rows[2]["code"] = rows[2]["code"], rows[1]["code"]
            write_table()
            route_import(args)
            edited = read_route(args.output.read_bytes())
            self.assertEqual(edited[1].lanes[1][0], (-5.5, 6.75))
            self.assertEqual(edited[0], read_route(original)[0])

            rows[2:2] = [dict(rows[2], distance_m="40", x0="-1.5")]
            for station, row in enumerate(rows[:5]):
                row["station"] = str(station)
            args.output = work / "resized.ail"
            write_table()
            with self.assertRaisesRegex(ValueError, "Use --resize"):
                route_import(args)
            args.resize = True
            route_import(args)
            resized = read_route(args.output.read_bytes())
            self.assertEqual([len(section.events) for section in resized], [5, 2, 3])
            self.assertEqual(resized[0].events[2][2], 40)
            self.assertEqual(resized[0].lanes[0][2][0], -1.5)
            self.assertEqual(resized[1:], edited[1:])

            # Put the additional station inside the wrapped lap-boundary span.
            rows[1], rows[2] = rows[2], rows[1]
            rows[1]["station"], rows[2]["station"] = "1", "2"
            args.output = work / "resized-auxiliary.ail"
            write_table()
            with self.assertRaisesRegex(ValueError, "do not span"):
                route_import(args)
            rows.insert(-1, dict(rows[-1], station="2", distance_m="5"))
            rows[-1]["station"] = "3"
            write_table()
            route_import(args)
            resized = read_route(args.output.read_bytes())
            self.assertEqual([len(section.events) for section in resized], [5, 2, 4])
            self.assertEqual(resized[2].events[2][2], 5)

            rows[:] = [row for row in rows if (row["section"], row["station"]) != ("pit", "1")]
            args.output = work / "shorter-pit.ail"
            write_table()
            route_import(args)
            shortened = read_route(args.output.read_bytes())
            self.assertEqual(shortened[1].events, resized[1].events[:1])
            self.assertEqual(shortened[1].lanes, tuple(lane[:1] for lane in resized[1].lanes))

    def test_scene_append_links_a_new_root_and_serializes_authored_positions(self):
        base, root, leaf, packet_at = 0x200000, 0x10, 0x30, 0xa0
        packet = struct.pack("<5I", 0x6c018000, 0x100, 3, 0x107, 0)
        for i in range(7):
            packet += struct.pack("<I", 0x6c010100 + i)
            if i == 6:
                giftag = 1 << 46 | 4 << 47 | 3
                packet += struct.pack("<2Q", giftag, 0x512)
            else:
                packet += bytes(16)
        packet += struct.pack("<I6f", 0x74030107, 0, 0, 1, 0, 0, 1)
        packet += struct.pack("<I", 0x6e030108) + bytes((70, 80, 90, 128)) * 3
        packet += struct.pack("<I9f", 0x68030109, 0, 0, 0, 3, 0, 0, 0, 0, 4)
        packet += struct.pack("<2I", 0x10000000, 0x17000000)
        packet += bytes(-len(packet) % 16)
        payload = bytearray(packet_at)
        struct.pack_into("<I", payload, 0, base + root)
        struct.pack_into("<3I", payload, root, len(packet), base + leaf, base + packet_at)
        struct.pack_into("<2I", payload, leaf, 0x30000000 | len(packet) // 16, base + packet_at)
        struct.pack_into("<I", payload, leaf + 0x40, len(packet))
        struct.pack_into("<I", payload, leaf + 0x48, base + packet_at)
        struct.pack_into("<I", payload, leaf + 0x60, 1)
        payload.extend(packet)
        relocations = [(0, 0), (root + 4, 0), (root + 8, 0), (root + 24, 0), (leaf, 3), (leaf + 0x48, 0)]
        original = payload + b"".join(RELOCATION.pack(*row) for row in relocations)
        original += FOOTER.pack(len(relocations), len(payload), base)

        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            template, obj, output = work / "stock.dma", work / "new.obj", work / "authored.dma"
            template.write_bytes(original)
            obj.write_text("v 10 3 20\nv 13 4 20\nv 10 3 24\nf 1 2 3\n", encoding="ascii")
            args = SimpleNamespace(command="scene-append", input=template, output=output, obj=obj, root=root, leaf=leaf,
                                   rgb=(1, 2, 3), offset_y=0.5)
            scene_append(args)
            scene = Scene(output.read_bytes())
            args.command = "scene-replace"
            args.output = work / "replacement.dma"
            scene_append(args)
            replacement = Scene(args.output.read_bytes())

        self.assertEqual(scene.data[packet_at:packet_at + len(packet)], packet)
        self.assertEqual(scene.roots[0], root)
        added_root, = scene.roots[1:]
        added_leaf, = scene.leaves(added_root)
        self.assertEqual(replacement.roots, [added_root])
        self.assertEqual(list(replacement.leaves(added_root)), [added_leaf])
        material = scene.material(added_root, added_leaf)
        self.assertEqual(material.colors, bytes((1, 2, 3, 128)) * 3)
        start = scene.word(added_leaf + 4) - scene.base
        length = scene.word(added_leaf + 0x40)
        positions, = (c for c in vif_commands(scene.data, start, start + length) if c.operation == 0x68)
        self.assertEqual(tuple(SCENE_VERTEX.iter_unpack(scene.data[positions.payload:positions.payload + positions.size])),
                         ((10, 3.5, 20), (13, 4.5, 20), (10, 3.5, 24)))
        self.assertEqual(SCENE_VERTEX.unpack_from(scene.data, added_leaf + 0x20), (10, 3.5, 20))
        self.assertEqual(SCENE_VERTEX.unpack_from(scene.data, added_leaf + 0x30), (13, 4.5, 24))

    def test_collision_append_remaps_existing_references_and_adds_the_authored_face(self):
        first_cell, later_cell, existing_reference = 2 * 256 + 2, 220 * 256 + 220, 221 * 256 + 220
        source_vertices = b"".join(VERTEX.pack(0, 100, 200, x, z) for x, z in
                                   ((2, 2), (3, 2), (2, 3), (220, 220), (221, 220), (220, 221)))
        original_polygons = POLYGON.pack(0xffff, 7, 0) + POLYGON.pack(0xffff, 9, 1)
        original_faces = TRIANGLE.pack(0, 1, 2) + TRIANGLE.pack(3, 4, 5)
        cells = b"".join(CELL.pack(int(i > first_cell) + int(i > later_cell), int(i > existing_reference))
                         for i in range(GRID_CELLS))
        grid = cells + REFERENCE.pack(1)
        original = struct.pack("<6f4I", 0, 0, 0, 256, 8, 256, len(grid), 2, 6, 0)
        original += source_vertices + original_polygons + original_faces + grid
        flags = b"\xa5" * (GRID_CELLS // 8)
        original += bytes(-len(original) % 4) + flags

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template, obj, output = root / "stock.col", root / "hump.obj", root / "edited.col"
            template.write_bytes(original)
            obj.write_text("v 10 3 30\nv 14 3 30\nv 10 3 34\nf -3 -2 -1\n", encoding="ascii")
            args = SimpleNamespace(command="collision-append", input=template, output=output, obj=obj, surface_from=0)
            collision_append(args)
            mesh = Collision(output.read_bytes())
            args.command = "collision-build"
            args.output = root / "replacement.col"
            collision_append(args)
            replacement = Collision(args.output.read_bytes())

        self.assertEqual(mesh.flags, flags)
        self.assertEqual(mesh.raw_vertices[:len(source_vertices)], source_vertices)
        self.assertEqual(mesh.triangles, ((0, 1, 2), (6, 7, 8), (3, 4, 5)))
        self.assertEqual(mesh.polygons, original_polygons[:4] + POLYGON.pack(0xffff, 7, 0) + original_polygons[4:])
        def in_cell(cell):
            return mesh.references[mesh.starts[cell][1]:mesh.starts[cell + 1][1]]

        self.assertEqual(in_cell(existing_reference), (2,))
        self.assertEqual(in_cell(33 * 256 + 13), (1,))
        self.assertAlmostEqual(mesh.world(mesh.vertices[6])[1], 3, places=3)
        self.assertEqual(replacement.triangles, ((0, 1, 2),))
        self.assertEqual(replacement.polygons, POLYGON.pack(0xffff, 7, 0))
        self.assertEqual(replacement.flags, bytes(len(flags)))
        for actual, expected in zip(replacement.world(replacement.vertices[0]), (10, 3, 30)):
            self.assertAlmostEqual(actual, expected, places=3)

    def test_track_catalog_moves_directory_base_for_separate_imported_slots(self):
        foundry = TrackEntry("tqa4", "Foundry Oval", "0.702", 36)
        reserved = {course.record for course in (ROAD_AMERICA, *A1_RING, foundry)}
        stock = {
            f"c{index:03}.ini".encode("ascii"): f"HOFIndex = {index}\r\n".encode("ascii")
            for index in range(84) if index not in reserved
        }
        original = repack_bigf(b"BIGF" + bytes(0x4800 - 4), stock, 0x7C0, 0x800, 0x4300)
        legacy, legacy_base = read_bigf(track_catalog(original), 81)
        expanded_catalog = track_catalog(original, (ROAD_AMERICA, *A1_RING))
        expanded, base = read_bigf(expanded_catalog, 83)
        self.assertEqual(legacy_base, 0x7C0)
        self.assertEqual(base, 0x800)
        self.assertEqual({name: expanded[name] for name in legacy}, legacy)
        for course in A1_RING:
            label = course.name.encode("ascii")
            self.assertIn(b"FullName = " + label + b"\r\n", expanded[f"{course.slot}.ini".encode("ascii")])
        fourth, base = read_bigf(track_catalog(expanded_catalog, (foundry,), existing=83), 84)
        self.assertEqual(base, 0x820)
        self.assertIn(b"HOFIndex = 36\r\n", fourth.pop(b"tqa4.ini"))
        self.assertEqual(fourth, expanded)

    def test_only_new_a1_ring_calendar_rounds_offer_sunny_weather(self):
        calendar = (
            b"[Info]\r\nRacesNum=9\r\n\r\n[Race 1]\r\nTrackID=hoc3\r\n"
            b"Weather1=SUNNY\r\nWeather2=RAIN\r\nWeatherProb1=90\r\nWeatherProb2=10\r\n"
            b"Laps=1\r\n\r\n[Race 2]\r\nTrackID=another\r\n"
        )
        other = {f"e{index:03}.ini".encode("ascii"): b"untouched" for index in range(203)}
        members = {**other, b"rccuf.ini": calendar}
        original = repack_bigf(b"BIGF" + bytes(0x4000 - 4), members, 0x1360, 0x1360, 0x4000)
        expanded, _ = read_bigf(event_catalog(original, (ROAD_AMERICA, *A1_RING)), 204)
        result = expanded.pop(b"rccuf.ini")
        self.assertEqual(expanded, other)
        self.assertIn(b"RacesNum=13\r\n", result)
        for section in (b"[Race 10]", b"[Race 11]"):
            body = result.split(section + b"\r\n", 1)[1].split(b"\r\n[", 1)[0]
            self.assertIn(b"Weather2=RAIN\r\n", body)
        for section, slot in ((b"[Race 12]", b"tqa2"), (b"[Race 13]", b"tqa3")):
            body = result.split(section + b"\r\n", 1)[1].split(b"\r\n[", 1)[0]
            self.assertIn(b"TrackID=" + slot + b"\r\n", body)
            self.assertIn(b"WeatherProb1=100\r\n", body)
            self.assertNotIn(b"Weather2", body)
            self.assertNotIn(b"WeatherProb2", body)
        foundry = TrackEntry("tqa4", "Foundry Oval", "0.702", 36)
        existing = event_catalog(original, (ROAD_AMERICA, *A1_RING))
        fourth, _ = read_bigf(event_catalog(existing, (foundry,), existing_rounds=13, add_oschersleben=False), 204)
        added = fourth.pop(b"rccuf.ini")
        self.assertEqual(fourth, other)
        first, last = added.split(b"[Race 14]\r\n")
        self.assertIn(b"RacesNum=14\r\n", first)
        self.assertEqual(first.count(b"TrackID=osc1\r\n"), 1)
        self.assertIn(b"TrackID=tqa4\r\n", last)
        self.assertIn(b"WeatherProb1=100\r\n", last)
        self.assertNotIn(b"Weather2=RAIN", last)

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

    def test_growing_nested_jpak_reuses_capacity_in_its_outer_package(self):
        inner = self.package()[:196]
        outer = bytearray(self.package())
        struct.pack_into("<III", outer, 36, len(inner), 128, len(inner))
        struct.pack_into("<I", outer, 72, 448)
        outer[128:128 + len(inner)] = inner
        outer[448:452] = b"KEEP"
        replacement = bytes(range(80))
        with self.assertRaisesRegex(ValueError, "exceeds the original package extent"):
            replace_member(inner, ["one.dat"], replacement)
        edited = replace_member(bytes(outer), ["one.dat", "one.dat"], replacement)
        self.assertEqual(len(edited), len(outer))
        self.assertEqual(find_member(edited, "two.dat")[0].read(edited), b"KEEP")
        rebuilt = find_member(edited, "one.dat")[0].read(edited)
        self.assertGreater(len(rebuilt), len(inner))
        self.assertEqual(find_member(rebuilt, "one.dat")[0].read(rebuilt), replacement)
        self.assertEqual(find_member(rebuilt, "two.dat")[0].read(rebuilt), b"BBBB")

    def test_compact_encoding_round_trips_across_the_ring_boundary(self):
        sample = bytes(random.Random(5).choices(range(9), k=5096)) + b"AABBAAAAABB" * 30
        compact = encode_lzss_compact(sample)
        self.assertLessEqual(len(compact), len(encode_lzss(sample)))
        self.assertEqual(bytes(unpack_lzss(compact, len(sample))), sample)

    def test_car_csv_round_trip_and_position_only_edit(self):
        mesh = bytearray(struct.pack("<9I", 0x6c028000, 1, 2, 0x40, 2, 0x60, 6, 0, 0))
        mesh.extend(struct.pack("<I4f", 0x64020040, 0, 0, 1, 1))
        mesh.extend(struct.pack("<I6f", 0x68020042, 1, 2, 3, 4, 5, 6))
        mesh.extend(struct.pack("<I6f", 0x68020060, 0, 1, 0, 0, 1, 0))
        call = len(mesh)
        mesh.extend(struct.pack("<I", 0x14000001))
        mesh.extend(bytes(-len(mesh) % 16))
        payload = len(mesh)
        mesh.extend(struct.pack("<5I", call, 4, 1, payload, 0x02bd0b60))
        _, streams = mesh_packets(mesh)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stock = root / "stock.msh"
            positions = root / "positions.csv"
            output = root / "roundtrip.msh"
            stock.write_bytes(mesh)
            mesh_export(SimpleNamespace(mesh=stock, output=positions))
            mesh_import(SimpleNamespace(mesh=stock, positions=positions, output=output))
            self.assertEqual(output.read_bytes(), mesh)
            with positions.open(newline="", encoding="utf-8") as stream:
                rows = list(csv.reader(stream))
            rows[1][2] = "0.8"
            with positions.open("w", newline="", encoding="utf-8") as stream:
                csv.writer(stream).writerows(rows)
            output = root / "edited.msh"
            mesh_import(SimpleNamespace(mesh=stock, positions=positions, output=output))
            struct.pack_into("<f", mesh, streams[0].position, 0.8)
            self.assertEqual(output.read_bytes(), mesh)

    def test_car_detail_levels_follow_model_dma_block_extents(self):
        base = 0x02bd0b60
        model = bytearray(64)
        struct.pack_into("<2I", model, 0, 0x30000002, base)
        struct.pack_into("<2I", model, 16, 0x30000002, base + 32)
        struct.pack_into("<2I", model, 48, 0x30000004, base + 64)
        sections = [(0, 32), (32, 64)]
        packets = [MeshPacket(position, 0, 0, 1, True) for position in (4, 36, 68, 100)]
        self.assertEqual(lod_packet_ranges(model, sections, base, 128, packets),
                         [range(0, 2), range(2, 4)])
        struct.pack_into("<I", model, 52, base + 80)
        with self.assertRaisesRegex(ValueError, "contiguous mesh blocks"):
            lod_packet_ranges(model, sections, base, 128, packets)

    def test_car_part_map_checks_indices_at_each_detail_level(self):
        counts = {0: 3, 1: 1}
        data = bytearray(struct.pack("<9I", 1, 2, 3, 0, 2, 2, 0xffffffff, 0, 0xffffffff))
        self.assertEqual(part_map_coverage(data, counts), {
            "entries_per_lod": 3,
            "lods": {0: {"assigned_slots": 3, "distinct_parts": 2},
                     1: {"assigned_slots": 1, "distinct_parts": 1}},
        })
        struct.pack_into("<I", data, 28, 2)
        with self.assertRaisesRegex(ValueError, "LOD 1 slot 1 refers to part 2"):
            part_map_coverage(data, counts)
        with self.assertRaisesRegex(ValueError, "2 detail levels, expected 1"):
            part_map_coverage(data, {0: 3})

    def test_car_obj_replacement_packs_independent_faces_into_fixed_capacity(self):
        count = 9
        mesh = bytearray(struct.pack("<9I", 0x6c028000, 1, 2, 0x40, count, 0x60, 6, 0, 0))
        for command, width in ((0x64090040, 8), (0x68090042, 12), (0x68090060, 12)):
            mesh.extend(struct.pack("<I", command) + bytes(count * width))
        gif = count | 1 << 46 | 4 << 47 | 3 << 60
        mesh.extend(struct.pack("<IQQ", 0x6c010090, gif, 0x512))
        call = len(mesh)
        mesh.extend(struct.pack("<I", 0x14000001))
        mesh.extend(bytes(-len(mesh) % 16))
        mesh.extend(struct.pack("<5I", call, 4, 1, len(mesh), 0x02bd0b60))
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source, obj, output = work / "source.msh", work / "new.obj", work / "new.msh"
            source.write_bytes(mesh)
            obj.write_text("g packet_0\nv 0 0 0\nv 0 0 1\nv 1 0 0\nv 2 0 0\nv 2 0 1\nv 3 0 0\n"
                           "vt 0 0\nvt 0 1\nvt 1 0\nf 1/1 2/2 3/3\nf -3/1 -2/2 -1/3\n", encoding="ascii")
            args = SimpleNamespace(mesh=source, obj=obj, output=output)
            mesh_replace(args)
            edited = output.read_bytes()
            self.assertEqual(len(edited), len(mesh))
            base, (stream,) = mesh_packets(edited)
            self.assertEqual((base, stream.count), (0x02bd0b60, count))
            corners = list(SCENE_VERTEX.iter_unpack(edited[stream.position:stream.position + count * 12]))
            faces = []
            for i in range(count - 2):
                a, b, c = corners[i:i + 3]
                if len({a, b, c}) == 3:
                    faces.append((b, a, c) if i % 2 else (a, b, c))
            self.assertEqual(faces, [((0, 0, 0), (0, 0, 1), (1, 0, 0)),
                                     ((2, 0, 0), (2, 0, 1), (3, 0, 0))])
            self.assertEqual(UV.unpack_from(edited, stream.uv + 5 * UV.size), (0, 1))
            self.assertEqual(SCENE_VERTEX.unpack_from(edited, stream.normal), (0, 1, 0))
            self.assertEqual(edited[call:], mesh[call:])
            with obj.open("a", encoding="ascii") as stream:
                stream.write("f 1/1 2/2 3/3\n")
            args.output = work / "too-large.msh"
            with self.assertRaisesRegex(ValueError, "has room for 9"):
                mesh_replace(args)
            self.assertFalse(args.output.exists())

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
