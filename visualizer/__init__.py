from __future__ import annotations

import asyncio
import logging
import threading
from typing import Optional

log = logging.getLogger(__name__)

_loop: Optional[asyncio.AbstractEventLoop] = None
_started = False
_cfg_cache = None

# PMAT matrix and ENU origin, handed over once by the main process at
# start() — the visualizer never loads these files itself.
_M = None
_origin = None


def _port_in_use(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def start(host: str = "0.0.0.0", port: int = 8080, M=None, origin=None) -> None:
    """Start the visualizer server in a daemon thread. No-op if already started or port taken.

    `M` (PMAT homography) and `origin` (lat, lon) are the ones already
    loaded by the main process — passed through so the visualizer doesn't
    load these files a second time.
    """
    global _loop, _started, _M, _origin
    if _started:
        return

    if _port_in_use(port):
        log.info("[visualizer] port %d already in use — skipping start", port)
        return

    try:
        import uvicorn  # noqa: F401
        import fastapi  # noqa: F401
    except ImportError as exc:
        log.warning("[visualizer] disabled — missing deps: %s", exc)
        return

    _M, _origin = M, origin
    _started = True
    ready = threading.Event()

    def _run() -> None:
        global _loop
        import uvicorn
        import visualizer.app as m
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        ready.set()
        _loop.run_until_complete(
            uvicorn.Server(uvicorn.Config(m.app, host=host, port=port, log_level="info")).serve()
        )

    threading.Thread(target=_run, daemon=True, name="viz").start()
    if not ready.wait(timeout=5.0):
        log.warning("[visualizer] server did not start within 5 s")


def push_frame(frame_id: int, timestamp: float, objects: list) -> None:
    """Push a processed frame to the visualizer. Thread-safe, non-blocking."""
    if _loop is None:
        return

    import visualizer.app as m
    from visualizer.geo import _enu_to_gps
    cfg = _get_cfg()
    rl, rn = _origin if _origin is not None else (cfg["ref_lat"], cfg["ref_lon"])

    def _safe(v):
        if v is None: return None
        f = float(v)
        return None if f != f else f  # NaN → None

    converted = []
    for o in objects:
        lat, lng = _enu_to_gps(float(o["enu_x"]), float(o["enu_y"]), rl, rn)
        rs = o.get("ref_speed")
        if rs is None:
            ref_speed = None
        elif rs != rs:  # NaN
            ref_speed = "nan"
        else:
            ref_speed = float(rs)

        converted.append({
            "track_id":         int(o["track_id"]),
            "class_id":         int(o["class_id"]),
            "lat":               lat,
            "lng":               lng,
            "speed":             float(o["speed"]) if o.get("speed") is not None else None,
            "poly_type":         str(o.get("poly_type") or ""),
            "state":             o.get("motion_state"),
            "ref_speed":         ref_speed,
            "raw_speed":         _safe(o.get("raw_speed")),
            "checkpoint_speed":  _safe(o.get("checkpoint_speed")),
            "kf_speed":          _safe(o.get("kf_speed")),
        })

    msg = {"type": "frame", "frame_id": frame_id, "ts": float(timestamp), "objects": converted}
    asyncio.run_coroutine_threadsafe(m.broadcast(msg), _loop)


def _get_cfg() -> dict:
    global _cfg_cache
    if _cfg_cache is None:
        from visualizer.config import load_config
        _cfg_cache = load_config()
    return _cfg_cache
