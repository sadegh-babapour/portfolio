# app/services/load_lrt.py
# Loads CTrain stations and route shapes into Postgres.
# Run: python -m app.services.load_lrt

import csv
import json
import logging
import os
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

# ── Curated station lists ────────────────────────────────────────
# Ordered south→north for Red, west→east for Blue
# Names must match substrings in stops.txt stop_name field

RED_LINE_STATIONS = [
    ('Somerset - Bridlewood', True),
    ('Shawnessy',             False),
    ('Fish Creek - Lacombe',  False),
    ('Canyon Meadows',        False),
    ('Anderson',              False),
    ('Southland',             False),
    ('Heritage',              False),
    ('Chinook',               False),
    ('39 Avenue',             False),
    ('Erlton / Stampede',     False),
    ('Victoria Park / Stampede', False),
    ('City Hall',             False),
    ('Sunnyside',             False),
    ('Lions Park',            False),
    ('Banff Trail',           False),
    ('University',            False),
    ('Brentwood',             False),
    ('Dalhousie',             False),
    ('Crowfoot',              False),
    ('Tuscany',               True),
]

BLUE_LINE_STATIONS = [
    ('69 Street',             True),
    ('Sirocco',               False),
    ('45 Street',             False),
    ('Westbrook',             False),
    ('Shaganappi Point',      False),
    ('Sunalta',               False),
    ('Downtown West-Kerby',   False),
    ('City Hall',             False),
    ('Victoria Park / Stampede', False),
    ('Erlton / Stampede',     False),
    ('Zoo',                   False),
    ('Bridgeland - Memorial', False),
    ('Barlow - Max Bell',     False),
    ('Franklin',              False),
    ('Marlborough',           False),
    ('Rundle',                False),
    ('Whitehorn',             False),
    ('McKnight - Westwinds',  False),
    ('Martindale',            False),
    ('Saddletowne',           True),
]

# Shape IDs for each direction — we pick the longest shape per line
RED_SHAPE_IDS  = None  # determined from trips.txt
BLUE_SHAPE_IDS = None


def _find_station_coords(name_fragment: str, stops: list[dict]) -> tuple[float, float] | None:
    """Average coordinates of all platform stops matching the fragment."""
    matches = [s for s in stops
               if name_fragment.lower() in s['stop_name'].lower()
               and 'station' in s['stop_name'].lower()]
    if not matches:
        return None
    avg_lat = sum(float(s['stop_lat']) for s in matches) / len(matches)
    avg_lon = sum(float(s['stop_lon']) for s in matches) / len(matches)
    return round(avg_lat, 6), round(avg_lon, 6)


def _best_shape(shape_ids: set, shapes_by_id: dict, route_id: str, trips: list) -> str:
    """Pick the shape_id with the most points for a given route (= most complete route)."""
    route_shapes = {t['shape_id'] for t in trips if t['route_id'] == route_id}
    best_id = max(route_shapes, key=lambda sid: len(shapes_by_id.get(sid, [])))
    return best_id


def load_lrt_data(
    stops_path:  str = 'data/stops.txt',
    shapes_path: str = 'data/shapes.txt',
    trips_path:  str = 'data/trips.txt',
) -> dict:
    from app.services.db import get_pool, init_pool
    if not get_pool():
        init_pool()
    pool = get_pool()
    if not pool:
        log.error("No DB pool.")
        return {}

    # read input files
    with open(stops_path,  'r') as f: stops  = list(csv.DictReader(f))
    with open(shapes_path, 'r') as f: shapes = list(csv.DictReader(f))
    with open(trips_path,  'r') as f: trips  = list(csv.DictReader(f))

    # group shapes by shape_id
    shapes_by_id: dict[str, list] = {}
    for s in shapes:
        sid = s['shape_id']
        if sid not in shapes_by_id:
            shapes_by_id[sid] = []
        shapes_by_id[sid].append(s)

    # pick best shape per line (most points = most complete)
    red_shape_id  = _best_shape(set(), shapes_by_id, '201-20780', trips)
    blue_shape_id = _best_shape(set(), shapes_by_id, '202-20780', trips)
    log.info("Red Line shape: %s (%d pts), Blue Line shape: %s (%d pts)",
             red_shape_id, len(shapes_by_id[red_shape_id]),
             blue_shape_id, len(shapes_by_id[blue_shape_id]))

    with pool.connection() as conn:
        with conn.transaction():
            with conn.cursor() as cur:

                # ── clear existing data ──────────────────────
                cur.execute("DELETE FROM lrt_stations")
                cur.execute("DELETE FROM lrt_shapes")

                # ── load stations ────────────────────────────
                station_count = 0

                # track shared stations (on both lines)
                red_names   = {name for name, _ in RED_LINE_STATIONS}
                blue_names  = {name for name, _ in BLUE_LINE_STATIONS}
                shared      = red_names & blue_names

                for seq, (name, is_terminal) in enumerate(RED_LINE_STATIONS):
                    coords = _find_station_coords(name, stops)
                    if not coords:
                        log.warning("Station not found: %s", name)
                        continue
                    line = 'both' if name in shared else 'red'
                    cur.execute("""
                        INSERT INTO lrt_stations
                            (station_name, lat, lon, line, sequence, is_terminal)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (name, coords[0], coords[1], line, seq, is_terminal))
                    station_count += 1

                for seq, (name, is_terminal) in enumerate(BLUE_LINE_STATIONS):
                    if name in shared:
                        continue  # already inserted as 'both'
                    coords = _find_station_coords(name, stops)
                    if not coords:
                        log.warning("Station not found: %s", name)
                        continue
                    cur.execute("""
                        INSERT INTO lrt_stations
                            (station_name, lat, lon, line, sequence, is_terminal)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (name, coords[0], coords[1], 'blue', seq, is_terminal))
                    station_count += 1

                log.info("Loaded %d stations.", station_count)

                # ── load route shapes ────────────────────────
                shape_count = 0
                for line, shape_id in [('red', red_shape_id), ('blue', blue_shape_id)]:
                    pts = sorted(shapes_by_id[shape_id],
                                 key=lambda s: int(s['shape_pt_sequence']))
                    for pt in pts:
                        cur.execute("""
                            INSERT INTO lrt_shapes
                                (shape_id, sequence, lat, lon, line)
                            VALUES (%s, %s, %s, %s, %s)
                            ON CONFLICT DO NOTHING
                        """, (
                            shape_id,
                            int(pt['shape_pt_sequence']),
                            float(pt['shape_pt_lat']),
                            float(pt['shape_pt_lon']),
                            line,
                        ))
                        shape_count += 1

                log.info("Loaded %d shape points.", shape_count)

    return {
        'stations': station_count,
        'shape_points': shape_count,
        'red_shape': red_shape_id,
        'blue_shape': blue_shape_id,
    }


if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO)
    result = load_lrt_data(
        stops_path  = sys.argv[1] if len(sys.argv) > 1 else 'data/stops.txt',
        shapes_path = sys.argv[2] if len(sys.argv) > 2 else 'data/shapes.txt',
        trips_path  = sys.argv[3] if len(sys.argv) > 3 else 'data/trips.txt',
    )
    print(f"Done: {result}")