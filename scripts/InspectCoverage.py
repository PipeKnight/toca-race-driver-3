"""Read the acceptance coverage inventory from the supported TOCA PS2 disc."""

import argparse
import configparser
import hashlib
import json
import re
import struct
from pathlib import Path


DISC_HASH = "08c1f20904bb99067588f0aff8637f0e97cbd46d2570f4a0247245e32e5ddf29"
TRACK_INFO = 0x68390800
CAREER_GATES = 0x68432800
CHAMPIONSHIPS = 0x68438000
CHECKSUM_CATALOG = 0x669D0000
CAMPAIGN_ALIASES = {"first": "1st__"}


def read_range(disc, offset, size):
    disc.seek(offset)
    data = disc.read(size)
    if len(data) != size:
        raise ValueError(f"Incomplete disc range at {offset:#x}")
    return data


def parse_ini(data):
    ini = configparser.ConfigParser(interpolation=None, strict=False)
    ini.read_string(data.decode("cp1252").rstrip("\0"))
    return ini


def ini_members(disc, package_offset):
    header = read_range(disc, package_offset, 0x24)
    magic, count, data_start = struct.unpack_from("<4sII", header)
    if magic != b"BIGF" or not 0 < count <= 204 or data_start < 0x24 + 24 * count:
        raise ValueError(f"Unexpected BIGF directory at {package_offset:#x}")

    directory = read_range(disc, package_offset + 0x24, 24 * count)
    members = {}
    for name, size, offset in struct.iter_unpack("<16sII", directory):
        filename = name.split(b"\0", 1)[0].decode("ascii")
        if filename in members:
            raise ValueError(f"Duplicate member {filename}")
        if filename.lower().endswith(".ini"):
            members[filename] = parse_ini(read_range(disc, package_offset + data_start + offset, size))
    return members


def fields(section, *keys):
    return {key: section[key] for key in keys if key in section}


def numbered_fields(section, prefix):
    values = []
    for key, value in section.items():
        suffix = key.removeprefix(prefix)
        if key.startswith(prefix) and suffix.isdecimal():
            values.append((int(suffix), value))
    return [value for _, value in sorted(values)]


def event_summary(filename, ini):
    event = fields(ini["General"], "Name", "Discipline", "RaceType", "ObjectiveType",
                   "ObjectiveFinishInNthPlaceOrAbove", "CareerOfferCarID")
    event["id"] = Path(filename).stem
    event["rounds"] = []
    for name in ini.sections():
        if not re.fullmatch(r"Race \d+", name):
            continue
        race = ini[name]
        round_summary = fields(race, "TrackID", "Genre", "RaceStartType", "MandatoryPitStop",
                               "CareerLapsNum", "FullRaceLapsNum", "RaceSessions",
                               "RaceSessionsFullEvents")
        round_summary["weather"] = numbered_fields(race, "weather")
        event["rounds"].append(round_summary)
    event["car_types"] = sorted({ini[name]["CarUID"].rsplit("/", 1)[-1].upper()
                                 for name in ini.sections() if "CarUID" in ini[name]})
    return event


def campaign_summary(ini):
    result = []
    for name in ini.sections():
        if not re.fullmatch(r"Gate\d+", name):
            continue
        gate = ini[name]
        levels = [numbered_fields(gate, f"level{i}champid")
                  for i in range(gate.getint("LevelsNum"))]
        if any(not level for level in levels):
            raise ValueError(f"Empty level in {name}")
        result.append({"gate": name, "next": gate.getint("GateNext"), "levels": levels})
    return result


def inspect(disc):
    track_files = ini_members(disc, TRACK_INFO)
    gate_files = ini_members(disc, CAREER_GATES)
    event_files = ini_members(disc, CHAMPIONSHIPS)
    catalog = parse_ini(read_range(disc, CHECKSUM_CATALOG, 90403))

    tracks = {ini["Info"]["TrackID"]: fields(ini["Info"], "FullName", "ShortName", "LengthInKm", "Stage")
              for ini in track_files.values()}
    campaigns = {Path(name).stem: campaign_summary(ini) for name, ini in gate_files.items()}
    events = [event_summary(name, ini) for name, ini in event_files.items()]
    event_ids = {event["id"] for event in events}
    referenced_events = {CAMPAIGN_ALIASES.get(event_id, event_id)
                         for gates in campaigns.values() for gate in gates
                         for level in gate["levels"] for event_id in level}
    referenced_tracks = {race["TrackID"] for event in events for race in event["rounds"]}
    if referenced_events - event_ids or referenced_tracks - tracks.keys():
        raise ValueError("Campaign or round references are missing from the inventory")
    catalog_tracks = {catalog[n]["TrackID"]
                      for n in catalog.sections() if n.startswith("Track ")}
    unused_tracks = sorted(set(tracks) - catalog_tracks)
    return {
        "disc": {"serial": "SLUS-21182", "revision": "1.02", "sha256": DISC_HASH},
        "tracks": tracks,
        "campaigns": campaigns,
        "campaign_aliases": CAMPAIGN_ALIASES,
        "events": events,
        "checksum_catalog": {
            "counts": {key: int(catalog["General"][key])
                       for key in ("NumChamps", "NumTracks", "NumCars", "NumUniqueCarTypes")},
            "car_types": numbered_fields(catalog["Unique CarTypes"], "cartype"),
            "tracks_absent_from_catalog": unused_tracks,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("iso", type=Path, help="Original SLUS-21182 v1.02 ISO")
    args = parser.parse_args()
    try:
        with args.iso.open("rb") as disc:
            if hashlib.file_digest(disc, "sha256").hexdigest() != DISC_HASH:
                raise ValueError("Disc SHA-256 does not match SLUS-21182 v1.02")
            inventory = inspect(disc)
    except (OSError, ValueError, KeyError, configparser.Error) as error:
        parser.exit(1, f"Coverage inventory: {error}\n")
    print(json.dumps(inventory, indent=2))


if __name__ == "__main__":
    main()
