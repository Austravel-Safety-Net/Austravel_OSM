#!/usr/bin/env bash
#
# Generate Australia PMTiles from Geofabrik PBF extract + coastline data.
#
# Prerequisites:
#   - Docker (for tilemaker)
#   - ~6 GB free disk space
#   - ~30 minutes on Apple M1 Max
#
# Usage:
#   cd tiles/
#   ./generate-tiles.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Docker CLI path (macOS Docker Desktop)
DOCKER="/Applications/Docker.app/Contents/Resources/bin/docker"
if [ ! -x "$DOCKER" ]; then
    DOCKER="docker"
fi

PBF_URL="https://download.geofabrik.de/australia-oceania/australia-latest.osm.pbf"
PBF_FILE="australia-latest.osm.pbf"
COASTLINE_URL="https://osmdata.openstreetmap.de/download/water-polygons-split-4326.zip"
COASTLINE_ZIP="water-polygons.zip"
COASTLINE_DIR="coastline"
OUTPUT_FILE="australia.pmtiles"
TEMP_OUTPUT="australia-new.pmtiles"

# --- Step 1: Download coastline shapefiles (if not already present) ---
if [ ! -f "$COASTLINE_DIR/water_polygons.shp" ]; then
    echo "==> Downloading coastline shapefiles (~800 MB)..."
    curl -L -o "$COASTLINE_ZIP" "$COASTLINE_URL"
    echo "    Extracting..."
    mkdir -p "$COASTLINE_DIR"
    unzip -o "$COASTLINE_ZIP" -d "$COASTLINE_DIR"
    # Move files up from nested directory
    if [ -d "$COASTLINE_DIR/water-polygons-split-4326" ]; then
        mv "$COASTLINE_DIR/water-polygons-split-4326"/* "$COASTLINE_DIR/"
        rmdir "$COASTLINE_DIR/water-polygons-split-4326"
    fi
    rm -f "$COASTLINE_ZIP"
    echo "    Done."
else
    echo "==> Coastline shapefiles already present, skipping download."
fi

# --- Step 2: Download Australia PBF ---
echo "==> Downloading Australia PBF extract (~880 MB)..."
curl -L -o "$PBF_FILE" "$PBF_URL"
echo "    Done."

# --- Step 3: Generate PMTiles with tilemaker (via Docker) ---
echo "==> Generating PMTiles (this takes 15-30 minutes)..."
$DOCKER run --rm \
    -v "$SCRIPT_DIR":/data \
    ghcr.io/systemed/tilemaker:master \
    --input /data/"$PBF_FILE" \
    --output /data/"$TEMP_OUTPUT" \
    --config /data/config-openmaptiles.json \
    --process /data/process-openmaptiles.lua \
    --store /tmp/tilemaker-store \
    --verbose
echo "    Done."

# --- Step 4: Atomic swap ---
echo "==> Swapping tile file..."
mv "$TEMP_OUTPUT" "$OUTPUT_FILE"
echo "    Done."

# --- Step 5: Clean up PBF (optional — comment out to keep) ---
echo "==> Cleaning up PBF..."
rm -f "$PBF_FILE"
echo "    Done."

echo ""
echo "=== SUCCESS ==="
echo "Generated: $SCRIPT_DIR/$OUTPUT_FILE"
echo "Size: $(du -h "$OUTPUT_FILE" | cut -f1)"
echo ""
echo "Start Martin tile server with: docker compose up -d tileserver"
