"""Private loopback server owned by the Electron desktop process.

Stdout is a machine-readable readiness channel. Closing stdin or sending
``shutdown`` asks the server to stop; Electron bounds shutdown and removes any
remaining child processes if a media operation cannot finish promptly.
"""
from __future__ import annotations

import argparse
import hmac
import json
import multiprocessing
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading

from .desktop_windows import enable_child_cleanup


class DesktopAccess:
    """Authenticate every HTTP request before routing or reading request bodies."""

    def __init__(self, app, token: str, port: int):
        self.app = app
        self.token = token.encode("utf-8")
        self.host = f"127.0.0.1:{port}".encode("ascii")
        self.origin = b"http://" + self.host

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = scope.get("headers", [])
        tokens = [value for name, value in headers if name == b"x-flight-sync-token"]
        hosts = [value for name, value in headers if name == b"host"]
        origins = [value for name, value in headers if name == b"origin"]
        status = 0
        if len(tokens) != 1 or not hmac.compare_digest(tokens[0], self.token):
            status = 401
        elif hosts != [self.host] or (origins and origins != [self.origin]):
            status = 403
        if status:
            body = b'{"detail":"Desktop access denied"}'
            await send({"type": "http.response.start", "status": status, "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
                (b"cache-control", b"no-store"),
            ]})
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)


def hide_child_consoles():
    """Apply desktop window behavior to existing FFmpeg/ffprobe call sites."""
    if os.name != "nt":
        return

    class DesktopPopen(subprocess.Popen):
        def __init__(self, *args, **kwargs):
            kwargs["creationflags"] = kwargs.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
            super().__init__(*args, **kwargs)

    # subprocess.run delegates to this class too. Installing only in desktop
    # startup preserves ordinary CLI behavior and each caller's other options.
    subprocess.Popen = DesktopPopen


def bind_loopback(preferred_port: int) -> socket.socket:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if os.name == "nt":
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind(("127.0.0.1", preferred_port))
        except OSError:
            if preferred_port == 0:
                raise
            # Windows can report an exclusive/reserved port as access denied.
            # Any preferred port is optional; the fresh bind still propagates
            # errors if loopback networking itself is unavailable.
            listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        listener.setblocking(False)
        return listener
    except BaseException:
        listener.close()
        raise


def main():
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(description="PropNutz Flight Sync desktop backend")
    parser.add_argument("--data-dir", required=True, help="Dedicated desktop data folder")
    parser.add_argument("--port", type=int, default=0, help="Preferred loopback port, or 0 for any free port")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    token = os.environ.get("FPV_DESKTOP_TOKEN", "")
    if not token.strip():
        parser.error("FPV_DESKTOP_TOKEN must contain a desktop access token")
    os.environ["FPV_AUDIO_DATA_DIR"] = str(Path(args.data_dir).expanduser().resolve())
    enable_child_cleanup()
    hide_child_consoles()

    # Store resolves its data folder at import time. Keep these imports after
    # configuration, including in the frozen executable's minimal entry script.
    from . import store, web
    import uvicorn

    try:
        store.acquire_instance()
    except (OSError, RuntimeError) as error:
        parser.error(str(error))
    for session in store.sessions():
        if session.get("job", {}).get("status") in {"queued", "running"} and not session.get("recovery_required"):
            store.update(session["id"], lambda document: document["job"].update(
                status="interrupted", message="App restarted. Resume the task to reuse saved work."))

    with bind_loopback(args.port) as listener:
        port = listener.getsockname()[1]
        url = f"http://127.0.0.1:{port}"

        class DesktopServer(uvicorn.Server):
            async def startup(self, sockets=None):
                await super().startup(sockets=sockets)
                if self.started and not self.should_exit:
                    print(json.dumps({"event": "ready", "url": url}), flush=True)

        server = DesktopServer(uvicorn.Config(
            DesktopAccess(web.app, token, port), host="127.0.0.1", port=port,
            loop="asyncio", http="h11", ws="none", lifespan="on",
            access_log=False, proxy_headers=False, timeout_graceful_shutdown=5,
        ))

        def request_shutdown():
            server.should_exit = True
            # Cancel background work before Uvicorn waits for active requests.
            # Its normal application-shutdown hook safely repeats this call.
            web.stop_workers()

        def watch_parent():
            try:
                if sys.stdin is not None:
                    for line in sys.stdin:
                        if line.strip() == "shutdown":
                            break
            finally:
                request_shutdown()

        threading.Thread(target=watch_parent, name="desktop-parent", daemon=True).start()
        try:
            server.run(sockets=[listener])
        finally:
            request_shutdown()


if __name__ == "__main__":
    main()
