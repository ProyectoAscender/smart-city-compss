from __future__ import annotations

import csv as csv_mod
import logging
import math
from pathlib import Path

import numpy as np

from .geo import _load_pmat, _load_origin, _pixel_to_map, _enu_to_gps

log = logging.getLogger(__name__)

# Row layout (udp_handler):
# [0]cam  [1]frame_id  [2]ts_ns  [3]ts_reception_ms  [4]track_id
# [5]x  [6]y  [7]w  [8]h  [9]score  [10]class  [11]enu_e  [12]enu_n  [13]speed  [14]poly_type
#
# Ground point: bottom-center = (x + w/2, y + h)  ← same as t.to_bc()


def find_tracklet_files(
    watch_paths: list[str],
    csv_day: str = "",
    csv_hours: str = "",
) -> list[Path]:
    files: list[Path] = []
    hour_filter = {h.strip().zfill(4) for h in csv_hours.split(",") if h.strip()} if csv_hours else set()

    for wp in watch_paths:
        root = Path(wp)
        if not root.exists():
            continue
        for f in sorted(root.rglob("tracklets.txt")):
            s = f.as_posix()
            if csv_day and csv_day not in s:
                continue
            if hour_filter and not any(f"/{h}/" in s for h in hour_filter):
                continue
            files.append(f)
    return files


def build_frames(files: list[Path], pmat_path: str,
                 ref_lat: float = 0.0, ref_lon: float = 0.0) -> list[dict]:
    """Parse tracklet CSVs → frame dicts using PMAT + GPS origin."""
    try:
        M = _load_pmat(pmat_path)
    except Exception as exc:
        log.error("Cannot load PMAT from %s: %s", pmat_path, exc)
        return []

    origin = _load_origin(pmat_path)
    if origin is not None:
        ref_lat, ref_lon = origin
    else:
        log.warning("origin_coordinates_utm.txt not found — using fallback ref (%.5f, %.5f)",
                    ref_lat, ref_lon)

    frame_map: dict[int, dict] = {}

    for path in files:
        log.info("Reading %s", path)
        try:
            with open(path, buffering=1 << 20) as fh:
                for row in csv_mod.reader(fh):
                    if not row or row[0].startswith("#"):
                        continue
                    try:
                        frame_id  = int(row[1])
                        ts_us     = int(row[3]) * 1000
                        track_id  = int(row[4])
                        class_id  = int(float(row[10]))
                        _spd      = float(row[13])
                        speed     = float(_spd) if math.isfinite(_spd) else None
                        poly_type = (row[14].strip() if len(row) > 14 else "") or "unknown"

                        px = float(row[5]) + float(row[7]) / 2   # x + w/2
                        py = float(row[6]) + float(row[8])        # y + h  (bottom-center)
                        enu = _pixel_to_map(M, np.array([[px, py]]))[0]
                        lat, lng = _enu_to_gps(float(enu[0]), float(enu[1]), ref_lat, ref_lon)

                    except (IndexError, ValueError):
                        continue

                    if frame_id not in frame_map:
                        frame_map[frame_id] = {
                            "type": "frame",
                            "frame_id": frame_id,
                            "ts": ts_us,
                            "objects": [],
                        }
                    frame_map[frame_id]["objects"].append({
                        "track_id": track_id,
                        "lat":      lat,
                        "lng":      lng,
                        "class_id": class_id,
                        "speed":    speed,
                        "poly_type": poly_type,
                    })
        except OSError as exc:
            log.warning("Cannot read %s: %s", path, exc)

    return sorted(frame_map.values(), key=lambda f: f["frame_id"])
