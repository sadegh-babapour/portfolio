# app/services/db.py
# Manages the Postgres connection pool and all DB write/read operations
# for the transit map feature.

import os
import logging
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

log = logging.getLogger(__name__)

# Module-level pool — initialised once when the app starts via init_pool()
_pool: ConnectionPool | None = None


def init_pool() -> None:
    """Call this once at app startup. Reads DATABASE_URL from environment."""
    global _pool
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        log.warning("DATABASE_URL not set — transit map DB features disabled.")
        return
    _pool = ConnectionPool(
        conninfo=db_url,
        min_size=1,
        max_size=5,
        kwargs={"row_factory": dict_row},
    )
    log.info("Postgres connection pool initialised.")


def get_pool() -> ConnectionPool | None:
    return _pool


# ------------------------------------------------------------------ #
#  Write                                                               #
# ------------------------------------------------------------------ #

def upsert_vehicles(vehicles: list[dict]) -> None:
    """
    Writes a batch of vehicle dicts to both tables in one transaction:
      - vehicle_positions_raw  → append row
      - vehicle_positions_latest → upsert (one row per vehicle_id)

    Each dict must have: vehicle_id, lat, lon
    Optional keys:       route_id, bearing, speed, occupancy
    """
    if not _pool or not vehicles:
        return

    # Calgary centre for quadrant calculation
    CALGARY_LAT = 51.0447
    CALGARY_LON = -114.0719

    def quadrant(lat: float, lon: float) -> str:
        ns = "N" if lat >= CALGARY_LAT else "S"
        ew = "E" if lon >= CALGARY_LON else "W"
        return ns + ew

    with _pool.connection() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                for v in vehicles:
                    vid   = v["vehicle_id"]
                    lat   = v["lat"]
                    lon   = v["lon"]
                    route = v.get("route_id")
                    bear  = v.get("bearing")
                    speed = v.get("speed")
                    occ   = v.get("occupancy")
                    quad  = quadrant(lat, lon)

                    # 1. Append to raw history
                    cur.execute("""
                        INSERT INTO vehicle_positions_raw
                            (vehicle_id, route_id, lat, lon, bearing, speed, occupancy)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (vid, route, lat, lon, bear, speed, occ))

                    # 2. Upsert latest — shift current → prev, detect stale
                    cur.execute("""
                        INSERT INTO vehicle_positions_latest
                            (vehicle_id, route_id, lat, lon, bearing, speed,
                             prev_lat, prev_lon, is_stale, quadrant, last_seen)
                        VALUES (%s, %s, %s, %s, %s, %s,
                                NULL, NULL, false, %s, now())
                        ON CONFLICT (vehicle_id) DO UPDATE SET
                            route_id  = EXCLUDED.route_id,
                            prev_lat  = vehicle_positions_latest.lat,
                            prev_lon  = vehicle_positions_latest.lon,
                            lat       = EXCLUDED.lat,
                            lon       = EXCLUDED.lon,
                            bearing   = EXCLUDED.bearing,
                            speed     = EXCLUDED.speed,
                            is_stale  = (
                                vehicle_positions_latest.lat = EXCLUDED.lat AND
                                vehicle_positions_latest.lon = EXCLUDED.lon
                            ),
                            quadrant  = EXCLUDED.quadrant,
                            last_seen = now()
                    """, (vid, route, lat, lon, bear, speed, quad))


# ------------------------------------------------------------------ #
#  Read                                                                #
# ------------------------------------------------------------------ #

def fetch_latest_vehicles(route_id: str | None = None,
                          quadrant: str | None = None) -> list[dict]:
    """
    Returns current vehicle positions from vehicle_positions_latest.
    Optionally filter by route_id and/or quadrant (NE/NW/SE/SW).
    """
    if not _pool:
        return []

    conditions = []
    params = []

    if route_id:
        conditions.append("route_id = %s")
        params.append(route_id)
    if quadrant:
        conditions.append("quadrant = %s")
        params.append(quadrant)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    with _pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT vehicle_id, route_id, lat, lon, bearing, speed,
                       prev_lat, prev_lon, is_stale, quadrant, last_seen
                FROM vehicle_positions_latest
                {where}
                ORDER BY vehicle_id
            """, params)
            return cur.fetchall()


def fetch_route_ids() -> list[str]:
    """Returns a sorted list of all known route IDs for the filter dropdown."""
    if not _pool:
        return []
    with _pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT route_id
                FROM vehicle_positions_latest
                WHERE route_id IS NOT NULL
                ORDER BY route_id
            """)
            return [row["route_id"] for row in cur.fetchall()]
            