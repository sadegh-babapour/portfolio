import os
import logging
import random
from datetime import date

from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

log = logging.getLogger(__name__)

_pool: ConnectionPool | None = None


def init_pool() -> None:
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


def normalize_route_label(route_id: str | None) -> str | None:
    if not route_id:
        return None
    return route_id.split("-", 1)[0].strip() or None


# ------------------------------------------------------------------ #
#  Write                                                              #
# ------------------------------------------------------------------ #

def upsert_vehicles(vehicles: list[dict]) -> None:
    if not _pool or not vehicles:
        return

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
                    vid = v["vehicle_id"]
                    lat = v["lat"]
                    lon = v["lon"]
                    route = normalize_route_label(v.get("route_id"))
                    bear = v.get("bearing")
                    speed = v.get("speed")
                    occ = v.get("occupancy")
                    trip_id = v.get("trip_id")
                    headsign = v.get("headsign")
                    quad = quadrant(lat, lon)

                    cur.execute(
                        """
                        INSERT INTO vehicle_positions_raw
                            (vehicle_id, route_id, lat, lon, bearing, speed,
                             occupancy, trip_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (vid, route, lat, lon, bear, speed, occ, trip_id),
                    )

                    cur.execute(
                        """
                        INSERT INTO vehicle_positions_latest
                            (vehicle_id, route_id, lat, lon, bearing, speed,
                             prev_lat, prev_lon, is_stale, quadrant, last_seen,
                             trip_id, headsign)
                        VALUES (%s, %s, %s, %s, %s, %s,
                                NULL, NULL, false, %s, now(), %s, %s)
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
                            last_seen = now(),
                            trip_id   = EXCLUDED.trip_id,
                            headsign  = EXCLUDED.headsign
                        """,
                        (vid, route, lat, lon, bear, speed, quad, trip_id, headsign),
                    )


def trim_raw_table() -> None:
    if not _pool:
        return
    with _pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM vehicle_positions_raw
                WHERE fetched_at < now() - INTERVAL '30 minutes'
                """
            )
            deleted = cur.rowcount
    if deleted:
        log.info("Trimmed %d old rows from vehicle_positions_raw.", deleted)


# ------------------------------------------------------------------ #
#  Read — latest positions                                            #
# ------------------------------------------------------------------ #

_NORMALIZED_ROUTE_SQL = """
COALESCE(
    NULLIF(gt.route_short_name, ''),
    NULLIF(split_part(vpl.route_id, '-', 1), ''),
    NULLIF(vpl.route_id, '')
)
""".strip()


def fetch_latest_vehicles(
    route_id: str | None = None,
    quadrant: str | None = None,
    vehicle_ids: list[str] | None = None,
    route_ids: list[str] | None = None,
) -> list[dict]:
    if not _pool:
        return []

    conditions: list[str] = []
    params: list[object] = []

    if route_id:
        conditions.append(f"{_NORMALIZED_ROUTE_SQL} = %s")
        params.append(route_id)
    if route_ids:
        conditions.append(f"{_NORMALIZED_ROUTE_SQL} = ANY(%s)")
        params.append(route_ids)
    if quadrant:
        conditions.append("vpl.quadrant = %s")
        params.append(quadrant)
    if vehicle_ids:
        conditions.append("vpl.vehicle_id = ANY(%s)")
        params.append(vehicle_ids)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    with _pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    vpl.vehicle_id,
                    {_NORMALIZED_ROUTE_SQL} AS route_id,
                    vpl.lat,
                    vpl.lon,
                    vpl.bearing,
                    vpl.speed,
                    vpl.prev_lat,
                    vpl.prev_lon,
                    vpl.is_stale,
                    vpl.quadrant,
                    vpl.last_seen,
                    vpl.trip_id,
                    COALESCE(NULLIF(vpl.headsign, ''), gt.headsign) AS headsign
                FROM vehicle_positions_latest vpl
                LEFT JOIN gtfs_trips gt ON gt.trip_id = vpl.trip_id
                {where}
                ORDER BY vpl.vehicle_id
                """,
                params,
            )
            return cur.fetchall()


def fetch_route_ids() -> list[str]:
    if not _pool:
        return []
    with _pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DISTINCT {_NORMALIZED_ROUTE_SQL} AS route_id
                FROM vehicle_positions_latest vpl
                LEFT JOIN gtfs_trips gt ON gt.trip_id = vpl.trip_id
                WHERE {_NORMALIZED_ROUTE_SQL} IS NOT NULL
                ORDER BY route_id
                """
            )
            return [row["route_id"] for row in cur.fetchall()]


# ------------------------------------------------------------------ #
#  Read — vehicle history (30 min window)                             #
# ------------------------------------------------------------------ #

