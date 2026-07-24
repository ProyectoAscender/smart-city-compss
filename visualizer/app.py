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

from .config import load_config
from .geo import load_polygons
from .reader import find_tracklet_files, build_frames

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
log = logging.getLogger(__name__)

cfg      = load_config()
polygons: list          = []
_frames:  list[dict]    = []
_connections: set[WebSocket] = set()
frame_buffer: deque     = deque(maxlen=500)
map_center: dict        = {"lat": cfg["ref_lat"], "lon": cfg["ref_lon"]}

# Created inside lifespan so it belongs to uvicorn's event loop (avoids
# "Future attached to a different loop" on Python 3.8)
_frames_ready: asyncio.Event | None = None


# ── helpers ───────────────────────────────────────────────────────────────────

def _compute_center(polys: list) -> dict:
    lats = [c["lat"] for p in polys for c in p["coords"]]
    lons = [c["lng"] for p in polys for c in p["coords"]]
    if not lats:
        return {"lat": cfg["ref_lat"], "lon": cfg["ref_lon"]}
    return {"lat": sum(lats) / len(lats), "lon": sum(lons) / len(lons)}


async def _send_frames(ws: WebSocket) -> None:
    """Stream all pre-loaded frames to one client in batches of 100."""
    BATCH = 100
    total = len(_frames)
    print(f"[viz] _send_frames: sending {total} frames in {(total-1)//BATCH+1} batches")
    for i in range(0, total, BATCH):
        try:
            await ws.send_text(json.dumps({"type": "batch", "frames": _frames[i:i + BATCH]}))
        except Exception as exc:
            print(f"[viz] _send_frames: error at batch {i//BATCH}: {exc}")
            return
        await asyncio.sleep(0)
    print(f"[viz] _send_frames: done")


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


# ── startup frame loader ──────────────────────────────────────────────────────

async def _load_frames() -> None:
    global _frames
    print("[viz] _load_frames: start")
    try:
        files = find_tracklet_files(
            cfg["watch_paths"],
            cfg.get("csv_day", ""),
            cfg.get("csv_hours", ""),
        )
        print(f"[viz] _load_frames: found {len(files)} file(s): {[str(f) for f in files]}")
        if not files:
            log.warning("No tracklet files found")
            return

        loop = asyncio.get_running_loop()
        print("[viz] _load_frames: calling build_frames in executor…")
        _frames = await loop.run_in_executor(
            None, build_frames, files, cfg["pmat_path"], cfg["ref_lat"], cfg["ref_lon"]
        )
        print(f"[viz] _load_frames: {len(_frames)} frames ready. "
              f"First={_frames[0]['frame_id'] if _frames else 'N/A'}, "
              f"Last={_frames[-1]['frame_id'] if _frames else 'N/A'}")
        if _frames:
            obj = _frames[0]['objects'][0] if _frames[0]['objects'] else None
            print(f"[viz] _load_frames: sample obj={obj}")
    except Exception as exc:
        print(f"[viz] _load_frames: EXCEPTION: {exc}")
        import traceback; traceback.print_exc()
    finally:
        print("[viz] _load_frames: setting _frames_ready event")
        if _frames_ready is not None:
            _frames_ready.set()


# ── lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global polygons, _frames_ready
    # Create Event here — guarantees it belongs to uvicorn's event loop
    _frames_ready = asyncio.Event()
    print(f"[viz] lifespan: Event created, loop={asyncio.get_running_loop()}")

    try:
        polygons = load_polygons(cfg["roi_path"], cfg["pmat_path"],
                                 cfg["ref_lat"], cfg["ref_lon"])
        map_center.update(_compute_center(polygons))
        print(f"[viz] lifespan: {len(polygons)} polygons loaded, "
              f"center={map_center['lat']:.5f},{map_center['lon']:.5f}")
    except Exception as exc:
        print(f"[viz] lifespan: polygon load FAILED: {exc}")

    task = asyncio.create_task(_load_frames())
    yield
    task.cancel()


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
        "frames_loaded": len(_frames),
        "frames_ready":  _frames_ready.is_set() if _frames_ready else False,
        "connections":   len(_connections),
        "pmat_path":     cfg["pmat_path"],
        "csv_day":       cfg.get("csv_day", ""),
        "csv_hours":     cfg.get("csv_hours", ""),
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

        # Wait for frames; send a ping every 10 s so the browser doesn't close
        # the connection while build_frames is running
        while _frames_ready is not None and not _frames_ready.is_set():
            print("[viz] WS waiting for frames (ping keepalive)…")
            try:
                await asyncio.wait_for(_frames_ready.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                await ws.send_text('{"type":"ping"}')

        print(f"[viz] WS frames ready — sending {len(_frames)} frames")
        await _send_frames(ws)

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
