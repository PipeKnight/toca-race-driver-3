#!/usr/bin/env python3
"""Discover indexed car and circuit packages on a supported RD2 PS2 disc."""

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import struct

from BuildTrackCollisionOverlay import BIGF_ENTRY, DONOR_DIRECTORY_HASH, SECTOR_SIZE, verify_directory


CHUNK_BYTES = 8 * 1024 * 1024
HEADER_BYTES = 0x24
HEADER = struct.Struct("<4sII")


@dataclass(frozen=True)
class AssetPackage:
    hug: int
    sector: int
    size: int
    entries: tuple[tuple[str, int, int], ...]

    @property
    def names(self):
        return tuple(name for name, _, _ in self.entries)

    def path(self, disc):
        return disc / f"RD2_{self.hug}.HUG"

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


def read_index(stream, offset, limit, hug):
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
                        tuple((name, *entries[name]) for name in sorted(entries)))


def scan_disc(disc):
    verify_directory(disc / "RD2.DIR", DONOR_DIRECTORY_HASH)
    for hug in range(3):
        path = disc / f"RD2_{hug}.HUG"
        limit = path.stat().st_size
        with path.open("rb") as stream, path.open("rb") as index:
            start = 0
            while chunk := stream.read(CHUNK_BYTES):
                for match in re.finditer(b"BIGF", chunk):
                    offset = start + match.start()
                    if offset % SECTOR_SIZE == 0:
                        package = read_index(index, offset, limit, hug)
                        if package:
                            yield package
                start += len(chunk)


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


def package_details(package):
    return {"hug": package.hug, "sector": package.sector, "bytes": package.size, "members": len(package.names)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("disc", type=Path, help="mounted or extracted RD2 PS2 disc directory")
    args = parser.parse_args()
    try:
        packages = tuple(scan_disc(args.disc))
        report = {
            "directory_sha256": hashlib.sha256((args.disc / "RD2.DIR").read_bytes()).hexdigest(),
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
