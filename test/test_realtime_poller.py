"""The realtime poller's writers: report times, batching, and the per-feed status row."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from google.transit import gtfs_realtime_pb2

from poller import poll_calgary_gtfs_rt_current as poller

HEADER = datetime(2026, 11, 13, 17, 0, tzinfo=timezone.utc)


def feed_message(header: datetime) -> gtfs_realtime_pb2.FeedMessage:
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = int(header.timestamp())
    return feed


def add_vehicle(feed, entity_id, vehicle_id, trip_id, reported: datetime | None, lat=51.05, lon=-114.07):
    entity = feed.entity.add()
    entity.id = entity_id
    vehicle = entity.vehicle
    vehicle.vehicle.id = vehicle_id
    vehicle.trip.trip_id = trip_id
    vehicle.position.latitude = lat
    vehicle.position.longitude = lon
    if reported is not None:
        vehicle.timestamp = int(reported.timestamp())


def add_trip_update(feed, entity_id, trip_id, stop_sequences):
    entity = feed.entity.add()
    entity.id = entity_id
    update = entity.trip_update
    update.trip.trip_id = trip_id
    update.trip.route_id = "300"
    for sequence in stop_sequences:
        stop = update.stop_time_update.add()
        stop.stop_sequence = sequence
        stop.stop_id = f"stop-{sequence}"
        stop.arrival.time = int((HEADER + timedelta(minutes=sequence)).timestamp())


def run_writer(writer, feed):
    """Run a writer on `feed`; returns the cursor and every execute_values call's (sql, rows)."""
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    batches = []
    with (
        patch.object(poller, "fetch_feed", return_value=(feed.SerializeToString(), feed)),
        patch.object(poller, "execute_values", side_effect=lambda cur, sql, rows, **kw: batches.append((sql, rows))),
    ):
        writer(connection)
    return cursor, batches


def status_call(cursor):
    """The parameters of the poller_feed_status upsert."""
    calls = [c for c in cursor.execute.call_args_list if "poller_feed_status" in c.args[0]]
    assert len(calls) == 1, calls
    return calls[0].args[1]


class ReportTimeTests(unittest.TestCase):
    def test_a_normal_report_keeps_its_own_time(self):
        reported = HEADER - timedelta(seconds=15)
        self.assertEqual(poller.report_time(reported, HEADER), (reported, False))

    def test_a_genuinely_stale_report_stays_stale(self):
        reported = HEADER - timedelta(minutes=40)
        self.assertEqual(poller.report_time(reported, HEADER), (reported, False))

    def test_impossible_times_fall_back_to_the_feed_header(self):
        for reported in (
            datetime(1988, 2, 3, tzinfo=timezone.utc),  # Calgary, 2026-11-09
            datetime(2020, 5, 18, 7, 57, tzinfo=timezone.utc),  # Calgary, 2026-11-13
            HEADER - timedelta(days=2),
            HEADER + timedelta(minutes=11),
            None,
        ):
            with self.subTest(reported=reported):
                self.assertEqual(poller.report_time(reported, HEADER), (HEADER, True))

    def test_without_a_header_the_report_time_is_kept(self):
        self.assertEqual(poller.report_time(None, None), (None, False))
        old = datetime(1988, 2, 3, tzinfo=timezone.utc)
        self.assertEqual(poller.report_time(old, None), (old, False))


