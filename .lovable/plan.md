# Bay of Bengal Cyclone Dashboard (SIH26070)

Reuse the HurricaneMap UI shell as a static site inside this project, driven by North Indian Ocean cyclone data, with Indian coastal state and district boundaries, IMD/MOSDAC links, and a precomputed track-forecast view.

## What you'll get

A dashboard at the home page showing every recorded Bay of Bengal and Arabian Sea cyclone from 1842 to present: tracks on a map, a storm detail panel, animated playback with the spinning glyph and wind-field disk, compare mode, landfall statistics per coastal state and district, CSV/GeoJSON export, and a forecast overlay for each storm's later track points.

## Decisions already locked in

- Dataset: `tropical-cyclone-patterns` (the other repo returns 404 — private or deleted).
- The HurricaneMap app is kept as a plain static site, served at `/`, not rewritten in React.
- Everything outside map / panel / animation / compare / stats / export / theming is removed.
- ML track prediction is included.
- Boundaries: coastal states plus coastal districts.

## Data pipeline

New script `scripts/preprocess_imd.py` reads raw IBTrACS North Indian Ocean (`ibtracs.NI.list.v04r01.csv`, auto-downloaded from NOAA NCEI) and emits the exact shapes the frontend already expects:

- `storms.json` — one object per storm: `id, basin, name, year, peak_wind_kt, min_pres_mb, peak_status, landfall_max_category, landfall_max_wind_kt, us_landfall_count, us_landfalls[], track[]`. Field names stay `us_*` so no UI code changes; they carry Indian landfalls. Track points keep `{t, lat, lon, wind, pres, status, rec}` with `rec: "L"` at landfall.
- `landfalls.json` — flat event list `{storm_id, name, year, t, lat, lon, wind, pres, status, category, state, district, inferred}`. `state` gets the Indian state name (Odisha, Andhra Pradesh, Tamil Nadu, West Bengal, Gujarat, Kerala, Karnataka, Maharashtra, Goa, Puducherry), plus a new `district` field.
- `stats.json` — same keys as today: `total_storms, total_landfall_events, total_hurricane_landfalls, by_state, by_decade, by_year, by_category, cold_spot_coastal_states, year_range, generated_from`, with `by_state` roll-ups over Indian states and a parallel `by_district`.
- `metadata.json` and `coverage.json` — regenerated with `schema_version: 1` (the frontend hard-fails without this) and IBTrACS/IMD provenance.

Intensity mapping: `USA_SSHS` drives the existing Saffir-Simpson category (`-1` for tropical storm and below, as today), and IMD grade from `NEWDELHI_GRADE`/`NEWDELHI_CI` is carried alongside so the panel can show both "Category 4" and "Extremely Severe Cyclonic Storm".

Landfall detection: a track point counts as landfall on the first crossing from sea into an Indian district polygon; state and district come from a point-in-polygon test against the boundary file.

## Boundaries

Replace `data/us-states.geojson` with `data/india-coastal.geojson`: coastal state outlines plus district polygons for the coastal belt, from Natural Earth admin-1/admin-2 (public domain, no attribution constraints, unlike Survey of India). Simplified for browser use, targeting well under 1 MB.

## Prediction view

The dataset repo's trained LSTM cannot run in a browser or on this project's serverless runtime. So forecasts are computed once, offline, and shipped as static JSON:

- Run the repo's `track_lstm.pt` over each storm's history in the sandbox and write `data/predictions.json` — per storm, the forecast next positions alongside the observed ones, plus the model's reported error metrics from `track_metrics.json`.
- The panel gains a "Model forecast" toggle that draws the predicted track as a dashed line against the actual, with the error figure shown.
- The satellite image classifier is left out: it needs live image upload and a Python runtime, which a static site has no way to serve.

This keeps prediction fully working as a demo without a backend. If you later want live, interactive prediction, that needs a Python service hosted outside this project.

## Link swaps

In `src/panel-impacts.js`, replace NOAA/NHC/Wikipedia/YouTube quicklinks with:

- IMD Cyclone e-Atlas / RSMC New Delhi best-track and bulletin archive for the storm's year.
- IMD RSMC annual cyclone report PDF for the season.
- MOSDAC cyclone product page for satellite imagery.
- Wikipedia search retargeted to the North Indian Ocean cyclone season instead of the Atlantic season.

Where no per-storm IMD URL exists, the link falls back to the season archive rather than rendering a dead link.

## Removals

Deleted: `data/hurdat2-*.txt` (11 MB), `hurdat2-sources.json`, `us-states.geojson`, `scripts/refresh-hurdat2.mjs`, `scripts/preprocess_hurdat2.py`, and the US-only data files (`aoml-*`, `billions.json`, `ncei-billions*.csv`, `impacts.json`, `storm-events.json`, `rainfall.json`, `tide-stations.json`, `advisories.json`, `outlook.json`, `enso.json`, `forecast-skill.json`, `distribution.json`, `coverage`-adjacent US artifacts, `data/radar/`, `data/surge-obs/`, `data/stac/`, `storms/` prebuilt pages).

Dropped from `src/` (US-feed-specific or out of scope): radar, satellite/GOES, surge, tides, FEMA, evacuation, exposure, population, 3D globe, advisory replay, active-storm polling, NHC proxy and summary, marine warnings, seasonal outlook, ENSO, billion-dollar impacts, storm events, cone and cone-retro, high-water marks, poster/video export, art mode, QGIS, plus their tests and gate scripts. Also removed: the service worker, Cloudflare worker, and the ~70 CI gate scripts, which check US data invariants and would block every build.

Kept intact: map, panel and panel controls, animation, windfield, compare, stats, timeline, chart, export/CSV/GeoJSON/SVG, theming, settings, search, filters, URL state, saved views, i18n, keyboard, tooltips, glossary, onboarding.

## Technical notes

- HurricaneMap is much larger than its README implies: 115 JS modules, ~27,800 lines, a 52 KB `index.html`, 597 prebuilt storm pages, a service worker and ~70 CI gate scripts. `src/main.js` imports 20 modules directly, and the keep-list above resolves to roughly 45 files after transitive imports. `index.html` needs matching surgery to drop the removed panels and toolbars.
- Files land in `public/hurricanemap/` (Vite serves `public/` verbatim, so the vanilla `import` graph and `data/*.json` fetches work untouched); `src/routes/index.tsx` redirects `/` there. Relative fetch paths in `data.js` mean the app must be served from its own directory.
- `assertSupportedDataSchema` in `src/schema-contract.js` throws unless `metadata.json` has `schema_version: 1` — the generator sets it.
- `storms.json.gz` is fetched first when `DecompressionStream` exists, so the generator writes both the gzip and the plain JSON.
- Preprocessing and offline inference run in the sandbox; `torch` isn't installed there yet, so a CPU build gets installed to load `track_lstm.pt`. If those weights fail to load standalone, the fallback is a NumPy reimplementation of the same recurrence from the checkpoint tensors.
- 1,716 storms and 30,633 six-hourly points is roughly 3x HurricaneMap's current storm count, so track rendering gets a year-range filter default rather than drawing everything at once.

## Order of work

1. Copy HurricaneMap into `public/hurricanemap/`, delete the removals above, get it booting on the existing US data to confirm the shell survives the strip.
2. Build the boundary GeoJSON.
3. Write `preprocess_imd.py`, generate the four JSON files, verify against the documented schema.
4. Swap the data in, fix whatever the strip and swap broke, wire the district stats.
5. Precompute predictions, add the forecast toggle.
6. Swap the quicklinks, verify the page end to end in a browser.
