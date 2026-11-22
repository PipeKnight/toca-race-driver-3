"""Regression checks for archive edits using synthetic payloads."""

import csv
from pathlib import Path
import random
import struct
import tempfile
from types import SimpleNamespace
import unittest

from BuildRoadAmericaMod import (
    A1_RING, ROAD_AMERICA, event_catalog, read_bigf, repack_bigf, track_catalog, unpack_lzss,
)
from BuildTrackCollisionOverlay import encode_lzss, encode_lzss_compact
from ModAssets import find_member, replace_member
from Ps2CarModel import mesh_export, mesh_import, mesh_packets


class ModAssetTests(unittest.TestCase):
    def test_track_catalog_moves_directory_base_for_separate_imported_slots(self):
        reserved = {course.record for course in (ROAD_AMERICA, *A1_RING)}
        stock = {
            f"c{index:03}.ini".encode("ascii"): f"HOFIndex = {index}\r\n".encode("ascii")
            for index in range(83) if index not in reserved
        }
        original = repack_bigf(b"BIGF" + bytes(0x4800 - 4), stock, 0x7C0, 0x800, 0x4300)
        legacy, legacy_base = read_bigf(track_catalog(original), 81)
        expanded, base = read_bigf(track_catalog(original, (ROAD_AMERICA, *A1_RING)), 83)
        self.assertEqual(legacy_base, 0x7C0)
        self.assertEqual(base, 0x800)
        self.assertEqual({name: expanded[name] for name in legacy}, legacy)
        for course in A1_RING:
            label = course.name.encode("ascii")
            self.assertIn(b"FullName = " + label + b"\r\n", expanded[f"{course.slot}.ini".encode("ascii")])

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
