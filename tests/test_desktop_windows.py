"""Windows job ownership must survive abrupt desktop-backend termination."""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WindowsChildCleanupTests(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "Other-platform behavior")
    def test_other_platforms_do_not_create_a_windows_job(self):
        from fpv_audio_pairing.desktop_windows import enable_child_cleanup

        self.assertIsNone(enable_child_cleanup())

    @unittest.skipUnless(os.name == "nt", "Requires native Windows job objects")
    def test_killing_backend_terminates_its_child_even_with_handle_inheritance(self):
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int32, ctypes.c_uint32]
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        kernel.WaitForSingleObject.restype = ctypes.c_uint32
        kernel.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        kernel.TerminateProcess.restype = ctypes.c_int32
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.CloseHandle.restype = ctypes.c_int32
        code = """
import json, subprocess, sys, time
from fpv_audio_pairing.desktop_windows import enable_child_cleanup
enable_child_cleanup()
child = subprocess.Popen(
    [sys.executable, '-c', 'import time; time.sleep(60)'],
    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    close_fds=False, creationflags=subprocess.CREATE_NO_WINDOW,
)
print(json.dumps({'pid': child.pid}), flush=True)
time.sleep(60)
"""
        with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as errors:
            process = subprocess.Popen([sys.executable, "-c", code], cwd=ROOT,
                                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                       stderr=errors, text=True, encoding="utf-8",
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            child_handle = None
            try:
                lines = queue.Queue()
                threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True).start()
                try:
                    line = lines.get(timeout=10)
                except queue.Empty:
                    self.fail("Backend did not start its child within 10 seconds")
                errors.seek(0)
                self.assertTrue(line, f"Backend setup failed: {errors.read()}")
                child_pid = json.loads(line)["pid"]
                # Retain a real process handle so PID reuse cannot hide a leak.
                child_handle = kernel.OpenProcess(0x00100000 | 0x0001, False, child_pid)
                self.assertTrue(child_handle, "Could not observe the backend child")
                self.assertEqual(kernel.WaitForSingleObject(child_handle, 0), 258)
                process.kill()
                process.wait(timeout=5)
                self.assertEqual(kernel.WaitForSingleObject(child_handle, 5000), 0,
                                 "Child remained alive after abrupt backend termination")
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
                process.stdout.close()
                if child_handle:
                    if kernel.WaitForSingleObject(child_handle, 0) == 258:
                        kernel.TerminateProcess(child_handle, 1)
                        kernel.WaitForSingleObject(child_handle, 5000)
                    kernel.CloseHandle(child_handle)


if __name__ == "__main__":
    unittest.main()
