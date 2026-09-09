# SIH26070 — Bay of Bengal Cyclone Dashboard

Plan: `.lovable/plan/bay-of-bengal-cyclone-dashboard-sih26070-2026-09-09.md`

- [ ] 1. Serve HurricaneMap from `public/hurricanemap/`, `/` redirects there; confirm it boots
- [ ] 2. Strip US-only features from `src/` + `index.html`; delete US data files & gate scripts
- [ ] 3. Build `data/india-coastal.geojson` (coastal states + coastal districts)
- [ ] 4. Write `scripts/preprocess_imd.py` → storms/landfalls/stats/metadata/coverage JSON
- [ ] 5. Swap data in, wire district stats
- [ ] 6. Precompute `data/predictions.json` from track_lstm.pt; add forecast toggle
- [ ] 7. Swap quicklinks to IMD / MOSDAC
- [ ] 8. Verify end-to-end in browser