class VehiclePositionWriterTests(unittest.TestCase):
    def test_buses_with_impossible_timestamps_are_stored_at_the_feed_time(self):
        feed = feed_message(HEADER)
        add_vehicle(feed, "e1", "bus-1", "trip-1", HEADER - timedelta(seconds=20))
        add_vehicle(feed, "e2", "bus-2", "trip-2", datetime(2020, 5, 18, tzinfo=timezone.utc))
        add_vehicle(feed, "e3", "bus-3", "trip-3", datetime(2020, 5, 18, tzinfo=timezone.utc))

        cursor, batches = run_writer(poller.upsert_vehicle_positions, feed)

        (current_sql, current_rows), (raw_sql, raw_rows) = batches
        self.assertIn("vehicle_positions_current", current_sql)
        self.assertIn("vehicle_positions_raw", raw_sql)
        self.assertEqual(
            {row[0]: row[3] for row in current_rows},
            {"bus-1": HEADER - timedelta(seconds=20), "bus-2": HEADER, "bus-3": HEADER},
        )
        self.assertEqual(sorted(row[4] for row in raw_rows), [HEADER - timedelta(seconds=20), HEADER, HEADER])
        _name, _duration, header, entities, written, from_header = status_call(cursor)
        self.assertEqual((header, entities, written, from_header), (HEADER, 3, 3, 2))

    def test_one_batch_per_table_and_one_row_per_bus(self):
        feed = feed_message(HEADER)
        for index in range(2500):
            add_vehicle(feed, f"e{index}", f"bus-{index}", f"trip-{index}", HEADER)
        # The same bus twice in one feed: the batch upsert must carry it once.
        add_vehicle(feed, "dup", "bus-7", "trip-7b", HEADER, lat=51.1)

        _cursor, batches = run_writer(poller.upsert_vehicle_positions, feed)

        self.assertEqual(len(batches), 2)
        current_rows = batches[0][1]
        self.assertEqual(len(current_rows), 2500)
        self.assertEqual([row for row in current_rows if row[0] == "bus-7"][0][1], "trip-7b")
        self.assertEqual(len(batches[1][1]), 2501)

    def test_reports_without_trip_or_position_are_skipped(self):
        feed = feed_message(HEADER)
        add_vehicle(feed, "e1", "bus-1", "", HEADER)
        entity = feed.entity.add()
        entity.id = "e2"
        entity.vehicle.vehicle.id = "bus-2"
        entity.vehicle.trip.trip_id = "trip-2"

        cursor, batches = run_writer(poller.upsert_vehicle_positions, feed)

        self.assertEqual(batches, [])
        _name, _duration, _header, entities, written, _from_header = status_call(cursor)
        self.assertEqual((entities, written), (2, 0))


class TripUpdateWriterTests(unittest.TestCase):
    def test_stop_times_are_written_in_batches_not_row_by_row(self):
        feed = feed_message(HEADER)
        for trip in range(300):
            add_trip_update(feed, f"e{trip}", f"trip-{trip}", range(1, 41))

        cursor, batches = run_writer(poller.upsert_trip_updates, feed)

        (parent_sql, parents), (child_sql, children) = batches
        self.assertIn("trip_updates_current", parent_sql)
        self.assertIn("trip_update_stop_times_current", child_sql)
        self.assertEqual((len(parents), len(children)), (300, 12000))
        # One delete for every trip's old stop list, not one per trip.
        deletes = [c for c in cursor.execute.call_args_list if "where trip_id = any" in c.args[0]]
        self.assertEqual(len(deletes), 1)
        self.assertEqual(len(deletes[0].args[1][0]), 300)
        self.assertLess(cursor.execute.call_count, 10)

    def test_repeated_trips_and_stops_are_carried_once(self):
        feed = feed_message(HEADER)
        add_trip_update(feed, "e1", "trip-1", [1, 2, 2])
        add_trip_update(feed, "e2", "trip-1", [3])
        add_trip_update(feed, "e3", "trip-2", [0, 1])

        cursor, batches = run_writer(poller.upsert_trip_updates, feed)

        (_parent_sql, parents), (_child_sql, children) = batches
        self.assertEqual(sorted(row[0] for row in parents), ["trip-1", "trip-2"])
        # Stop sequence 0 is skipped, as before.
        self.assertEqual(sorted((row[0], row[1]) for row in children),
                         [("trip-1", 1), ("trip-1", 2), ("trip-1", 3), ("trip-2", 1)])
        _name, _duration, _header, entities, written, _from_header = status_call(cursor)
        self.assertEqual((entities, written), (3, 2))


class PassScheduleTests(unittest.TestCase):
    def test_a_pass_sleeps_only_the_rest_of_the_interval(self):
        self.assertEqual(poller.next_pass_delay(30, 4.5), 25.5)
        self.assertEqual(poller.next_pass_delay(30, 29.5), 1.0)
        self.assertEqual(poller.next_pass_delay(30, 95), 1.0)


if __name__ == "__main__":
    unittest.main()
