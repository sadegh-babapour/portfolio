from __future__ import annotations

import hashlib
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from poller.static_gtfs_sync import sync_static_gtfs


class StaticGtfsSyncTests(unittest.TestCase):
    def connection_with_state(self, state):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = state
        return connection, cursor

    @patch("poller.static_gtfs_sync.requests.get")
    def test_etag_not_modified_only_advances_check_time(self, get):
        connection, cursor = self.connection_with_state(
            ("https://example.test/gtfs.zip", '"etag"', "old-sha")
        )
        response = Mock(status_code=304)
        get.return_value = response
        checked_at = datetime(2026, 9, 2, 18, 0, tzinfo=timezone.utc)

        result = sync_static_gtfs(
            connection,
            source_url="https://example.test/gtfs.zip",
            route_catalog=Path("missing.csv"),
            now=checked_at,
        )

        self.assertEqual(result, "unchanged")
        get.assert_called_once_with(
            "https://example.test/gtfs.zip",
            headers={"If-None-Match": '"etag"'},
            timeout=90,
        )
        self.assertTrue(any("UPDATE transit.static_gtfs_import_state" in call.args[0]
                            for call in cursor.execute.call_args_list))
        connection.commit.assert_called_once_with()

    @patch("poller.static_gtfs_sync.requests.get")
    def test_changed_source_does_not_reuse_previous_etag(self, get):
        connection, _ = self.connection_with_state(
            ("https://old.example/gtfs.zip", '"etag"', "old-sha")
        )
        response = Mock(status_code=200, content=b"same")
        response.headers = {}
        response.raise_for_status = Mock(side_effect=RuntimeError("stop after request"))
        get.return_value = response

        with self.assertRaises(RuntimeError):
            sync_static_gtfs(
                connection,
                source_url="https://new.example/gtfs.zip",
                route_catalog=Path("missing.csv"),
            )

        get.assert_called_once_with(
            "https://new.example/gtfs.zip",
            headers={},
            timeout=90,
        )

    @patch("poller.static_gtfs_sync.load_gtfs_archive")
    @patch("poller.static_gtfs_sync.requests.get")
    def test_changed_archive_reloads_and_records_hash(self, get, load_archive):
        connection, cursor = self.connection_with_state(None)
        archive = b"new-static-gtfs"
        response = Mock(status_code=200, content=archive, headers={"ETag": '"new"'})
        response.raise_for_status = Mock()
        get.return_value = response
        checked_at = datetime(2026, 9, 2, 18, 0, tzinfo=timezone.utc)

        result = sync_static_gtfs(
            connection,
            source_url="https://example.test/gtfs.zip",
            route_catalog=Path("missing.csv"),
            now=checked_at,
        )

        self.assertEqual(result, "loaded")
        load_archive.assert_called_once_with(connection, archive, None)
        state_write = next(
            call for call in cursor.execute.call_args_list
            if "INSERT INTO transit.static_gtfs_import_state" in call.args[0]
        )
        self.assertIn(hashlib.sha256(archive).hexdigest(), state_write.args[1])
        connection.commit.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
