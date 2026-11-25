"""Exercise RD2 archive discovery and route validation without a retail disc."""

from io import BytesIO
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from BuildRoadAmericaMod import convert_pit, convert_route, pit_distances, road_america_weather, route_counts
from ImportRd2Car import discover_mechanics
from ImportRd2Track import check_ground, check_ground_segments
from Rd2AssetCatalog import BIGF_ENTRY, HEADER, HEADER_BYTES, SECTOR_SIZE, read_index, scan_disc
from Ps2TrackCollision import GRID_CELLS
from Ps2TrackRoute import PIT_STALL_COUNT, read_route


def archive(names):
    base = HEADER_BYTES + len(names) * BIGF_ENTRY.size
    header = HEADER.pack(b"BIGF", len(names), base).ljust(HEADER_BYTES, b"\0")
    table = b"".join(BIGF_ENTRY.pack(name, 1, index) for index, name in enumerate(names))
    return b"\0" * SECTOR_SIZE + header + table + b"?" * len(names)


class Rd2AssetCatalogTests(unittest.TestCase):
    def test_cockpit_and_damage_lookup_uses_the_number_configuration_variant(self):
        def package(number, damage, interior):
            files = {"num.ini": number, "dmg.ini": damage, "int.ini": interior}
            return SimpleNamespace(names=tuple(files), member=lambda _, name: files[name])

        prefix = package(b"[bs_01_0]\r\n", b"other damage", b"other interior")
        first = package(b"[BS_0_0]\r\n", b"evo damage", b"evo interior")
        with patch("ImportRd2Car.scan_disc", return_value=(prefix, first, first)):
            self.assertEqual(discover_mechanics(Path("RD2"), "bs_0"), (b"evo damage", b"evo interior"))
        other = package(b"[bs_0]\r\n", b"different damage", b"evo interior")
        with patch("ImportRd2Car.scan_disc", return_value=(first, other)):
            with self.assertRaisesRegex(ValueError, "found 2"):
                discover_mechanics(Path("RD2"), "bs_0")

    def test_disc_scan_finds_relocated_package_with_an_unknown_directory(self):
        with TemporaryDirectory() as parent:
            disc = Path(parent)
            (disc / "RD2.DIR").write_bytes(bytes(16))
            archive_path = disc / "RD2_2.HUG"
            archive_path.write_bytes(bytes(3 * SECTOR_SIZE) + archive((b"COL.COL", b"ROA_TRK.DMA")))
            package, = scan_disc(disc)
            self.assertEqual((package.hug, package.sector), (2, 4))
            self.assertEqual(package.member(disc, "ROA_TRK.DMA"), b"?")

    def test_unknown_roa_weather_requires_selection_when_multiple_scenes_exist(self):
        data = archive((b"roa_trk.dma", b"col.col"))
        sunny = read_index(BytesIO(data), SECTOR_SIZE, len(data), 2)
        rain = read_index(BytesIO(data), SECTOR_SIZE, len(data), 1)
        with self.assertRaisesRegex(ValueError, "Could not identify a sunny Road America scene"):
            road_america_weather(None, (rain, sunny))
        self.assertEqual(road_america_weather(None, (rain, sunny), 2, 1), (sunny, rain))
        with self.assertRaisesRegex(ValueError, "Choose different Road America scenes"):
            road_america_weather(None, (rain, sunny), 2, 2)

    def test_index_resolves_members_relative_to_data_base(self):
        data = archive((b"COL.COL", b"ADE.AID"))
        package = read_index(BytesIO(data), SECTOR_SIZE, len(data), 1)
        self.assertEqual((package.hug, package.sector, package.size), (1, 1, len(data) - SECTOR_SIZE))
        self.assertEqual(package.entries, (("ade.aid", package.size - 1, 1),
                                           ("col.col", package.size - 2, 1)))

    def test_index_rejects_truncated_and_duplicate_members(self):
        data = archive((b"COL.COL", b"col.col"))
        self.assertIsNone(read_index(BytesIO(data), SECTOR_SIZE, len(data), 0))
        data = archive((b"ADE.AID",))[:-1]
        self.assertIsNone(read_index(BytesIO(data), SECTOR_SIZE, len(data), 0))

    def test_route_counts_require_complete_closed_circuit_sections(self):
        main, pit, grid = 3, 2, 4
        source = struct.pack("<6sH4x", bytes.fromhex("060d01200005"), main) + bytes(main * 48)
        source += struct.pack("<BBH4x", 1, 3, pit) + bytes(pit * 32)
        source += struct.pack("<BBH4x", 2, 2, grid) + bytes(grid * 24)
        self.assertEqual(route_counts(source), (main, pit, grid))
        with self.assertRaisesRegex(ValueError, "truncated RD2 grid route"):
            route_counts(source[:-1])

    def test_collision_audit_distinguishes_floor_from_wall_and_open_space(self):
        mesh = SimpleNamespace(
            lower=(0., 0., 0.), spans=(256., 16., 256.),
            vertices=((0., 0., 0.), (0., 0., 1.), (1., 0., 0.), (1., 2., 0.)),
            triangles=((0, 1, 2), (0, 2, 3)), world=lambda vertex: vertex,
            starts=((0, 0),) + ((2, 0),) * (GRID_CELLS - 1), references=(),
        )
        routes = {"main": [(0.25, 0.25), (0.75, 0.75)], "pit": [(0.5, 0.0)]}
        self.assertEqual(dict(check_ground(mesh, routes)), {"main": [1], "pit": []})

    def test_collision_audit_finds_gap_between_supported_stations(self):
        mesh = SimpleNamespace(
            lower=(0., 0., 0.), spans=(256., 16., 256.),
            vertices=((0., 0., 0.), (0., 0., 1.), (1., 0., 0.),
                      (3., 0., 0.), (3., 0., 1.), (4., 0., 0.)),
            triangles=((0, 1, 2), (3, 4, 5)), world=lambda vertex: vertex,
            starts=((0, 0), (1, 0), (1, 0), (1, 0)) + ((2, 0),) * (GRID_CELLS - 4),
            references=(),
        )
        routes = {"main": [(0.2, 0.2), (3.2, 0.2)]}
        self.assertEqual(dict(check_ground(mesh, routes)), {"main": []})
        self.assertEqual(check_ground_segments(mesh, routes), {"main": [0]})
        self.assertEqual(check_ground_segments(mesh, routes, {"main"}), {"main": [0, 1]})

    def test_route_conversion_rejects_ambiguous_grid_markers(self):
        source = struct.pack("<6sH4x", bytes.fromhex("060d01200005"), 3) + bytes(3 * 5 * 8)
        source += b"".join(struct.pack("<HBBf", 0, 0, code, 0.) for code in (12, 13, 12))
        source += struct.pack("<BBH4x", 1, 3, 1) + bytes(32)
        source += struct.pack("<BBH4x", 2, 2, 2) + bytes(48)
        with self.assertRaisesRegex(ValueError, "exactly one start and end marker"):
            convert_route(source, (3, 1, 2))

    def test_route_conversion_pairs_stalls_across_the_start_line(self):
        def section(lanes, rows):
            return (b"".join(struct.pack("<2f", *point) for lane in lanes for point in lane)
                    + b"".join(struct.pack("<HBBf", *row) for row in rows))

        main = ([(0., 0.), (0., 10.), (0., 20.)], [(6., 0.), (6., 10.), (6., 20.)])
        pit = ([(10., -2.), (10., 0.), (10., 10.)], [(16., -2.), (16., 0.), (16., 10.)],
               [(19., -2.), (19., 0.), (19., 10.)])
        source = struct.pack("<6sH4x", bytes.fromhex("060d01200005"), 3)
        source += section(main + (main[0],) * 3, ((255, 0, 6, 100.), (0, 0, 12, 10.), (0, 0, 13, 20.)))
        source += struct.pack("<BBH4x", 1, 3, 3)
        source += section(pit, ((0, 7, 3, 98.), (0, 0, 6, 0.), (0, 0, 3, 10.)))
        source += struct.pack("<BBH4x", 2, 2, 2)
        source += section(tuple(lane[1:] for lane in main), ((0, 0, 0, 10.), (0, 0, 0, 20.)))
        _, converted, _ = read_route(convert_route(source, (3, 3, 2)))
        self.assertEqual(converted.events[0][2:6], (98., 3, 7, 1))
        self.assertEqual(converted.events[1][2:6], (99., 4, 7, 0))
        self.assertEqual(converted.lanes[2], ((13., -2.), (13., -1.), (13., 0.), (13., 10.)))
        self.assertEqual(converted.lanes[3], ((19., -2.), (19., -1.), (19., 0.), (19., 10.)))

    def test_full_pit_grid_preserves_the_service_ribbon_and_finish_gate(self):
        stations = (0., 20., 60., 100., 140., 160.)
        lanes = tuple([(x, z) for z in stations] for x in (0., 6., 5.))
        donor = ((0, 0, 14, 80.), (0, 3, 3, 84.), (0, 0, 6, 98.),
                 (0, 4, 3, 3.), (0, 5, 3, 10.), (0, 0, 15, 15.))

        coordinates, events = convert_pit(lanes, donor, 200.)
        events = pit_distances(coordinates, events, 200.)

        starts = [tag for tag, argument, code, _ in events if (code, argument) == (3, 1)]
        ends = [tag for tag, _, code, _ in events if code == 4]
        self.assertEqual(starts, list(range(PIT_STALL_COUNT)))
        self.assertEqual(ends, starts)
        finish, = (i for i, (_, _, code, _) in enumerate(events) if code == 6)
        self.assertEqual((events[finish][3], coordinates[2][finish]), (0., (3., 60.)))
        for i, (a, b) in enumerate(zip(events, events[1:])):
            self.assertAlmostEqual((b[3] - a[3]) % 200.,
                                   coordinates[2][i + 1][1] - coordinates[2][i][1], places=4)
        self.assertTrue(all(x == 3. for x, _ in coordinates[2]))
        self.assertTrue(all(x == 5. for x, _ in coordinates[3]))
        for tag in starts:
            first, = (i for i, e in enumerate(events) if e[:3] == (tag, 1, 3))
            last, = (i for i, e in enumerate(events) if e[:3] == (tag, 0, 4))
            self.assertAlmostEqual(coordinates[3][last][1] - coordinates[3][first][1], 4., delta=.051)


if __name__ == "__main__":
    unittest.main()
