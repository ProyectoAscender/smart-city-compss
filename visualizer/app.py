from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from . import _M, _origin
from .config import load_config
from .geo import load_polygons

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
log = logging.getLogger(__name__)

cfg      = load_config()
polygons: list          = []
_connections: set[WebSocket] = set()
frame_buffer: deque     = deque(maxlen=500)
map_center: dict        = {"lat": cfg["ref_lat"], "lon": cfg["ref_lon"]}


# ── helpers ───────────────────────────────────────────────────────────────────

def _compute_center(polys: list) -> dict:
    lats = [c["lat"] for p in polys for c in p["coords"]]
    lons = [c["lng"] for p in polys for c in p["coords"]]
    if not lats:
        return {"lat": cfg["ref_lat"], "lon": cfg["ref_lon"]}
    return {"lat": sum(lats) / len(lats), "lon": sum(lons) / len(lons)}


# ── live broadcast ────────────────────────────────────────────────────────────

async def broadcast(msg: dict) -> None:
    frame_buffer.append(msg)
    if not _connections:
        return
    text = json.dumps(msg, ensure_ascii=False)
    results = await asyncio.gather(
        *[ws.send_text(text) for ws in list(_connections)],
        return_exceptions=True,
    )
    dead = {ws for ws, r in zip(list(_connections), results) if isinstance(r, Exception)}
    _connections.difference_update(dead)


# ── lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global polygons

    try:
        polygons = load_polygons(cfg["roi_path"], _M, _origin,
                                 cfg["ref_lat"], cfg["ref_lon"])
        map_center.update(_compute_center(polygons))
        print(f"[viz] lifespan: {len(polygons)} polygons loaded, "
              f"center={map_center['lat']:.5f},{map_center['lon']:.5f}")
    except Exception as exc:
        print(f"[viz] lifespan: polygon load FAILED: {exc}")

    yield


# ── FastAPI app ───────────────────────────────────────────────────────────────

app     = FastAPI(title="Smart City Traffic Visualizer", lifespan=lifespan)
_static = Path(__file__).parent / "static"
if _static.exists():
    app.mount("/static", StaticFiles(directory=str(_static)), name="static")

_html = Path(__file__).parent / "templates" / "index.html"


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(_html.read_text(encoding="utf-8"))


@app.get("/api/config")
async def api_config():
    return {
        "cam_id":   cfg["cam_id"],
        "fps":      cfg["fps"],
        "ref_lat":  map_center["lat"],
        "ref_lon":  map_center["lon"],
        "polygons": polygons,
    }


@app.get("/api/status")
async def api_status():
    return {
        "connections": len(_connections),
        "pmat_path":   cfg["pmat_path"],
    }


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    _connections.add(ws)
    print(f"[viz] WS connected — total connections: {len(_connections)}")
    try:
        await ws.send_text(json.dumps({
            "type":     "init",
            "cam_id":   cfg["cam_id"],
            "fps":      cfg["fps"],
            "ref_lat":  map_center["lat"],
            "ref_lon":  map_center["lon"],
            "polygons": polygons,
        }))
        print("[viz] WS init sent")

        # Replay recently-broadcast live frames so a late-joining client catches up
        for frame in list(frame_buffer):
            await ws.send_text(json.dumps(frame))

        print("[viz] WS entering keepalive loop")
        while True:
            try:
                msg = await asyncio.wait_for(ws.receive_text(), timeout=30.0)
                if msg == '{"type":"ping"}':
                    await ws.send_text('{"type":"pong"}')
            except asyncio.TimeoutError:
                await ws.send_text('{"type":"ping"}')

    except WebSocketDisconnect:
        print("[viz] WS disconnected")
    except Exception as exc:
        print(f"[viz] WS error: {exc}")
        import traceback; traceback.print_exc()
    finally:
        _connections.discard(ws)


if __name__ == "__main__":
    uvicorn.run("visualizer.app:app", host="0.0.0.0", port=cfg["port"], log_level="info")
