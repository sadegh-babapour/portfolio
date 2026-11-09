"""The Railway `dagster` service's process supervision and heartbeat, with real child processes.

No database and no dbt: this imports only orchestration.production and orchestration.alerts.

  .venv-data/bin/python -m unittest discover -s test_data
"""
import socket
import subprocess
import sys
import threading
import time
import unittest
from unittest import mock

import requests
from dagster import (DagsterEventType, DagsterInstance, DefaultSensorStatus, asset, build_run_status_sensor_context,
                     materialize)

from orchestration import alerts, production

SLEEPER = [sys.executable, "-c", "import time; time.sleep(60)"]
POPEN = subprocess.Popen  # the real one, for tests that patch it


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class SupervisionTests(unittest.TestCase):

    def setUp(self):
        patcher = mock.patch.object(production, "STOP_GRACE_SECONDS", 5)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.processes = []

    def tearDown(self):
        for process in self.processes:
            if process.poll() is None:
                process.kill()
                process.wait()

    def spawn(self, command, **kwargs):
        process = POPEN(command, **kwargs)
        self.processes.append(process)
        return process

    def test_when_one_process_exits_the_other_is_stopped_and_the_service_fails(self):
        survivor = self.spawn(SLEEPER)
        quitter = self.spawn([sys.executable, "-c", "raise SystemExit(3)"])
        with mock.patch("sys.stderr") as stderr:
            code = production.watch({"code_server": survivor, "daemon": quitter}, threading.Event(), interval=0.1)
        self.assertEqual(code, 1)
        self.assertIsNotNone(survivor.poll())
        self.assertIn("daemon exited with 3", "".join(str(c.args[0]) for c in stderr.write.call_args_list))

    def test_a_requested_stop_stops_both_and_succeeds(self):
        processes = {"code_server": self.spawn(SLEEPER), "daemon": self.spawn(SLEEPER)}
        stop = threading.Event()
        threading.Timer(0.3, stop.set).start()
        self.assertEqual(production.watch(processes, stop, interval=0.1), 0)
        self.assertTrue(all(p.poll() is not None for p in processes.values()))

    def test_a_process_that_ignores_sigterm_is_killed(self):
        stubborn = self.spawn([sys.executable, "-c",
                               "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                               "print('ready', flush=True); time.sleep(60)"])
        time.sleep(0.5)  # let it install the handler
        with mock.patch.object(production, "STOP_GRACE_SECONDS", 0.5):
            production.stop_all([stubborn])
        self.assertEqual(stubborn.returncode, -9)

    def test_ready_once_the_server_listens(self):
        port = free_port()
        server = self.spawn([sys.executable, "-c",
                             f"import socket, time; s = socket.socket(); s.bind(('127.0.0.1', {port})); "
                             "time.sleep(0.5); s.listen(); time.sleep(60)"])
        self.assertTrue(production.wait_until_listening(server, "127.0.0.1", port, 10, threading.Event(),
                                                        interval=0.1))

    def test_not_ready_if_the_server_exits_first(self):
        crashed = self.spawn([sys.executable, "-c", "raise SystemExit(1)"])
        started = time.monotonic()
        self.assertFalse(production.wait_until_listening(crashed, "127.0.0.1", free_port(), 30, threading.Event(),
                                                         interval=0.1))
        self.assertLess(time.monotonic() - started, 10)

    def test_a_code_server_that_never_listens_fails_the_service_without_a_daemon(self):
        with mock.patch.object(production, "CODE_SERVER", SLEEPER), \
                mock.patch.object(production, "CODE_SERVER_PORT", free_port()), \
                mock.patch.object(production, "CODE_SERVER_READY_SECONDS", 1), \
                mock.patch.object(production.subprocess, "Popen", side_effect=self.spawn) as popen, \
                mock.patch("sys.stderr") as stderr:
            code = production.run_services(threading.Event())
        self.assertEqual(code, 1)
        self.assertEqual(popen.call_count, 1)  # the daemon never started
        self.assertIsNotNone(self.processes[0].poll())
        self.assertIn("code_server_not_ready", "".join(str(c.args[0]) for c in stderr.write.call_args_list))


class HeartbeatTests(unittest.TestCase):

    def test_pings_the_configured_url(self):
        get = mock.Mock()
        self.assertTrue(alerts.ping_heartbeat(env={alerts.HEARTBEAT_SETTING: "https://hc.example/abc"}, get=get))
        self.assertEqual(get.call_args.args, ("https://hc.example/abc",))
        get.return_value.raise_for_status.assert_called_once()

    def test_no_url_no_ping(self):
        get = mock.Mock()
        self.assertFalse(alerts.ping_heartbeat(env={}, get=get))
        get.assert_not_called()

    def test_a_failed_ping_never_shows_the_url(self):
        secret = "https://hc.example/0f3c-secret-uuid"
        get = mock.Mock(side_effect=requests.ConnectionError(f"Max retries exceeded with url: {secret}"))
        with self.assertRaises(RuntimeError) as raised:
            alerts.ping_heartbeat(env={alerts.HEARTBEAT_SETTING: secret}, get=get)
        self.assertEqual(str(raised.exception), "heartbeat ping failed: ConnectionError")
        self.assertIsNone(raised.exception.__cause__)

    def test_the_sensor_pings_after_a_successful_run(self):
        @asset
        def one():
            return 1

        instance = DagsterInstance.ephemeral()
        run = materialize([one], instance=instance)
        (success,) = instance.all_logs(run.run_id, of_type=DagsterEventType.RUN_SUCCESS)
        sensor = next(s for s in alerts.sensors(DefaultSensorStatus.STOPPED) if s.name == "ping_heartbeat_on_success")
        context = build_run_status_sensor_context(sensor_name=sensor.name, dagster_event=success.dagster_event,
                                                  dagster_instance=instance,
                                                  dagster_run=instance.get_run_by_id(run.run_id))
        with mock.patch.object(alerts, "ping_heartbeat", return_value=True) as ping:
            sensor(context)
        ping.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
