"""Regression checks for original circuits and the RD2 import front end."""

import json
import math
from pathlib import Path
import tempfile
import unittest

from BuildAuthoredCircuit import Circuit, build_route, edges_touch, preview, validate_ribbon
from BuildRoadAmericaMod import TrackEntry, read_bigf, repack_bigf, track_catalog
from ImportRd2Car import variants
from Ps2TrackCollision import read_triangles
from Ps2TrackRoute import read_route


class AuthoredCircuitTests(unittest.TestCase):
    def layout(self):
        return json.loads((Path(__file__).resolve().parents[1] / "tracks/tsukuba.json").read_text(encoding="utf-8"))

    def test_route_contains_ordered_ghost_splits_and_independent_pit_lane(self):
        circuit = Circuit(self.layout())
        main, pit, auxiliary = read_route(build_route(circuit))
        self.assertEqual(main.events[0][2:4], (2045.0, 6))
        self.assertEqual(len(main.events), 256)
        self.assertEqual([event[5] for event in main.events if event[3] == 2], [0, 1])
        self.assertEqual([event[4] for event in main.events if event[3] == 10], [0, 1, 2])
        self.assertAlmostEqual(math.dist(main.lanes[0][0], main.lanes[4][0]), circuit.width, places=3)
        self.assertEqual([event[3] for event in pit.events if event[3] not in (0, 3)], [5, 14, 6, 15, 11])
        self.assertEqual(sum(event[3] == 1 for event in main.events), 1)
        for gate in (5, 11, 14, 15):
            i, = (i for i, event in enumerate(pit.events) if event[3] == gate)
            center = circuit.position(pit.events[i][2])
            self.assertGreater(math.dist(center, pit.lanes[0][i]), circuit.width / 2 + 5)
        self.assertGreater(pit.events[0][2], pit.events[-1][2])
        self.assertGreater(auxiliary.events[0][2], auxiliary.events[-1][2])
        self.assertEqual(len(auxiliary.events), 21)
        self.assertNotEqual(main.lanes[0][0], pit.lanes[0][18])

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
