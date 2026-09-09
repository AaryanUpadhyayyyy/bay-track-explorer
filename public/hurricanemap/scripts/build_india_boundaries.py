"""Build Indian coastal state and district boundaries for the cyclone atlas.

Source: geoBoundaries gbOpen IND ADM1/ADM2 (Open Database License 1.0),
simplified releases. Districts are assigned to a state by spatial join.

Outputs (both consumed by the frontend and by preprocess_imd.py):
  data/india-states.geojson     properties: {name, level:"state"}
  data/india-districts.geojson  properties: {name, state, level:"district"}

Usage:  python3 scripts/build_india_boundaries.py
"""

from __future__ import annotations

import json
import os
import unicodedata
import urllib.request
from pathlib import Path

from shapely.geometry import mapping, shape
from shapely.ops import unary_union
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CACHE = Path(os.environ.get("CYCLONE_CACHE_DIR", "/tmp/sih/cache"))

REV = "9469f09"
BASE = f"https://github.com/wmgeolab/geoBoundaries/raw/{REV}/releaseData/gbOpen/IND"
SOURCES = {
    "adm1": f"{BASE}/ADM1/geoBoundaries-IND-ADM1_simplified.geojson",
    "adm2": f"{BASE}/ADM2/geoBoundaries-IND-ADM2_simplified.geojson",
}

# Every state / union territory with a coastline on the North Indian Ocean.
# Names are the ASCII-folded geoBoundaries shapeName values.
COASTAL_STATES = {
    "Gujarat",
    "Maharashtra",
    "Goa",
    "Karnataka",
    "Kerala",
    "Tamil Nadu",
    "Puducherry",
    "Andhra Pradesh",
    "Odisha",
    "West Bengal",
    "Dadra and Nagar Haveli and Daman and Diu",
    "Lakshadweep",
    "Andaman and Nicobar Islands",
}

# Simplification tolerance in degrees. ~1 km at this latitude; landfall
# attribution stays district-accurate while the payload stays browser-friendly.
STATE_TOLERANCE = 0.01
DISTRICT_TOLERANCE = 0.008
COORD_PRECISION = 4


def fold(name: str) -> str:
    """Strip the macrons geoBoundaries carries (Gujarāt -> Gujarat)."""
    decomposed = unicodedata.normalize("NFKD", name or "")
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).strip()


def fetch(key: str) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"geoboundaries-{key}.geojson"
    if not path.exists():
        print(f"Downloading {key.upper()} from {SOURCES[key]}")
        urllib.request.urlretrieve(SOURCES[key], path)
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def round_coords(obj):
    if isinstance(obj, (int, float)):
        return round(float(obj), COORD_PRECISION)
    if isinstance(obj, (list, tuple)):
        return [round_coords(item) for item in obj]
    return obj


def feature(geom, properties: dict, tolerance: float) -> dict:
    simplified = geom.simplify(tolerance, preserve_topology=True)
    if simplified.is_empty:
        simplified = geom
    geometry = mapping(simplified)
    geometry["coordinates"] = round_coords(geometry["coordinates"])
    return {"type": "Feature", "properties": properties, "geometry": geometry}


def main() -> None:
    adm1 = fetch("adm1")
    adm2 = fetch("adm2")

    states: dict[str, object] = {}
    for entry in adm1["features"]:
        name = fold(entry["properties"].get("shapeName", ""))
        if name not in COASTAL_STATES:
            continue
        geom = shape(entry["geometry"])
        states[name] = unary_union([states[name], geom]) if name in states else geom

    missing = COASTAL_STATES - set(states)
    if missing:
        raise SystemExit(f"coastal states absent from ADM1: {sorted(missing)}")

    state_names = list(states)
    tree = STRtree([states[name] for name in state_names])

    districts: list[dict] = []
    unassigned = 0
    for entry in adm2["features"]:
        geom = shape(entry["geometry"])
        if geom.is_empty:
            continue
        probe = geom.representative_point()
        owner = None
        for idx in tree.query(probe):
            if states[state_names[idx]].contains(probe):
                owner = state_names[idx]
                break
        if owner is None:
            # Boundary mismatch between the two releases: fall back to the
            # state sharing the largest overlap, and only within coastal states.
            best_area = 0.0
            for idx in tree.query(geom):
                candidate = state_names[idx]
                try:
                    area = geom.intersection(states[candidate]).area
                except Exception:  # pragma: no cover - invalid source geometry
                    continue
                if area > best_area:
                    best_area, owner = area, candidate
            if owner is None or best_area < geom.area * 0.2:
                unassigned += 1
                continue
        districts.append(
            feature(
                geom,
                {
                    "name": fold(entry["properties"].get("shapeName", "")),
                    "state": owner,
                    "level": "district",
                },
                DISTRICT_TOLERANCE,
            )
        )

    state_features = [
        feature(states[name], {"name": name, "level": "state"}, STATE_TOLERANCE)
        for name in sorted(states)
    ]

    attribution = (
        "geoBoundaries gbOpen IND ADM1/ADM2 "
        f"(rev {REV}), Open Database License 1.0"
    )
    DATA.mkdir(parents=True, exist_ok=True)
    for filename, features in (
        ("india-states.geojson", state_features),
        ("india-districts.geojson", sorted(districts, key=lambda f: (f["properties"]["state"], f["properties"]["name"]))),
    ):
        payload = {
            "type": "FeatureCollection",
            "attribution": attribution,
            "features": features,
        }
        target = DATA / filename
        with target.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, separators=(",", ":"))
        size_kb = target.stat().st_size / 1024
        print(f"wrote {target.relative_to(ROOT)}  {len(features)} features  {size_kb:.0f} KB")

    print(f"districts skipped (outside coastal states): {unassigned}")


if __name__ == "__main__":
    main()
