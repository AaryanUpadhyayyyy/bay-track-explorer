"""Build the cyclone atlas data files for the North Indian Ocean.

Reads the IBTrACS North Indian Ocean best-track archive (which carries the IMD /
RSMC New Delhi columns NEWDELHI_WIND, NEWDELHI_PRES, NEWDELHI_GRADE,
NEWDELHI_CI alongside the JTWC USA_* columns) and writes the exact JSON shapes
the frontend already consumes:

  data/storms.json      one record per storm, with full track
  data/storms.json.gz   gzip of the above (fetched first when the browser
                        supports DecompressionStream)
  data/landfalls.json   one record per landfall event
  data/stats.json       pre-computed roll-ups by state, district, decade,
                        year and category
  data/metadata.json    provenance, schema_version 1 (the app hard-fails
                        without this)
  data/coverage.json    archive coverage and lifecycle facts

Landfall attribution is a point-in-polygon test against
data/india-districts.geojson, so run scripts/build_india_boundaries.py first.

Usage:  python3 scripts/preprocess_imd.py
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from shapely.geometry import Point, shape
from shapely.prepared import prep
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CACHE = Path(os.environ.get("CYCLONE_CACHE_DIR", "/tmp/sih/cache"))

IBTRACS_FILE = "ibtracs.NI.list.v04r01.csv"
IBTRACS_URL = (
    "https://www.ncei.noaa.gov/data/"
    "international-best-track-archive-for-climate-stewardship-ibtracs/"
    "v04r01/access/csv/" + IBTRACS_FILE
)

# Saffir-Simpson thresholds in knots, used only when USA_SSHS is absent.
SSHS_THRESHOLDS = ((137, 5), (113, 4), (96, 3), (83, 2), (64, 1))

# IMD grade code -> the full RSMC New Delhi classification name.
IMD_GRADES = {
    "D": "Depression",
    "DD": "Deep Depression",
    "CS": "Cyclonic Storm",
    "SCS": "Severe Cyclonic Storm",
    "SCS(H)": "Severe Cyclonic Storm",
    "VSCS": "Very Severe Cyclonic Storm",
    "ESCS": "Extremely Severe Cyclonic Storm",
    "SUCS": "Super Cyclonic Storm",
    "SUCS ": "Super Cyclonic Storm",
    "L": "Land Depression",
}

# Wind (kt) -> IMD grade, for points with no NEWDELHI_GRADE of their own.
IMD_WIND_GRADES = ((120, "SuCS"), (90, "ESCS"), (64, "VSCS"), (48, "SCS"), (34, "CS"), (28, "DD"), (0, "D"))


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def fetch_ibtracs() -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / IBTRACS_FILE
    if not path.exists():
        print(f"Downloading IBTrACS North Indian Ocean from {IBTRACS_URL}")
        urllib.request.urlretrieve(IBTRACS_URL, path)
    return path


def load_tracks(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, skiprows=[1], low_memory=False)
    frame["ISO_TIME"] = pd.to_datetime(frame["ISO_TIME"], utc=True, errors="coerce")
    frame["LAT"] = numeric(frame["LAT"])
    frame["LON"] = numeric(frame["LON"])
    frame["SEASON"] = numeric(frame["SEASON"])

    # Prefer IMD's own wind and pressure; fall back to WMO then JTWC so early
    # seasons (which predate the IMD columns) still carry an intensity.
    frame["WIND"] = pd.NA
    for column in ("NEWDELHI_WIND", "WMO_WIND", "USA_WIND"):
        if column in frame.columns:
            frame["WIND"] = frame["WIND"].fillna(numeric(frame[column]))
    frame["PRES"] = pd.NA
    for column in ("NEWDELHI_PRES", "WMO_PRES", "USA_PRES"):
        if column in frame.columns:
            frame["PRES"] = frame["PRES"].fillna(numeric(frame[column]))
    frame["WIND"] = numeric(frame["WIND"])
    frame["PRES"] = numeric(frame["PRES"])
    frame["SSHS"] = numeric(frame.get("USA_SSHS"))
    frame["GRADE"] = frame.get("NEWDELHI_GRADE", "").astype(str).str.strip()
    frame["CI"] = numeric(frame.get("NEWDELHI_CI"))

    frame = frame.dropna(subset=["SID", "ISO_TIME", "LAT", "LON", "SEASON"])
    # Keep the basin box; IBTrACS NI includes a few strays from neighbours.
    frame = frame[frame["LAT"].between(-5, 35) & frame["LON"].between(40, 110)]
    return frame.sort_values(["SID", "ISO_TIME"])


def category_from(sshs: float | None, wind: float | None) -> int:
    """Saffir-Simpson category, -1 for tropical-storm strength and below.

    The frontend's colour ramps, filters and legends are all written against
    this encoding, so it is preserved exactly.
    """
    if sshs is not None and not math.isnan(sshs):
        value = int(sshs)
        return value if value >= 1 else -1
    if wind is None or math.isnan(wind):
        return -1
    for threshold, category in SSHS_THRESHOLDS:
        if wind >= threshold:
            return category
    return -1


def status_from(category: int, wind: float | None) -> str:
    if category >= 1:
        return "HU"
    if wind is not None and not math.isnan(wind) and wind >= 34:
        return "TS"
    return "TD"


def grade_from(raw: str, wind: float | None) -> tuple[str, str]:
    code = (raw or "").strip()
    if code and code.upper() != "NAN":
        return code, IMD_GRADES.get(code.upper(), IMD_GRADES.get(code, code))
    if wind is None or math.isnan(wind):
        return "", ""
    for threshold, fallback in IMD_WIND_GRADES:
        if wind >= threshold:
            return fallback, IMD_GRADES[fallback.upper()]
    return "", ""


def basin_of(lon: float) -> str:
    """BB (Bay of Bengal) east of 78E, AS (Arabian Sea) west of it."""
    return "BB" if lon >= 78 else "AS"


def load_districts() -> tuple[STRtree, list[dict], list[object]]:
    path = DATA / "india-districts.geojson"
    if not path.exists():
        raise SystemExit(
            f"{path.relative_to(ROOT)} is missing — run scripts/build_india_boundaries.py first"
        )
    with path.open(encoding="utf-8") as handle:
        collection = json.load(handle)
    geometries = []
    properties = []
    for entry in collection["features"]:
        geometries.append(shape(entry["geometry"]))
        properties.append(entry["properties"])
    return STRtree(geometries), properties, [prep(geom) for geom in geometries]


def locate(tree: STRtree, props: list[dict], prepared: list[object], lat: float, lon: float):
    point = Point(lon, lat)
    for idx in tree.query(point):
        if prepared[idx].contains(point):
            return props[idx]
    return None


def numeric_or_none(value) -> float | int | None:
    if value is None or (isinstance(value, float) and math.isnan(value)) or pd.isna(value):
        return None
    number = float(value)
    return int(number) if number.is_integer() else round(number, 1)


def build() -> None:
    source = fetch_ibtracs()
    frame = load_tracks(source)
    tree, props, prepared = load_districts()

    storms: list[dict] = []
    landfalls: list[dict] = []

    for sid, group in frame.groupby("SID", sort=True):
        name = str(group["NAME"].iloc[0] or "UNNAMED").strip().upper() or "UNNAMED"
        if name in {"NOT_NAMED", "NOT NAMED", "NAN", ""}:
            name = "UNNAMED"
        year = int(group["SEASON"].iloc[0])

        track: list[dict] = []
        storm_landfalls: list[dict] = []
        was_inland = False
        for _, row in group.iterrows():
            wind = numeric_or_none(row["WIND"])
            pres = numeric_or_none(row["PRES"])
            category = category_from(row["SSHS"], row["WIND"])
            status = status_from(category, row["WIND"])
            grade, grade_name = grade_from(row["GRADE"], row["WIND"])
            lat = round(float(row["LAT"]), 2)
            lon = round(float(row["LON"]), 2)
            timestamp = row["ISO_TIME"].strftime("%Y-%m-%dT%H:%M:%SZ")

            district = locate(tree, props, prepared, lat, lon)
            is_landfall = district is not None and not was_inland
            was_inland = district is not None

            point = {
                "t": timestamp,
                "lat": lat,
                "lon": lon,
                "wind": wind,
                "pres": pres,
                "status": status,
                "rec": "L" if is_landfall else None,
                "imd_grade": grade or None,
                "imd_grade_name": grade_name or None,
                "imd_ci": numeric_or_none(row["CI"]),
            }
            track.append(point)

            if is_landfall:
                event = {
                    "t": timestamp,
                    "lat": lat,
                    "lon": lon,
                    "wind": wind,
                    "pres": pres,
                    "status": status,
                    "category": category,
                    "state": district["state"],
                    "district": district["name"],
                    "imd_grade": grade or None,
                    "imd_grade_name": grade_name or None,
                    "inferred": False,
                }
                storm_landfalls.append(event)
                landfalls.append({"storm_id": sid, "name": name, "year": year, **event})

        if not track:
            continue

        winds = [p["wind"] for p in track if p["wind"] is not None]
        pressures = [p["pres"] for p in track if p["pres"] is not None]
        peak_wind = max(winds) if winds else None
        peak_category = max(
            (category_from(None, p["wind"]) for p in track if p["wind"] is not None),
            default=-1,
        )
        sshs_values = [v for v in group["SSHS"].tolist() if v is not None and not math.isnan(v)]
        if sshs_values:
            peak_category = max(peak_category, category_from(max(sshs_values), None))
        peak_grade, peak_grade_name = grade_from("", peak_wind)
        grades_present = [g for g in group["GRADE"].tolist() if g and g.upper() != "NAN"]
        if grades_present:
            ranked = {code: rank for rank, (_, code) in enumerate(reversed(IMD_WIND_GRADES))}
            best = max(grades_present, key=lambda g: ranked.get(g.replace("(H)", ""), -1))
            peak_grade, peak_grade_name = grade_from(best, peak_wind)

        storms.append(
            {
                "id": sid,
                "basin": basin_of(float(group["LON"].iloc[0])),
                "name": name,
                "year": year,
                "peak_wind_kt": peak_wind,
                "min_pres_mb": min(pressures) if pressures else None,
                "peak_status": status_from(peak_category, peak_wind),
                "peak_category": peak_category,
                "imd_peak_grade": peak_grade or None,
                "imd_peak_grade_name": peak_grade_name or None,
                # The frontend reads these field names; here they carry Indian
                # landfalls rather than U.S. ones.
                "landfall_max_category": max((e["category"] for e in storm_landfalls), default=None),
                "landfall_max_wind_kt": max(
                    (e["wind"] for e in storm_landfalls if e["wind"] is not None), default=None
                ),
                "us_landfall_count": len(storm_landfalls),
                "us_landfalls": storm_landfalls,
                "track": track,
            }
        )

    stats = build_stats(storms, landfalls)
    write_outputs(storms, landfalls, stats, source)


def empty_bucket() -> dict:
    return {"total": 0, "by_cat": [0] * 7}


def add_to(bucket: dict, category: int) -> None:
    bucket["total"] += 1
    index = 0 if category < 1 else min(category, 5)
    bucket["by_cat"][index] += 1


def build_stats(storms: list[dict], landfalls: list[dict]) -> dict:
    by_state: dict[str, dict] = {}
    by_district: dict[str, dict] = {}
    by_decade: dict[str, dict] = {}
    by_year: dict[str, dict] = {}
    by_category = {"ts_or_below": 0, "cat1": 0, "cat2": 0, "cat3": 0, "cat4": 0, "cat5": 0}
    by_basin = {"BB": 0, "AS": 0}

    for event in landfalls:
        category = event["category"]
        add_to(by_state.setdefault(event["state"], empty_bucket()), category)
        add_to(
            by_district.setdefault(f"{event['district']}, {event['state']}", empty_bucket()),
            category,
        )
        add_to(by_decade.setdefault(str(event["year"] // 10 * 10), empty_bucket()), category)
        add_to(by_year.setdefault(str(event["year"]), empty_bucket()), category)
        key = "ts_or_below" if category < 1 else f"cat{min(category, 5)}"
        by_category[key] += 1

    for storm in storms:
        by_basin[storm["basin"]] = by_basin.get(storm["basin"], 0) + 1

    with (DATA / "india-states.geojson").open(encoding="utf-8") as handle:
        coastal = [f["properties"]["name"] for f in json.load(handle)["features"]]

    years = [storm["year"] for storm in storms]
    return {
        "total_storms": len(storms),
        "total_landfall_events": len(landfalls),
        "total_hurricane_landfalls": sum(1 for e in landfalls if e["category"] >= 1),
        "by_state": dict(sorted(by_state.items())),
        "by_district": dict(sorted(by_district.items())),
        "by_decade": dict(sorted(by_decade.items(), key=lambda kv: int(kv[0]))),
        "by_year": dict(sorted(by_year.items(), key=lambda kv: int(kv[0]))),
        "by_category": by_category,
        "by_basin": by_basin,
        "cold_spot_coastal_states": sorted(name for name in coastal if name not in by_state),
        "year_range": [min(years), max(years)],
        "generated_from": "IBTrACS v04r01 North Indian Ocean (IMD / RSMC New Delhi best track)",
    }


def write_outputs(storms: list[dict], landfalls: list[dict], stats: dict, source: Path) -> None:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    year_range = stats["year_range"]
    end_date = f"{year_range[1]}-12-31"

    dataset_paths = [
        "data/landfalls.json",
        "data/stats.json",
        "data/storms.json",
        "data/storms.json.gz",
    ]
    dataset = {
        "id": "ibtracs-ni",
        "label": "IBTrACS v04r01 North Indian Ocean best track (IMD / RSMC New Delhi)",
        "paths": dataset_paths,
        "status": "active",
        "end_date": end_date,
        "retirement_citation": None,
    }
    boundaries = {
        "id": "india-boundaries",
        "label": "Indian coastal state and district boundaries (geoBoundaries gbOpen, ODbL 1.0)",
        "paths": ["data/india-states.geojson", "data/india-districts.geojson"],
        "status": "active",
        "end_date": None,
        "retirement_citation": None,
    }

    metadata = {
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "generator": {
            "name": "scripts/preprocess_imd.py",
            "app_version": "1.0.0-imd",
            "source_commit": None,
            "source_manifest": None,
            "runtime": f"Python {os.sys.version.split()[0]}",
        },
        "sources": [
            {
                "id": "ibtracs_north_indian",
                "basin": "NI",
                "filename": source.name,
                "path": f"cache/{source.name}",
                "size_bytes": source.stat().st_size,
                "modified_utc": datetime.fromtimestamp(
                    source.stat().st_mtime, timezone.utc
                ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "source_date": generated_at[:10],
                "source_file": source.name,
                "source_url": IBTRACS_URL,
                "sha256": digest,
                "storm_count": len(storms),
                "storm_year_range": year_range,
            }
        ],
        "datasets": [dataset, boundaries],
        "coverage": {
            "basins": ["BB", "AS"],
            "year_range": year_range,
            "storm_count": len(storms),
            "landfall_event_count": len(landfalls),
            "hurricane_landfall_count": stats["total_hurricane_landfalls"],
        },
        "outputs": dataset_paths,
        "methodology": [
            "Best-track positions come from IBTrACS v04r01 for the North Indian Ocean, "
            "which republishes the IMD / RSMC New Delhi best track alongside other agencies.",
            "Wind and pressure prefer the IMD columns (NEWDELHI_WIND, NEWDELHI_PRES) and fall "
            "back to WMO then JTWC values for seasons that predate them.",
            "Saffir-Simpson category comes from USA_SSHS, with the IMD grade "
            "(Depression through Super Cyclonic Storm) carried alongside on every point.",
            "A landfall is the first track position inside an Indian coastal district polygon "
            "after the storm was last over water; state and district come from that polygon.",
        ],
    }

    coverage = {
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "source_commit": None,
        "catalog": {
            "basins": ["BB", "AS"],
            "year_range": year_range,
            "storm_count": len(storms),
            "landfall_event_count": len(landfalls),
            "hurricane_landfall_count": stats["total_hurricane_landfalls"],
        },
        "datasets": [
            {
                **dataset,
                "sources": [
                    {
                        "name": f"{source.name} (NI)",
                        "url": IBTRACS_URL,
                        "revision_date": generated_at[:10],
                        "basin": "NI",
                    }
                ],
                "basins": ["BB", "AS"],
                "year_range": year_range,
                "lifecycle_status": "active",
                "value_status": "final",
                "availability": {
                    "runnable": True,
                    "records": len(landfalls),
                    "storms": len(storms),
                    "frames": None,
                    "advisories": None,
                    "marks": None,
                    "detail": (
                        f"{len(storms)} best-track storms; {len(landfalls)} landfall events "
                        "attributed to Indian coastal districts."
                    ),
                },
                "distribution": ["core", "full"],
                "notes": [
                    "Landfall events are derived by point-in-polygon against Indian district "
                    "boundaries, not published landfall records."
                ],
            },
            {
                **boundaries,
                "sources": [
                    {
                        "name": "geoBoundaries gbOpen IND ADM1/ADM2",
                        "url": "https://www.geoboundaries.org/",
                        "revision_date": "2023-01-19",
                        "basin": None,
                    }
                ],
                "basins": [],
                "year_range": None,
                "lifecycle_status": "active",
                "value_status": "final",
                "availability": {
                    "runnable": True,
                    "records": len(stats["by_district"]),
                    "storms": None,
                    "frames": None,
                    "advisories": None,
                    "marks": None,
                    "detail": "13 coastal states and union territories; 230 coastal districts.",
                },
                "distribution": ["core", "full"],
                "notes": [],
            },
        ],
    }

    DATA.mkdir(parents=True, exist_ok=True)
    payloads = {
        "storms.json": storms,
        "landfalls.json": landfalls,
        "stats.json": stats,
        "metadata.json": metadata,
        "coverage.json": coverage,
    }
    for filename, payload in payloads.items():
        target = DATA / filename
        text = json.dumps(payload, separators=(",", ":"))
        target.write_text(text, encoding="utf-8")
        print(f"wrote {target.relative_to(ROOT)}  {target.stat().st_size / 1024:.0f} KB")

    gz = DATA / "storms.json.gz"
    with gzip.open(gz, "wb", compresslevel=9) as handle:
        handle.write(json.dumps(storms, separators=(",", ":")).encode("utf-8"))
    print(f"wrote {gz.relative_to(ROOT)}  {gz.stat().st_size / 1024:.0f} KB")

    print(
        f"\n{len(storms)} storms  {len(landfalls)} landfall events  "
        f"{stats['total_hurricane_landfalls']} at hurricane strength  "
        f"years {year_range[0]}-{year_range[1]}"
    )
    top = sorted(stats["by_state"].items(), key=lambda kv: -kv[1]["total"])[:6]
    print("top states: " + ", ".join(f"{name} {v['total']}" for name, v in top))


if __name__ == "__main__":
    build()
