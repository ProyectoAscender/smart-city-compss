from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np


def _load_pmat(pmat_path: str) -> np.ndarray:
    return np.loadtxt(pmat_path, delimiter=" ", usecols=range(3))


def _pixel_to_map(M: np.ndarray, pixels: np.ndarray) -> np.ndarray:
    """Homography projection — identical to ViewTransformer.pixel_to_map."""
    if pixels.ndim == 1:
        pixels = pixels.reshape(1, 2)
    pts = np.concatenate([pixels, np.ones((len(pixels), 1))], axis=1)
    mapped = M @ pts.T
    return (mapped[:2] / mapped[2]).T


def _load_origin(pmat_path: str) -> tuple[float, float] | None:
    """Read origin_coordinates_utm.txt (lat, lon) from the PMAT folder.
    Returns None if the file does not exist.
    """
    p = Path(pmat_path).parent / "origin_coordinates_utm.txt"
    if not p.exists():
        return None
    tokens = p.read_text().replace(",", " ").split()
    return float(tokens[0]), float(tokens[1])


def _enu_to_gps(e: float, n: float, ref_lat: float, ref_lon: float) -> tuple[float, float]:
    """ENU metres → WGS-84 using flat-earth approx (< 1 mm error at < 1 km)."""
    R = 6_378_137.0
    lat = ref_lat + math.degrees(n / R)
    lon = ref_lon + math.degrees(e / (R * math.cos(math.radians(ref_lat))))
    return lat, lon


def load_polygons(roi_path: str, pmat_path: str,
                  ref_lat: float = 0.0, ref_lon: float = 0.0) -> list[dict]:
    """Load VIA-format ROI JSON and project pixel vertices → GPS via PMAT."""
    M = _load_pmat(pmat_path)
    origin = _load_origin(pmat_path)
    if origin is not None:
        ref_lat, ref_lon = origin

    with open(roi_path) as f:
        data = json.load(f)

    polygons: list[dict] = []
    for img_data in data["_via_img_metadata"].values():
        for region in img_data["regions"]:
            shape = region["shape_attributes"]
            if shape["name"] != "polygon":
                continue

            poly_type = region["region_attributes"].get("type", "unknown")
            xs = np.asarray(shape["all_points_x"], dtype=float)
            ys = np.asarray(shape["all_points_y"], dtype=float)

            enu = _pixel_to_map(M, np.column_stack([xs, ys]))
            coords = [{"lat": lat, "lng": lng}
                      for e, n in enu
                      for lat, lng in [_enu_to_gps(float(e), float(n), ref_lat, ref_lon)]]

            polygons.append({"type": poly_type, "coords": coords})

    return polygons
