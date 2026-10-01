"""Phone dashboard on LAN (HANDOFF section 8.4): live stats + thumbnail,
pause/stop behind a PIN. Off by default, binds to the local network only.

``create_app`` returns a plain FastAPI app (testable with
``fastapi.testclient.TestClient`` - no real socket needed); ``LanDashboardServer``
is the thin uvicorn wrapper that actually binds a port, used only when the
integration is enabled for real.
"""

from __future__ import annotations

import ipaddress
import logging
import secrets
import threading
from collections.abc import Callable

log = logging.getLogger(__name__)

# RFC 1918 / loopback / link-local - anything else is not "LAN only".
_PRIVATE_NETS = [ipaddress.ip_network(n) for n in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8", "169.254.0.0/16",
)]


def is_lan_only_bind(host: str) -> bool:
    """True if binding to ``host`` can only ever be reached from the local network.

    ``0.0.0.0``/``::`` bind every interface, which is still LAN-only *unless*
    something outside this app (a router's port-forward) exposes it further -
    that's outside what this process can check, so it's accepted here; a
    bind to a known-public address is rejected outright.
    """
    if host in ("0.0.0.0", "::", "localhost", "127.0.0.1"):
        return True
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(addr in net for net in _PRIVATE_NETS)


def ensure_pin(pin: str) -> str:
    """A dashboard with real controls must never run with no PIN - generate one if empty."""
    if pin and pin.strip():
        return pin.strip()
    generated = f"{secrets.randbelow(900000) + 100000}"
    log.warning("LAN dashboard enabled with no PIN set - generated one: %s", generated)
    return generated


def create_app(pin: str, get_status: Callable[[], dict], on_pause: Callable[[], None],
               on_resume: Callable[[], None], on_stop: Callable[[], None]):
    from fastapi import Depends, FastAPI, Header, HTTPException

    pin = ensure_pin(pin)
    app = FastAPI(title="Warden LAN Dashboard")

    def check_pin(x_warden_pin: str | None = Header(default=None)) -> None:
        if x_warden_pin != pin:
            raise HTTPException(status_code=401, detail="bad pin")

    @app.get("/api/status")
    def status():
        return get_status()

    @app.post("/api/pause", dependencies=[Depends(check_pin)])
    def pause():
        on_pause()
        return {"ok": True}

    @app.post("/api/resume", dependencies=[Depends(check_pin)])
    def resume():
        on_resume()
        return {"ok": True}

    @app.post("/api/stop", dependencies=[Depends(check_pin)])
    def stop():
        on_stop()
        return {"ok": True}

    return app


class LanDashboardServer:
    def __init__(self, host: str, port: int, pin: str, get_status, on_pause, on_resume, on_stop):
        if not is_lan_only_bind(host):
            raise ValueError(f"refusing to bind LAN dashboard to a non-local address: {host}")
        self.host = host
        self.port = port
        self.pin = ensure_pin(pin)
        self.app = create_app(self.pin, get_status, on_pause, on_resume, on_stop)
        self._server = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        import uvicorn

        config = uvicorn.Config(self.app, host=self.host, port=self.port, log_level="warning")
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, name="warden-lan-dashboard", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None