def fetch_vehicle_history(vehicle_id: str, limit: int = 60) -> list[dict]:
    if not _pool:
        return []
    with _pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT lat, lon, bearing, speed, fetched_at
                FROM vehicle_positions_raw
                WHERE vehicle_id = %s
                  AND fetched_at >= now() - INTERVAL '30 minutes'
                ORDER BY fetched_at DESC
                LIMIT %s
                """,
                (vehicle_id, limit),
            )
            rows = cur.fetchall()
    return list(reversed(rows))


def fetch_vehicles_history(vehicle_ids: list[str], limit: int = 60) -> dict[str, list[dict]]:
    if not _pool or not vehicle_ids:
        return {}
    with _pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT vehicle_id, lat, lon, bearing, speed, fetched_at
                FROM vehicle_positions_raw
                WHERE vehicle_id = ANY(%s)
                  AND fetched_at >= now() - INTERVAL '30 minutes'
                ORDER BY vehicle_id, fetched_at DESC
                """,
                (vehicle_ids,),
            )
            all_rows = cur.fetchall()

    result: dict[str, list] = {}
    for row in all_rows:
        vid = row["vehicle_id"]
        if vid not in result:
            result[vid] = []
        if len(result[vid]) < limit:
            result[vid].append(
                {
                    "lat": row["lat"],
                    "lon": row["lon"],
                    "bearing": row["bearing"],
                    "speed": row["speed"],
                    "fetched_at": row["fetched_at"].isoformat() if row["fetched_at"] else None,
                }
            )

    for vid in result:
        result[vid] = list(reversed(result[vid]))

    return result


# ------------------------------------------------------------------ #
#  Daily sample                                                       #
# ------------------------------------------------------------------ #

def get_daily_sample() -> dict[str, list[str]]:
    if not _pool:
        return {}
    today = date.today()
    with _pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT quadrant, vehicle_id
                FROM transit_daily_sample
                WHERE sample_date = %s
                ORDER BY quadrant, vehicle_id
                """,
                (today,),
            )
            rows = cur.fetchall()

    result: dict[str, list] = {}
    for row in rows:
        result.setdefault(row["quadrant"], []).append(row["vehicle_id"])
    return result


def create_daily_sample(max_per_quadrant: int = 3) -> dict[str, list[str]]:
    if not _pool:
        return {}
    today = date.today()

    with _pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT quadrant, array_agg(vehicle_id) as ids
                FROM vehicle_positions_latest
                WHERE quadrant IS NOT NULL
                GROUP BY quadrant
                """
            )
            rows = cur.fetchall()

    if not rows:
        return {}

    sample: dict[str, list[str]] = {}
    for row in rows:
        q = row["quadrant"]
        ids = row["ids"]
        sample[q] = random.sample(ids, min(max_per_quadrant, len(ids)))

    with _pool.connection() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM transit_daily_sample WHERE sample_date = %s",
                    (today,),
                )
                for q, ids in sample.items():
                    for vid in ids:
                        cur.execute(
                            """
                            INSERT INTO transit_daily_sample
                                (sample_date, quadrant, vehicle_id)
                            VALUES (%s, %s, %s)
                            ON CONFLICT DO NOTHING
                            """,
                            (today, q, vid),
                        )

    log.info("Created daily sample: %s", {q: len(ids) for q, ids in sample.items()})
    return sample


def get_or_create_daily_sample(max_per_quadrant: int = 3) -> dict[str, list[str]]:
    existing = get_daily_sample()
    if existing:
        return existing
    return create_daily_sample(max_per_quadrant)


# ------------------------------------------------------------------ #
#  GTFS static — trips and shapes                                     #
# ------------------------------------------------------------------ #

def fetch_trip_info(trip_id: str) -> dict | None:
    if not _pool:
        return None
    with _pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT t.route_short_name, t.headsign, t.direction_id, t.shape_id
                FROM gtfs_trips t
                WHERE t.trip_id = %s
                LIMIT 1
                """,
                (trip_id,),
            )
            return cur.fetchone()


def fetch_trips_batch(trip_ids: list[str]) -> dict[str, dict]:
    if not _pool or not trip_ids:
        return {}
    with _pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT trip_id, route_short_name, headsign, direction_id, shape_id
                FROM gtfs_trips
                WHERE trip_id = ANY(%s)
                """,
                (trip_ids,),
            )
            rows = cur.fetchall()
    return {r["trip_id"]: dict(r) for r in rows}


def _fetch_representative_trip(cur, route_short_name: str) -> dict | None:
    cur.execute(
        """
        WITH ranked_shapes AS (
            SELECT
                shape_id,
                direction_id,
                COUNT(*) AS trip_count,
                MIN(trip_id) AS sample_trip_id
            FROM gtfs_trips
            WHERE route_short_name = %s
              AND COALESCE(shape_id, '') <> ''
            GROUP BY shape_id, direction_id
            ORDER BY trip_count DESC, direction_id ASC NULLS LAST, shape_id ASC
            LIMIT 1
        )
        SELECT
            rs.sample_trip_id AS trip_id,
            rs.shape_id,
            rs.direction_id,
            gt.headsign,
            gt.route_short_name
        FROM ranked_shapes rs
        JOIN gtfs_trips gt ON gt.trip_id = rs.sample_trip_id
        LIMIT 1
        """,
        (route_short_name,),
    )
    return cur.fetchone()


