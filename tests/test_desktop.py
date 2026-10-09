"""Exercise the private desktop server through its real process/HTTP boundary."""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
TOKEN = "desktop-integration-test-secret"


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.data = Path(self.temporary.name) / "desktop data"
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def start(self, *, port=0, token=TOKEN, ready=True):
        environment = os.environ.copy()
        environment.update(FPV_DESKTOP_TOKEN=token, PYTHONUNBUFFERED="1",
                           OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1")
        # An inherited server data directory must not override the desktop choice.
        environment["FPV_AUDIO_DATA_DIR"] = str(Path(self.temporary.name) / "wrong data")
        errors = tempfile.TemporaryFile(mode="w+t", encoding="utf-8")
        self.addCleanup(errors.close)
        process = subprocess.Popen(
            [sys.executable, "-m", "fpv_audio_pairing.desktop", "--data-dir", str(self.data),
             "--port", str(port)], cwd=ROOT, env=environment,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors,
            text=True, encoding="utf-8",
        )

        def cleanup():
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)
            process.stdin.close()
            process.stdout.close()

        self.addCleanup(cleanup)
        if not ready:
            return process, errors
        lines = queue.Queue()
        threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True).start()
        try:
            line = lines.get(timeout=30)
        except queue.Empty:
            self.fail("Desktop backend did not announce readiness within 30 seconds")
        errors.seek(0)
        self.assertTrue(line, f"Backend exited before readiness: {errors.read()}")
        message = json.loads(line)
        self.assertEqual(message["event"], "ready")
        self.assertEqual(set(message), {"event", "url"})
        self.assertRegex(message["url"], r"^http://127\.0\.0\.1:[1-9][0-9]*$")
        return process, message["url"], errors

    def request(self, url, *, token=TOKEN, headers=None):
        request_headers = dict(headers or {})
        if token is not None:
            request_headers["X-Flight-Sync-Token"] = token
        request = urllib.request.Request(url, headers=request_headers)
        try:
            response = self.opener.open(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, response.read()

    def stop(self, process, errors, *, eof=False):
        if eof:
            process.stdin.close()
        else:
            process.stdin.write("shutdown\n")
            process.stdin.flush()
        self.assertEqual(process.wait(timeout=10), 0)
        self.assertEqual(process.stdout.read(), "")
        errors.seek(0)
        self.assertNotIn(TOKEN, errors.read())

    def test_ready_means_http_available_with_isolated_data_and_stdin_shutdown(self):
        process, url, errors = self.start()
        status, body = self.request(url + "/api/system")
        self.assertEqual(status, 200)
        self.assertEqual(Path(json.loads(body)["data"]), self.data.resolve())
        self.assertTrue((self.data / ".app.lock").is_file())
        self.assertFalse((Path(self.temporary.name) / "wrong data").exists())
        self.stop(process, errors)

    def test_every_http_route_requires_the_secret(self):
        process, url, errors = self.start()
        for path in ("/", "/static/style.css", "/api/system", "/api/sessions",
                     "/api/sessions/unknown/videos/unknown/original"):
            for token in (None, "incorrect"):
                with self.subTest(path=path, token=token):
                    self.assertEqual(self.request(url + path, token=token)[0], 401)
        for path in ("/", "/static/style.css", "/api/system", "/api/sessions"):
            with self.subTest(path=path):
                self.assertEqual(self.request(url + path)[0], 200)
        self.stop(process, errors)

    def test_untrusted_host_and_origin_are_rejected(self):
        process, url, errors = self.start()
        self.assertEqual(self.request(url, headers={"Host": "untrusted.example"})[0], 403)
        self.assertEqual(self.request(url, headers={"Origin": "https://untrusted.example"})[0], 403)
        self.assertEqual(self.request(url, headers={"Origin": "null"})[0], 403)
        self.assertEqual(self.request(url, headers={"Origin": url})[0], 200)
        self.stop(process, errors)

    def test_parent_pipe_eof_stops_the_server(self):
        process, _, errors = self.start()
        self.stop(process, errors, eof=True)

    def test_occupied_preferred_port_falls_back_to_available_loopback_port(self):
        with socket.socket() as occupied:
            if os.name == "nt":
                occupied.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            occupied.bind(("0.0.0.0", 0))
            occupied.listen()
            port = occupied.getsockname()[1]
            process, url, errors = self.start(port=port)
            self.assertNotEqual(int(url.rsplit(":", 1)[1]), port)
            self.assertEqual(self.request(url + "/api/system")[0], 200)
            self.stop(process, errors)

    def test_windows_reserved_port_error_falls_back_to_a_real_free_socket(self):
        from fpv_audio_pairing.desktop import bind_loopback

        class ReservedPortSocket(socket.socket):
            def bind(self, address):
                if address[1] == 8768:
                    # Winsock uses access-denied for some exclusive bindings.
                    raise OSError(10013, "A different process reserved this port")
                return super().bind(address)

        with patch("fpv_audio_pairing.desktop.socket.socket", ReservedPortSocket):
            with bind_loopback(8768) as listener:
                self.assertEqual(listener.getsockname()[0], "127.0.0.1")
                self.assertNotEqual(listener.getsockname()[1], 8768)
                with socket.create_connection(listener.getsockname(), timeout=2) as client:
                    self.assertEqual(client.getpeername(), listener.getsockname())

    def test_windows_media_children_hide_console_and_keep_launch_options(self):
        from fpv_audio_pairing import desktop

        native_popen = subprocess.Popen
        flags = []
        no_window = 0x08000000
        new_process_group = 0x00000200

        class RecordingPopen(native_popen):
            def __init__(self, *args, **kwargs):
                flags.append(kwargs.get("creationflags", 0))
                if os.name != "nt":
                    # Linux cannot pass Windows creation flags to the kernel.
                    kwargs["creationflags"] = 0
                super().__init__(*args, **kwargs)

        environment = {**os.environ, "FLIGHT_SYNC_CHILD_TEST": "preserved"}
        code = ("import ctypes,json,os; print(json.dumps([os.getcwd(), "
                "os.environ['FLIGHT_SYNC_CHILD_TEST'], "
                "bool(ctypes.windll.kernel32.GetConsoleWindow()) if os.name == 'nt' else False]))")
        with patch.object(desktop, "os", SimpleNamespace(name="nt")), \
                patch.object(subprocess, "CREATE_NO_WINDOW", no_window, create=True), \
                patch.object(subprocess, "Popen", RecordingPopen):
            desktop.hide_child_consoles()
            result = subprocess.run([sys.executable, "-c", code], cwd=self.temporary.name,
                                    env=environment, text=True, capture_output=True,
                                    creationflags=new_process_group, check=True, timeout=10)
        self.assertEqual(flags, [no_window | new_process_group])
        directory, inherited, has_console = json.loads(result.stdout)
        self.assertEqual(Path(directory).resolve(), Path(self.temporary.name).resolve())
        self.assertEqual(inherited, "preserved")
        self.assertFalse(has_console)

    def test_restart_marks_unfinished_jobs_interrupted_and_reuses_port(self):
        sid = "a" * 32
        folder = self.data / "sessions" / sid
        folder.mkdir(parents=True)
        session = {"id": sid, "name": "Interrupted project", "created": 1,
                   "videos": [], "pairs": [], "exports": [], "folders": {},
                   "job": {"status": "running", "percent": 42}}
        (folder / "session.json").write_text(json.dumps(session), encoding="utf-8")
        process, url, errors = self.start()
        saved = json.loads((folder / "session.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["job"]["status"], "interrupted")
        self.assertEqual(saved["job"]["percent"], 42)
        self.stop(process, errors)
        restarted, second_url, second_errors = self.start(port=int(url.rsplit(":", 1)[1]))
        self.assertEqual(second_url, url)
        self.stop(restarted, second_errors)

    def test_missing_secret_fails_before_starting_server(self):
        process, errors = self.start(token="", ready=False)
        self.assertNotEqual(process.wait(timeout=10), 0)
        self.assertEqual(process.stdout.read(), "")
        errors.seek(0)
        self.assertIn("FPV_DESKTOP_TOKEN", errors.read())
        self.assertFalse(self.data.exists())


if __name__ == "__main__":
    unittest.main()
