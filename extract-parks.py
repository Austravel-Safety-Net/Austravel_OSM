#!/usr/bin/env python3
"""
Extract national park and nature reserve polygons from an OSM PBF file.

Many Australian national parks are stored as type=boundary relations in OSM,
which tilemaker cannot assemble into polygons. This script extracts them
into a shapefile that tilemaker can use as a layer source.

Usage:
    pip install osmium shapely fiona pyproj
    python extract-parks.py australia-latest.osm.pbf parks/parks.shp

Output: Shapefile with 'name' and 'class' attributes.
        class is 'national_park' or 'nature_reserve'.
"""

import os
import sys

import osmium
from shapely.geometry import MultiPolygon, Polygon, LineString, mapping as shapely_mapping
from shapely.ops import unary_union, polygonize
import fiona
from fiona.crs import from_epsg


class RelationScanner(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.park_relations = {}

    def relation(self, r):
        tags = dict(r.tags)
        rtype = tags.get("type", "")
        boundary = tags.get("boundary", "")

        if rtype not in ("boundary", "multipolygon"):
            return

        # Only land-based national parks
        park_class = ""
        pt = tags.get("protection_title", "")
        pt_lower = pt.lower()
        name_lower = tags.get("name", "").lower()

        if boundary == "national_park":
            park_class = "national_park"
        elif boundary == "protected_area":
            # Must have "national park" in protection_title
            if "national park" not in pt_lower:
                return
            park_class = "national_park"

        if not park_class:
            return

        # Exclude marine, Aboriginal/Indigenous, aquatic, and marine park zones
        for keyword in ("marine", "aboriginal", "indigenous", "aquatic"):
            if keyword in name_lower or keyword in pt_lower:
                return
        # "National Park Zone" = marine zone (but "CCA Zone" = land)
        if "zone" in pt_lower and "cca zone" not in pt_lower:
            return

        outers, inners = [], []
        for m in r.members:
            if m.type == "w":
                (inners if m.role == "inner" else outers).append(m.ref)

        if outers:
            self.park_relations[r.id] = {
                "name": tags.get("name", ""),
                "class": park_class,
                "outers": outers,
                "inners": inners,
            }


class WayCollector(osmium.SimpleHandler):
    def __init__(self, way_ids):
        super().__init__()
        self.way_ids = way_ids
        self.ways = {}

    def way(self, w):
        if w.id in self.way_ids:
            try:
                coords = [(n.lon, n.lat) for n in w.nodes]
                if len(coords) >= 2:
                    self.ways[w.id] = coords
            except Exception:
                pass


def stitch_ways(way_coords_list):
    lines = [LineString(c) for c in way_coords_list if len(c) >= 2]
    if not lines:
        return []
    return list(polygonize(unary_union(lines)))


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <input.osm.pbf> <output.shp>")
        sys.exit(1)

    pbf_path = sys.argv[1]
    shp_path = sys.argv[2]

    print(f"Pass 1: Scanning relations in {pbf_path}...")
    scanner = RelationScanner()
    scanner.apply_file(pbf_path)
    print(f"  Found {len(scanner.park_relations)} park relations")

    all_way_ids = set()
    for info in scanner.park_relations.values():
        all_way_ids.update(info["outers"])
        all_way_ids.update(info["inners"])

    print(f"Pass 2: Collecting {len(all_way_ids)} way geometries...")
    collector = WayCollector(all_way_ids)
    collector.apply_file(pbf_path, locations=True)
    print(f"  Collected {len(collector.ways)} ways")

    print("Pass 3: Building polygons...")
    features = []
    for rid, info in scanner.park_relations.items():
        outer_coords = [collector.ways[wid] for wid in info["outers"] if wid in collector.ways]
        inner_coords = [collector.ways[wid] for wid in info["inners"] if wid in collector.ways]
        if not outer_coords:
            continue

        try:
            outer_polys = stitch_ways(outer_coords)
            inner_polys = stitch_ways(inner_coords) if inner_coords else []

            if not outer_polys:
                if (len(outer_coords) == 1 and len(outer_coords[0]) >= 4
                        and outer_coords[0][0] == outer_coords[0][-1]):
                    outer_polys = [Polygon(outer_coords[0])]
                if not outer_polys:
                    continue

            result = unary_union(outer_polys)
            if inner_polys:
                result = result.difference(unary_union(inner_polys))
            if result.is_empty:
                continue
            if not result.is_valid:
                result = result.buffer(0)
            if result.is_empty:
                continue

            if result.geom_type == "Polygon":
                result = MultiPolygon([result])
            elif result.geom_type == "GeometryCollection":
                polys = [g for g in result.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
                all_polys = []
                for p in polys:
                    all_polys.extend(p.geoms if p.geom_type == "MultiPolygon" else [p])
                if not all_polys:
                    continue
                result = MultiPolygon(all_polys)

            area_km2 = result.area * 12321  # rough deg-to-km2 at Australian latitudes
            if area_km2 < 0.5:
                continue

            features.append({
                "geometry": result,
                "name": info["name"],
                "class": info["class"],
                "area_km2": area_km2,
            })
        except Exception:
            pass

    features.sort(key=lambda f: f["area_km2"], reverse=True)
    print(f"  Built {len(features)} park polygons (> 0.5 km2)")

    # Show top parks
    for f in features[:10]:
        print(f"    {f['name'][:50]:50s} {f['class']:20s} {f['area_km2']:>10.0f} km2")

    # Write shapefile
    os.makedirs(os.path.dirname(shp_path) or ".", exist_ok=True)
    schema = {"geometry": "MultiPolygon", "properties": {"name": "str:80", "class": "str:20"}}

    with fiona.open(shp_path, "w", driver="ESRI Shapefile", schema=schema, crs=from_epsg(4326)) as dst:
        written = 0
        for f in features:
            try:
                dst.write({
                    "geometry": shapely_mapping(f["geometry"]),
                    "properties": {"name": (f["name"] or "")[:80], "class": f["class"]},
                })
                written += 1
            except Exception:
                pass
        print(f"  Wrote {written} features to {shp_path}")


if __name__ == "__main__":
    main()