def fetch_stops_for_route(route_short_name: str) -> list[dict]:
    if not _pool:
        return []
    with _pool.connection() as conn:
        with conn.cursor() as cur:
            trip = _fetch_representative_trip(cur, route_short_name)
            if not trip:
                return []
            cur.execute(
                """
                SELECT
                    st.stop_id,
                    st.stop_sequence,
                    s.stop_name,
                    s.stop_lat,
                    s.stop_lon,
                    st.shape_dist
                FROM gtfs_stop_times st
                JOIN gtfs_stops s ON s.stop_id = st.stop_id
                WHERE st.trip_id = %s
                ORDER BY st.stop_sequence
                """,
                (trip["trip_id"],),
            )
            return cur.fetchall()


def _fetch_gtfs_shape_points(cur, route_short_name: str) -> list[list[float]]:
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = 'gtfs_shapes'
        ) AS present
        """
    )
    row = cur.fetchone()
    if not row or not row["present"]:
        return []

    trip = _fetch_representative_trip(cur, route_short_name)
    if not trip or not trip.get("shape_id"):
        return []

    cur.execute(
        """
        SELECT shape_pt_lat, shape_pt_lon
        FROM gtfs_shapes
        WHERE shape_id = %s
        ORDER BY shape_pt_sequence
        """,
        (trip["shape_id"],),
    )
    rows = cur.fetchall()
    return [[r["shape_pt_lat"], r["shape_pt_lon"]] for r in rows]


# ------------------------------------------------------------------ #
#  Routes + LRT                                                       #
# ------------------------------------------------------------------ #

def fetch_route_geometry(route_short_name: str) -> list | None:
    if not _pool:
        return None
    with _pool.connection() as conn:
        with conn.cursor() as cur:
            gtfs_coords = _fetch_gtfs_shape_points(cur, route_short_name)
            if gtfs_coords:
                return gtfs_coords
            cur.execute(
                """
                SELECT coordinates FROM transit_routes
                WHERE route_short_name = %s
                """,
                (route_short_name,),
            )
            row = cur.fetchone()
    return row["coordinates"] if row else None


def fetch_lrt_routes() -> list[dict]:
    if not _pool:
        return []
    with _pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT route_short_name, route_long_name, coordinates
                FROM transit_routes
                WHERE route_category = 'LRT'
                ORDER BY route_short_name
                """
            )
            return cur.fetchall()


def fetch_all_route_names() -> list[dict]:
    if not _pool:
        return []
    with _pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT route_short_name, route_long_name, route_category
                FROM transit_routes
                ORDER BY route_category, route_short_name
                """
            )
            return cur.fetchall()


def fetch_lrt_stations(line: str | None = None) -> list[dict]:
    if not _pool:
        return []
    with _pool.connection() as conn:
        with conn.cursor() as cur:
            if line:
                cur.execute(
                    """
                    SELECT station_id, station_name, lat, lon, line, sequence, is_terminal
                    FROM lrt_stations
                    WHERE line = %s OR line = 'both'
                    ORDER BY sequence
                    """,
                    (line,),
                )
            else:
                cur.execute(
                    """
                    SELECT station_id, station_name, lat, lon, line, sequence, is_terminal
                    FROM lrt_stations
                    ORDER BY line, sequence
                    """
                )
            return cur.fetchall()


def fetch_lrt_shape(line: str) -> list[dict]:
    if not _pool:
        return []
    with _pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT lat, lon, sequence
                FROM lrt_shapes
                WHERE line = %s
                ORDER BY sequence
                """,
                (line,),
            )
            return cur.fetchall()


def fetch_lrt_vehicles() -> list[dict]:
    if not _pool:
        return []
    with _pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT vehicle_id, lat, lon, bearing, speed,
                       prev_lat, prev_lon, is_stale, last_seen
                FROM vehicle_positions_latest
                WHERE (
                    vehicle_id ~ '^[0-9]+$'
                    AND vehicle_id::integer BETWEEN 2001 AND 2463
                )
                AND last_seen > now() - INTERVAL '5 minutes'
                ORDER BY vehicle_id
                """
            )
            return cur.fetchall()


def fetch_vehicle_full_history(vehicle_id: str) -> list[dict]:
    if not _pool:
        return []
    with _pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT lat, lon, bearing, speed, fetched_at
                FROM vehicle_positions_raw
                WHERE vehicle_id = %s
                  AND fetched_at > now() - INTERVAL '30 minutes'
                ORDER BY fetched_at ASC
                """,
                (vehicle_id,),
            )
            return cur.fetchall()
