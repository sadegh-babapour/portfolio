# import csv
# import json
# import re
# import os
# import logging
# from dotenv import load_dotenv

# load_dotenv()
# log = logging.getLogger(__name__)


# def parse_longest_segment(wkt: str) -> list[list[float]]:
#     """
#     Extract only the longest line segment from a MULTILINESTRING.
#     Avoids drawing both directions as duplicate lines.
#     Returns [[lat, lon], ...] flipped for Leaflet.
#     """
#     segments = re.findall(r'\(([^()]+)\)', wkt)
#     best = []
#     for seg in segments:
#         coords = re.findall(r'(-?\d+\.\d+)\s+(-?\d+\.\d+)', seg)
#         points = [[float(lat), float(lon)] for lon, lat in coords]
#         if len(points) > len(best):
#             best = points
#     return best


# def load_routes_from_csv(csv_path: str = 'data/Calgary_Transit_Routes_20260417.csv') -> int:
#     from app.services.db import get_pool, init_pool
#     if not get_pool():
#         init_pool()
#     pool = get_pool()
#     if not pool:
#         log.error("No DB pool — cannot load routes.")
#         return 0
#     if not os.path.exists(csv_path):
#         log.error("CSV not found at %s", csv_path)
#         return 0

#     with open(csv_path, 'r') as f:
#         reader = csv.DictReader(f)
#         rows = list(reader)

#     log.info("Parsing %d routes from CSV...", len(rows))
#     loaded = 0

#     with pool.connection() as conn:
#         with conn.transaction():
#             with conn.cursor() as cur:
#                 for row in rows:
#                     try:
#                         coords = parse_longest_segment(row['MULTILINESTRING'])
#                         if not coords:
#                             continue
#                         cur.execute("""
#                             INSERT INTO transit_routes
#                                 (route_short_name, route_long_name, route_category, coordinates)
#                             VALUES (%s, %s, %s, %s)
#                             ON CONFLICT (route_short_name) DO UPDATE SET
#                                 route_long_name  = EXCLUDED.route_long_name,
#                                 route_category   = EXCLUDED.route_category,
#                                 coordinates      = EXCLUDED.coordinates
#                         """, (
#                             row['ROUTE_SHORT_NAME'],
#                             row['ROUTE_LONG_NAME'],
#                             row['ROUTE_CATEGORY'],
#                             json.dumps(coords),
#                         ))
#                         loaded += 1
#                     except Exception as e:
#                         log.warning("Failed to load route %s: %s", row.get('ROUTE_SHORT_NAME'), e)

#     log.info("Loaded %d routes into transit_routes.", loaded)
#     return loaded


# if __name__ == '__main__':
#     import sys
#     logging.basicConfig(level=logging.INFO)
#     csv_path = sys.argv[1] if len(sys.argv) > 1 else 'data/Calgary_Transit_Routes_20260417.csv'
#     count = load_routes_from_csv(csv_path)
#     print(f"Done — loaded {count} routes.")
import csv
import json
import logging
import os
import re

from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)


def parse_multilinestring(wkt: str) -> list[list[float]]:
    """
    Parse a WKT MULTILINESTRING into a flat list of [lat, lon] points.
    We keep every segment in order instead of only the longest one so the
    stored route geometry is not truncated to a single fragment.
    """
    coords = re.findall(r'(-?\d+\.\d+)\s+(-?\d+\.\d+)', wkt)
    points: list[list[float]] = []
    for lon, lat in coords:
        point = [float(lat), float(lon)]
        if not points or points[-1] != point:
            points.append(point)
    return points


def load_routes_from_csv(csv_path: str = 'data/Calgary_Transit_Routes_20260417.csv') -> int:
    from app.services.db import get_pool, init_pool

    if not get_pool():
        init_pool()
    pool = get_pool()
    if not pool:
        log.error("No DB pool — cannot load routes.")
        return 0
    if not os.path.exists(csv_path):
        log.error("CSV not found at %s", csv_path)
        return 0

    with open(csv_path, 'r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    log.info("Parsing %d routes from CSV...", len(rows))
    loaded = 0

    with pool.connection() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                for row in rows:
                    try:
                        coords = parse_multilinestring(row['MULTILINESTRING'])
                        if not coords:
                            continue
                        cur.execute(
                            """
                            INSERT INTO transit_routes
                                (route_short_name, route_long_name, route_category, coordinates)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (route_short_name) DO UPDATE SET
                                route_long_name = EXCLUDED.route_long_name,
                                route_category = EXCLUDED.route_category,
                                coordinates = EXCLUDED.coordinates
                            """,
                            (
                                row['ROUTE_SHORT_NAME'],
                                row['ROUTE_LONG_NAME'],
                                row['ROUTE_CATEGORY'],
                                json.dumps(coords),
                            ),
                        )
                        loaded += 1
                    except Exception as exc:
                        log.warning("Failed to load route %s: %s", row.get('ROUTE_SHORT_NAME'), exc)

    log.info("Loaded %d routes into transit_routes.", loaded)
    return loaded


if __name__ == '__main__':
    import sys

    logging.basicConfig(level=logging.INFO)
    csv_path = sys.argv[1] if len(sys.argv) > 1 else 'data/Calgary_Transit_Routes_20260417.csv'
    count = load_routes_from_csv(csv_path)
    print(f"Done — loaded {count} routes.")
