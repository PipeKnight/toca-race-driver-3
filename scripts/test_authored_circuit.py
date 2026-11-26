"""Regression checks for original circuits and the RD2 import front end."""

import configparser
import json
import math
import struct
from pathlib import Path
import tempfile
import unittest

from BuildAuthoredCircuit import (
    GRID_APPROACH_METRES, PIT_HALF_WIDTH, Circuit, build_replay_cameras, build_route, edges_touch, pit_inner_edge, pit_offset,
    preview, validate_ribbon,
)
from BuildFoundryOval import copy_circuit_files
from BuildRoadAmericaMod import TrackEntry, read_bigf, repack_bigf, track_catalog
from ImportRd2Car import variants
from Ps2TrackCollision import read_triangles
from Ps2TrackRoute import PIT_STALL_COUNT, read_route
from Ps2TrackScene import Material, triangle_batch


class AuthoredCircuitTests(unittest.TestCase):
    def layout(self):
        return json.loads((Path(__file__).resolve().parents[1] / "tracks/tsukuba.json").read_text(encoding="utf-8"))

    def test_pack_extension_keeps_existing_replay_cameras(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            source.mkdir()
            for name in ("TRACK.JPK", "DMA1.JPK"):
                (source / name).write_bytes(name.encode("ascii"))
            camera = b"[Cameras]\r\nuNumCameras=0\r\n"
            (source / "replay-cameras.ini").write_bytes(camera)
            target = Path(temporary) / "target"
            copy_circuit_files(source, target)
            self.assertEqual((target / "replay-cameras.ini").read_bytes(), camera)

    def test_generated_replay_zones_reference_trackside_cameras(self):
        circuit = Circuit(self.layout())
        config = configparser.ConfigParser()
        config.read_string(build_replay_cameras(circuit).decode("ascii"))
        count = config.getint("Cameras", "uNumCameras")
        self.assertEqual(count, config.getint("Activation_Zones", "uNumActivationZones"))
        for i in range(count):
            with self.subTest(camera=i):
                section = config[f"Camera_{i:03}"]
                self.assertIs(section.getboolean("boRaceStart"), i == 0)
                self.assertAlmostEqual(math.hypot(*(section.getfloat(f"fDirection{axis}") for axis in "xyz")),
                                       1., places=5)
                zone = config[f"Activation_Zone_{i:03}"]
                self.assertEqual(zone.getint("uCamera000"), i)
                self.assertEqual(zone.getint("uNumVertices"), 4)
                x = sum(zone.getfloat(f"fVertex{j:03}x") for j in range(4)) / 4
                z = sum(zone.getfloat(f"fVertex{j:03}z") for j in range(4)) / 4
                self.assertLess(math.dist((x, z), circuit.position(i * circuit.length / count)), 1.)

    def test_route_contains_ordered_ghost_splits_and_independent_pit_lane(self):
        circuit = Circuit(self.layout())
        main, pit, auxiliary = read_route(build_route(circuit))
        self.assertEqual(main.events[0][2:4], (2045.0, 6))
        self.assertEqual(len(main.events), 256)
        self.assertEqual([event[5] for event in main.events if event[3] == 2], [0, 1])
        self.assertEqual([event[4] for event in main.events if event[3] == 10], [0, 1, 2])
        self.assertAlmostEqual(math.dist(main.lanes[0][0], main.lanes[4][0]), circuit.width, places=3)
        self.assertEqual([event[3] for event in pit.events if event[3] not in (0, 3, 4)], [5, 14, 6, 15, 11])
        self.assertEqual(sum(event[3] == 1 for event in main.events), 1)
        self.assertEqual([event[3:6] for event in main.events if event[3] == 3], [(3, 255, 1)])
        self.assertEqual(pit.events[-1][3:6], (3, 255, 0))
        self.assertEqual(len(pit.events), 63)
        stalls = [(i, event[4]) for i, event in enumerate(pit.events) if event[3:6:2] == (3, 1)]
        self.assertEqual([tag for _, tag in stalls], list(range(PIT_STALL_COUNT)))
        for i, tag in stalls:
            end, = (e for e in pit.events[i + 1:] if e[3:6] == (4, tag, 0))
            self.assertAlmostEqual((end[2] - pit.events[i][2]) % circuit.length, 4.)
        for gate in (5, 11, 14, 15):
            i, = (i for i, event in enumerate(pit.events) if event[3] == gate)
            d = pit.events[i][2]
            d = d - circuit.length if d > circuit.length / 2 else d
            center = circuit.offset(d, pit_offset(d, circuit.width))
            self.assertLess(math.dist(center, pit.lanes[2][i]), .0001)
            self.assertLess(math.dist(circuit.offset(d, pit_inner_edge(d, circuit.width)), pit.lanes[0][i]), .0001)
            self.assertLess(math.dist(circuit.offset(d, pit_offset(d, circuit.width) + PIT_HALF_WIDTH),
                                      pit.lanes[1][i]), .0001)
            self.assertGreater(math.dist(circuit.position(d), pit.lanes[0][i]), circuit.width / 2)
            if gate == 5:
                self.assertEqual(d, -55)
                self.assertAlmostEqual(math.dist(circuit.position(d), pit.lanes[0][i]), circuit.width / 2 + .4,
                                       places=3)
        self.assertGreater(pit.events[0][2], pit.events[-1][2])
        self.assertGreater(auxiliary.events[0][2], auxiliary.events[-1][2])
        self.assertGreaterEqual(circuit.length - auxiliary.events[0][2], GRID_APPROACH_METRES)
        for code, event in ((12, auxiliary.events[0]), (13, auxiliary.events[-1])):
            marker, = (main_event for main_event in main.events if main_event[3] == code)
            self.assertEqual(marker[:3], event[:3])
        for i, (_, _, distance, *_) in enumerate(auxiliary.events):
            self.assertLess(math.dist(auxiliary.lanes[0][i], circuit.offset(distance, -circuit.width / 6)), .001)
            self.assertLess(math.dist(auxiliary.lanes[1][i], circuit.offset(distance, circuit.width / 6)), .001)

    def test_ai_margin_keeps_the_hairpin_lanes_inside_the_paved_ribbon(self):
        layout = self.layout()
        source = dict(layout, ai_lane_margin_m=0, ai_lane_margin_zones=())
        old, pit, grid = read_route(build_route(Circuit(source)))
        circuit = Circuit(layout)
        main, new_pit, new_grid = read_route(build_route(circuit))
        self.assertEqual((new_pit, new_grid), (pit, grid))
        self.assertEqual(main.events, old.events)
        self.assertEqual(main.lanes[1:4], old.lanes[1:4])
        for target, margin in ((92, 0), (420, 1.25), (610, 2.75), (1215, 2.75)):
            i = min(range(len(circuit.stations)), key=lambda i: abs(circuit.stations[i] - target))
            for lane in (0, 4):
                self.assertAlmostEqual(math.dist(old.lanes[lane][i], main.lanes[lane][i]), margin, places=3)
        with self.assertRaisesRegex(ValueError, "outer lanes"):
            Circuit(dict(layout, ai_lane_margin_m=4, ai_lane_margin_zones=()))

    def test_ai_corner_markers_keep_the_timing_gates_and_pit_route(self):
        layout = self.layout()
        circuit = Circuit(layout)
        main, pit, grid = read_route(build_route(circuit))
        old, old_pit, old_grid = read_route(build_route(Circuit(dict(layout, ai_corners=()))))
        self.assertEqual((pit, grid, main.lanes), (old_pit, old_grid, old.lanes))
        markers = {11: 9, 26: 18, 42: 8, 64: 9, 76: 18, 89: 8,
                   91: 9, 101: 18, 112: 8, 137: 9, 151: 18, 161: 8}
        for i, (after, before) in enumerate(zip(main.events, old.events, strict=True)):
            code = markers.get(i, before[3])
            self.assertEqual(after, (*before[:3], code, *before[4:]))
        with self.assertRaisesRegex(ValueError, "overlaps another route marker"):
            build_route(Circuit(dict(layout, ai_corners=[{"approach_m": 1, "apex_m": 20, "exit_m": 40}])))

    def test_solid_scene_batch_omits_the_inherited_texture_enable_bit(self):
        prefix = bytearray(24)
        gif = 16
        textured_tag = (1 << 46) | (0x1c << 47) | 6
        struct.pack_into("<Q", prefix, gif, textured_tag)
        material = Material(0, 0, prefix, bytes([128, 128, 128, 0] * 3), 0, 0, 0, gif)
        vertices = ((0, 0, 0), (1, 0, 0), (0, 0, 1))
        bounds = ((0, 0, 0), (1, 0, 1))
        colored = triangle_batch(material, vertices, *bounds, (135, 135, 148), textured=False)
        textured = triangle_batch(material, vertices, *bounds, (135, 135, 148))
        header = gif + 4  # FLUSHE precedes the original material prefix.
        before, = struct.unpack_from("<Q", textured, header)
        after, = struct.unpack_from("<Q", colored, header)
        self.assertEqual(before ^ after, 1 << 51)
        self.assertEqual(colored[header + 8:], textured[header + 8:])

    def test_preview_exports_upward_geometry_and_the_same_route(self):
        circuit = Circuit(self.layout())
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            preview(circuit, folder)
            self.assertEqual((folder / "route.ail").read_bytes(), build_route(circuit))
            road, faces = read_triangles(folder / "road.obj")
            self.assertGreater(len(faces), 2 * len(circuit.stations))  # Includes the pit ribbon.
            for i, j, k in faces:
                a, b, c = road[i], road[j], road[k]
                area_y = (b[2] - a[2]) * (c[0] - a[0]) - (b[0] - a[0]) * (c[2] - a[2])
                self.assertGreater(area_y, 0)
            ground, _ = read_triangles(folder / "ground.obj")
            wall, faces = read_triangles(folder / "perimeter.obj")
            floor_positions = {(x, z) for x, _, z in ground}
            cx = (max(x for x, _, _ in ground) + min(x for x, _, _ in ground)) / 2
            cz = (max(z for _, _, z in ground) + min(z for _, _, z in ground)) / 2
            self.assertEqual(len(faces), len(wall))
            for x, y, z in wall:
                self.assertIn((x, z), floor_positions)
                self.assertIn(y, (circuit.height - 0.2, circuit.height + circuit.perimeter_wall))
            for i, j, k in faces:
                a, b, c = wall[i], wall[j], wall[k]
                nx = (b[1] - a[1]) * (c[2] - a[2]) - (b[2] - a[2]) * (c[1] - a[1])
                nz = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
                self.assertGreater(nx * (cx - a[0]) + nz * (cz - a[2]), 0)

    def test_rejects_reordered_sectors_and_a_duplicate_closure(self):
        layout = self.layout()
        with self.assertRaisesRegex(ValueError, "sector fractions"):
            Circuit(dict(layout, sectors=[0.7, 0.3]))
        nodes = layout["centerline"]
        with self.assertRaisesRegex(ValueError, "Coincident"):
            Circuit(dict(layout, centerline=nodes + nodes[:1]))

    def test_rejects_overlapping_road_edges_even_with_a_valid_centerline(self):
        layout = self.layout()
        with self.assertRaisesRegex(ValueError, r"racing surface.*intersects itself near station"):
            Circuit(dict(layout, road_width_m=24))

    def test_rejects_a_folded_strip_and_counts_collinear_overlap(self):
        a, b, c, d = (0, 0), (3, 0), (2, 0), (5, 0)
        self.assertTrue(edges_touch(a, b, c, d))
        self.assertFalse(edges_touch(a, b, (4, 0), d))
        with self.assertRaisesRegex(ValueError, "pit lane folds near station 0"):
            validate_ribbon([(0, 1), (1, -1)], [(0, -1), (1, 1)], "The pit lane", closed=False)

    def test_track_catalog_preserves_the_other_courses_when_adding_a_right_pit_lane(self):
        original = b"BIGF" + bytes(0x4300 - 4)
        stock = {b"osc1.ini": b"[Info]\r\nHOFIndex = 60\r\nPitSide = LEFT\r\n"}
        archive = repack_bigf(original, stock, 128, 128, len(original))
        entries = (TrackEntry("tqa4", "Foundry Oval", "0.702", 36),
                   TrackEntry("tqa5", "Tsukuba Circuit", "2.045", 54, pit_side="RIGHT"))
        result, _ = read_bigf(track_catalog(archive, entries, existing=1), 3)
        self.assertEqual(result[b"osc1.ini"], stock[b"osc1.ini"])
        self.assertIn(b"\r\nPitSide = LEFT\r\n", result[b"tqa4.ini"])
        self.assertIn(b"\r\nPitSide = RIGHT\r\n", result[b"tqa5.ini"])

    def test_car_catalog_reads_variants_without_assuming_the_model_name(self):
        original = bytes(512)
        archive = repack_bigf(b"BIGF" + original[4:],
                              {b"lookup.ini": b"[lookup]\r\nvc_2=db5\r\nvc_0=jag_e\r\n"}, 128, 128, len(original))
        self.assertEqual(variants(archive), {"vc_2": "db5", "vc_0": "jag_e"})


if __name__ == "__main__":
    unittest.main()
