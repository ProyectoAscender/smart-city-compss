from __future__ import annotations

import os
from pathlib import Path


# GPS origin of the ENU coordinate system per camera area.
# Add a new entry whenever a new city/area is deployed.
_AREA_GPS_REF: dict[tuple[str, str], tuple[float, float]] = {
    ("barcelona", "urgell"): (41.3936, 2.1536),
}


def _gps_ref(city: str, area: str) -> tuple[float, float]:
    return _AREA_GPS_REF.get((city.lower(), area.lower()), (41.3936, 2.1536))


def _load_dotenv(env_path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not env_path.exists():
        return result
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            result[key.strip()] = val.strip().strip('"').strip("'")
    # Simple single-pass variable expansion: ${KEY}
    for k in list(result):
        v = result[k]
        for ref_k, ref_v in result.items():
            v = v.replace(f"${{{ref_k}}}", ref_v)
        result[k] = v
    return result


def load_config() -> dict:
    project_root = Path(__file__).parent.parent

    env = _load_dotenv(project_root / ".env")
    # Visualizer-local overrides (optional)
    env.update(_load_dotenv(Path(__file__).parent / ".env"))
    # OS env has highest priority
    for k in list(env):
        if k in os.environ:
            env[k] = os.environ[k]

    cam_id = env.get("CAM_ID", "0003")
    city = env.get("CITY", "barcelona")
    area = env.get("AREA", "urgell")
    fps = int(env.get("FPS", "25"))

    area_root = project_root / "data_cache" / city / area
    roi_file = env.get("ROI", f"{area.lower()}_{cam_id}.json")
    pmat_file = env.get("PMAT", f"projMat{cam_id}_ACTIVE.txt")

    roi_path = area_root / "roi" / roi_file
    pmat_path = area_root / "pmat" / pmat_file

    ref_lat, ref_lon = _gps_ref(city, area)

    port = int(env.get("VIZ_PORT", "8080"))

    return {
        "cam_id": cam_id,
        "city": city,
        "area": area,
        "fps": fps,
        "roi_path": str(roi_path),
        "pmat_path": str(pmat_path),
        "ref_lat": ref_lat,
        "ref_lon": ref_lon,
        "port": port,
        "project_root": str(project_root),
    }
