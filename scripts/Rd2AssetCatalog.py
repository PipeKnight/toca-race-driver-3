#!/usr/bin/env python3
"""Discover indexed car and circuit packages on a Race Driver 2 PS2 disc."""

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import struct

from BuildTrackCollisionOverlay import BIGF_ENTRY, DONOR_DIRECTORY_HASH, SECTOR_SIZE


CHUNK_BYTES = 8 * 1024 * 1024
HEADER_BYTES = 0x24
HEADER = struct.Struct("<4sII")


@dataclass(frozen=True)
class AssetPackage:
    hug: int
    sector: int
    size: int
    entries: tuple[tuple[str, int, int], ...]
    archive_name: str | None = None

    @property
    def names(self):
        return tuple(name for name, _, _ in self.entries)

    def path(self, disc):
        return disc / (self.archive_name or f"RD2_{self.hug}.HUG")

    def read(self, disc):
        with self.path(disc).open("rb") as stream:
            stream.seek(self.sector * SECTOR_SIZE)
            data = stream.read(self.size)
        if len(data) != self.size:
            raise ValueError(f"Incomplete BIGF at HUG {self.hug}, sector {self.sector}")
        return data

    def member(self, disc, key):
        for name, offset, length in self.entries:
            if name == key.lower():
                with self.path(disc).open("rb") as stream:
                    stream.seek(self.sector * SECTOR_SIZE + offset)
                    data = stream.read(length)
                if len(data) != length:
                    raise ValueError(f"Incomplete donor member {name}")
                return data
        raise ValueError(f"Missing donor member {key!r} in HUG {self.hug}, sector {self.sector}")


def read_index(stream, offset, limit, hug, archive_name=None):
    if offset + HEADER_BYTES > limit:
        return None
    stream.seek(offset)
    signature, count, base = HEADER.unpack(stream.read(HEADER.size))
    table_bytes = count * BIGF_ENTRY.size
    if signature != b"BIGF" or not 0 < count <= 4096 or not HEADER_BYTES + table_bytes <= base <= limit - offset:
        return None
    stream.seek(offset + HEADER_BYTES)
    rows = stream.read(table_bytes)
    if len(rows) != table_bytes:
        return None
    entries = {}
    extent = base
    for name, length, relative in BIGF_ENTRY.iter_unpack(rows):
        raw = name.split(b"\0", 1)[0]
        finish = base + relative + length
        if not raw or not all(0x20 <= value < 0x7f for value in raw) or finish > limit - offset:
            return None
        key = raw.decode("ascii").lower()
        if key in entries:
            return None
        entries[key] = (base + relative, length)
        extent = max(extent, finish)
    return AssetPackage(hug, offset // SECTOR_SIZE, extent,
                        tuple((name, *entries[name]) for name in sorted(entries)), archive_name)


def scan_disc(disc):
    directory = disc / "RD2.DIR"
    if not directory.is_file():
        raise ValueError(f"Missing {directory}. Pass the mounted or extracted Race Driver 2 PS2 disc root")
    archives = sorted(path for path in disc.iterdir()
                      if re.fullmatch(r"RD2_[0-9]+\.HUG", path.name, re.IGNORECASE) and path.is_file())
    if not archives:
        raise ValueError(f"No numbered RD2_*.HUG archives found in {disc}")
    found = False
    for path in archives:
        hug = int(path.stem.split("_")[-1])
        limit = path.stat().st_size
        with path.open("rb") as stream, path.open("rb") as index:
            start = 0
            while chunk := stream.read(CHUNK_BYTES):
                for match in re.finditer(b"BIGF", chunk):
                    offset = start + match.start()
                    if offset % SECTOR_SIZE == 0:
                        package = read_index(index, offset, limit, hug, path.name)
                        if package:
                            found = True
                            yield package
                start += len(chunk)
    if not found:
        raise ValueError(f"No compatible sector-aligned PS2 BIGF packages found in {disc}")


def car_packages(packages):
    for package in packages:
        names = set(package.names)
        if "lookup.ini" in names and any(name.endswith(".mdl") and name[:-4] + ".msh" in names for name in names):
            yield package


def circuits(packages):
    layouts = {}
    for package in packages:
        for name in package.names:
            if name.endswith(".aid"):
                layouts.setdefault(name[:-4], {"routes": [], "scenes": []})["routes"].append(package)
            if name.endswith("_trk.dma") and "col.col" in package.names:
                layouts.setdefault(name[:-8], {"routes": [], "scenes": []})["scenes"].append(package)
    return {name: layout for name, layout in sorted(layouts.items()) if layout["scenes"]}


def choose_route(disc, code, packages, scene):
    if not packages:
        raise ValueError(f"No race route was found for {code}")
    candidates = {}
    scene_rules = {name for name in scene.names if name.endswith(".red")}
    for package in packages:
        route = package.member(disc, f"{code}.aid")
        score = len(scene_rules.intersection(package.names))
        candidates[route] = max(candidates.get(route, 0), score)
    maximum = max(candidates.values())
    matches = [route for route, value in candidates.items() if value == maximum]
    if len(matches) != 1:
        raise ValueError(f"{code} has {len(matches)} different routes matching this scene; pairing needs verification")
    return matches[0]


def package_details(package):
    return {"hug": package.hug, "sector": package.sector, "bytes": package.size, "members": len(package.names)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("disc", type=Path, help="mounted or extracted RD2 PS2 disc directory")
    args = parser.parse_args()
    try:
        packages = tuple(scan_disc(args.disc))
        directory_hash = hashlib.sha256((args.disc / "RD2.DIR").read_bytes()).hexdigest()
        report = {
            "directory_sha256": directory_hash,
            "reference_directory": directory_hash == DONOR_DIRECTORY_HASH,
            "car_classes": [package_details(package) for package in car_packages(packages)],
            "circuits": {
                name: {key: [package_details(package) for package in packages] for key, packages in layout.items()}
                for name, layout in circuits(packages).items()
            },
        }
    except (OSError, ValueError, struct.error) as error:
        parser.exit(1, f"RD2 asset catalog failed: {error}\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
