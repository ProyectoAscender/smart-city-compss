import json
import os


def load_exclusion_zones(path):
    """Load exclusion zone rules from JSON. Returns [] if file absent (no filtering)."""
    if not path or not os.path.exists(path):
        return []
    with open(path) as f:
        data = json.load(f)
    zones = data.get("exclusion_zones", [])
    print(f"[exclusions] {len(zones)} zone(s) loaded from {path}")
    return zones


def in_exclusion_zone(tlwh, zones):
    """True if the bbox (tlwh) matches ANY zone (conditions within a zone are ANDed)."""
    for zone in zones:
        if all(_check(tlwh, c) for c in zone.get("conditions", [])):
            return True
    return False


def _coord(tlwh, name):
    x, y, w, h = float(tlwh[0]), float(tlwh[1]), float(tlwh[2]), float(tlwh[3])
    return {
        "x":        x,
        "y":        y,
        "w":        w,
        "h":        h,
        "x_center": x + w / 2,
        "y_center": y + h / 2,
        "x_right":  x + w,
        "y_bottom": y + h,
    }.get(name)


def _check(tlwh, cond):
    val = _coord(tlwh, cond["coord"])
    if val is None:
        return False
    t, op = cond["value"], cond["op"]
    if op == "lt":  return val <  t
    if op == "lte": return val <= t
    if op == "gt":  return val >  t
    if op == "gte": return val >= t
    if op == "eq":  return val == t
    return False
