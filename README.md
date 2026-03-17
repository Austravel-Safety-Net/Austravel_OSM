# Austravel OSM — Self-Hosted Map Infrastructure

Self-hosted OpenStreetMap vector tile server and geocoding service for the **Austravel SafetyNet HF Radio Operations Platform**. Provides offline-capable map rendering and place search across Australia with no external API dependencies.

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌───────────────────┐
│  MapLibre GL │────▶│    Martin    │────▶│  PMTiles Archives │
│   (browser)  │     │  (port 3000) │     │  australia.pmtiles │
│              │     │              │     │  ocean.pmtiles     │
└──────────────┘     └──────────────┘     └───────────────────┘
       │
       │  /geocode/
       ▼
┌──────────────┐     ┌──────────────┐
│    Django    │────▶│  Nominatim   │
│  (port 8000) │     │  (port 8080) │
└──────────────┘     └──────────────┘
```

| Component | Purpose |
|---|---|
| **Martin** | Rust-based tile server serving PMTiles archives + PBF font glyphs |
| **PMTiles** | Static vector tile archives (Australia land features + global ocean) |
| **Nominatim** | Self-hosted geocoding/place search (Australia data) |
| **MapLibre GL JS** | Client-side vector tile renderer (WebGL) |
| **tilemaker** | Converts OSM PBF extracts to PMTiles using Lua processing scripts |

## Quick Start

### Prerequisites

- Docker and Docker Compose
- ~5 GB disk space (tiles + Nominatim database)

### Start Services

```bash
docker compose up -d
```

On first run, Nominatim will download and import the Australia PBF extract (~30 minutes).

### Verify

```bash
# Tile server
curl http://localhost:3000/catalog

# Nominatim geocoding
curl "http://localhost:8080/search?q=Alice+Springs&format=json&limit=1"
```

## Tile Generation

To regenerate vector tiles from a fresh OSM extract:

```bash
# Download latest Australia PBF
curl -L -o tiles/australia-latest.osm.pbf \
  https://download.geofabrik.de/australia-oceania/australia-latest.osm.pbf

# Generate Australia tiles (~20 minutes)
./generate-tiles.sh

# Generate global ocean tiles (~5 minutes)
docker run --rm -v "$(pwd)/tiles":/data ghcr.io/systemed/tilemaker:master \
  --input /data/australia-latest.osm.pbf \
  --output /data/ocean.pmtiles \
  --config /data/config-ocean.json \
  --process /data/process-ocean.lua \
  --bbox -180,-85,180,85

# Restart Martin to pick up new tiles
docker compose restart tileserver
```

### National Parks

Large national parks are extracted from the PBF as a separate shapefile layer to ensure proper rendering of multipolygon relations:

```bash
python3 extract-parks.py
```

This creates `tiles/parks/parks.shp` which is referenced by `config-openmaptiles.json` as the `park_major` layer.

## File Structure

```
Austravel_OSM/
├── docker-compose.yml          # Martin + Nominatim services
├── config-openmaptiles.json    # Tilemaker layer config (Australia)
├── config-ocean.json           # Tilemaker layer config (global ocean)
├── process-openmaptiles.lua    # Lua processing script (features + styling attrs)
├── process-ocean.lua           # Lua processing script (ocean only)
├── generate-tiles.sh           # Full tile regeneration script
├── extract-parks.py            # Extract national parks to shapefile
├── fonts/                      # Open Sans TTF fonts (served as PBF glyphs)
├── style/
│   └── style.json              # MapLibre GL JS style definition
└── editor/
    └── index.html              # Standalone style editor (optional)
```

## Map Style

The style (`style/style.json`) is a custom light theme with layers for:

- Ocean and coastlines (global coverage)
- Landcover (wood, grass, farmland, sand, wetland, rock)
- Land use (residential, commercial, schools, hospitals, military)
- National parks (with dedicated `park_major` layer for large parks)
- Water bodies and waterways
- Transportation (roads, rail, paths, tracks)
- Buildings (z13+)
- Administrative boundaries (state, country)
- Aeroways (runways, taxiways, aerodrome labels)
- Place labels (cities, towns, suburbs, neighbourhoods)

The style is compatible with MapLibre GL JS, QGIS Vector Tiles, and Maputnik.

## Data Sources

| Data | Source | Update Frequency |
|---|---|---|
| Australia OSM | [Geofabrik](https://download.geofabrik.de/australia-oceania/australia.html) | Daily |
| Coastline polygons | [osmdata.openstreetmap.de](https://osmdata.openstreetmap.de/data/water-polygons.html) | Weekly |
| Nominatim geocoding | Same Australia PBF | On import |

## Integration with DjangoGO

This tile server is consumed by the DjangoGO application:

- **Dashboard map** — MapLibre GL JS with travelling member and base station markers
- **Base Stations map** — Radio tower markers on self-hosted tiles
- **Map Style Editor** — Interactive layer property editor at `/map/`
- **Sked Log geocoding** — Django proxies place searches to Nominatim at `/geocode/`
- **QGIS** — Connect via Vector Tiles with style URL pointing to `style.json`

## Licence

Map data: OpenStreetMap contributors (ODbL 1.0)
