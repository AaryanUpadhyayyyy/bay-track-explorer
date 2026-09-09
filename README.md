# Bay Cyclone Tracker

I'm building a cyclone tracking dashboard for SIH26070 (Bay of Bengal / North Indian Ocean 

tropical cyclones). I want to combine two repos:

1. Frontend/UI shell: https://github.com/SysAdminDoc/HurricaneMap

   - Vanilla JS + Leaflet, no framework. Key files: src/main.js, src/map.js, src/panel.js,

     src/animation.js, src/stats.js, src/styles.css

   - It's built for US hurricanes off NOAA HURDAT2. I only want its UI/UX architecture —

     the map rendering, storm detail panel, track animation (spinning glyph + wind-field

     disk), compare mode, state/region hotspot stats, and CSV/GeoJSON export.

2. Data source: https://github.com/d1panshuparmar/tropical-cyclone-patterns

   (or https://github.com/SanyamBothra-cmd/bob-cyclone-dataset if the ML prediction piece

   isn't needed — check both and tell me which fits better)

   - This provides Bay of Bengal / Arabian Sea cyclone track and intensity data

     (IMD best-track format: NEWDELHI_CI, NEWDELHI_GRADE, USA_SSHS fields).

TASK:

1. Clone HurricaneMap and strip out everything HURDAT2/NOAA-specific: data/hurdat2-*.txt,

   scripts/refresh-hurdat2.mjs, scripts/preprocess_hurdat2.py, us-states.geojson, and any

   NOAA/NHC-specific quicklinks in panel.js.

2. Inspect src/data.js and the shape of data/storms.json, data/landfalls.json, and

   data/stats.json — document the exact schema (fields, types, nesting) the frontend expects.

3. Write a new preprocessing script (Python) that reads the Bay of Bengal dataset from

   [tropical-cyclone-patterns or bob-cyclone-dataset] and outputs storms.json/landfalls.json/

   stats.json in that same schema, so the existing frontend code in map.js/panel.js/

   animation.js/stats.js works with minimal changes.

4. Replace the US state boundary GeoJSON with Indian coastal state/district boundaries

   (Odisha, Andhra Pradesh, Tamil Nadu, West Bengal, etc. — use Survey of India or Natural

   Earth admin boundaries).

5. Swap panel.js quicklinks (Wikipedia/YouTube/NOAA) for IMD bulletin links and MOSDAC

   satellite links where equivalent URLs exist.

6. Keep the theming, compare-mode, panel-minimize-to-tab, and export functionality intact —

   these are basin-agnostic.

7. Get it running locally and show me the diff/plan before making destructive changes to

   the data folder.

Start by cloning both repos, inspecting their actual file structures and data schemas

(don't assume from README alone), and report back what you find before writing code.

This project was built with [Lovable](https://lovable.dev).

**Live app**: https://bay-track-explorer.lovable.app

## Build with Lovable

Continue developing this project in the [Lovable editor](https://lovable.dev/projects/9ec29263-42af-4bf5-b177-060bf891eb6d).

- **Ship faster**: describe what you want to build and Lovable handles the code.
- **Stay in sync**: every change made in Lovable is committed straight to this repository.
- **Full ownership**: this code is yours. Push to `main` on GitHub and your changes sync back into Lovable, ready for your next prompt.

## Development

Prefer working locally? You need Node.js and npm — [install with nvm](https://github.com/nvm-sh/nvm#installing-and-updating).

```sh
git clone <this-repository-url>
cd <repository-name>
npm i
npm run dev
```
