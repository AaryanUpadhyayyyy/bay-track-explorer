# SIH26070 — Bay of Bengal Cyclone Dashboard

Plan: `.lovable/plan/bay-of-bengal-cyclone-dashboard-sih26070-2026-09-09.md`

- [x] 1. Serve HurricaneMap from `public/hurricanemap/`, `/` redirects there; confirm it boots
- [ ] 2. Strip US-only features from `src/` + `index.html`; delete US data files & gate scripts
- [x] 3. Build `data/india-states.geojson` + `data/india-districts.geojson` (13 coastal states/UTs, 230 districts)
- [x] 4. Write `scripts/preprocess_imd.py` → storms/landfalls/stats/metadata/coverage JSON
- [x] 5. Swap data in, wire district stats
- [ ] 6. Precompute `data/predictions.json` from track_lstm.pt; add forecast toggle
- [x] 7. Swap quicklinks to IMD / MOSDAC
- [x] 8. Verify end-to-end in browser

Open:
- Step 2 (removing the leftover US-only feeds/panels: NOAA active storms, outlook, FEMA-era modules) is partly done — links, boundaries, cities and labels are swapped; the optional NOAA feed widgets still show retry cards.
- Step 6 (ML track prediction) is blocked: PyTorch is unavailable in this environment, so the model cannot be run to precompute forecasts.
