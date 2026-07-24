#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd


TRACKLET_COLUMNS = [
    "cam_id",
    "frame_id",
    "timestamp_raw",
    "event_time",
    "track_id",
    "bbox_x",
    "bbox_y",
    "bbox_w",
    "bbox_h",
    "score",
    "class_id",
    "enu_x",
    "enu_y",
    "speed",
    "semantic_zone",
]
CLASS_LABELS = {
    0: "person",
    1: "car",
    2: "truck",
    3: "bus",
    4: "motorbike",
    5: "bike",
    6: "rider",
}
CHUNK_SIZE = 200_000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Track quality analysis for Smart City tracklets.")
    parser.add_argument("--input-dir", default="runs/exp/20260712")
    parser.add_argument("--road-only", dest="road_only", action="store_true", default=True)
    parser.add_argument("--no-road-only", dest="road_only", action="store_false")
    return parser.parse_args()


def quantile(values: list[float], percentile: int) -> float:
    if not values:
        return float("nan")
    values = sorted(values)
    idx = min(len(values) - 1, max(0, math.ceil((percentile / 100) * len(values)) - 1))
    return values[idx]


def main() -> None:
    args = parse_args()
    input_dir = Path(args.input_dir)
    tracks = {}
    rows_scanned = 0
    candidate_rows = 0

    for path in sorted(input_dir.rglob("tracklets.txt")):
        for chunk in pd.read_csv(
            path,
            header=None,
            names=TRACKLET_COLUMNS,
            usecols=["track_id", "event_time", "score", "class_id", "semantic_zone"],
            chunksize=CHUNK_SIZE,
        ):
            rows_scanned += len(chunk.index)
            chunk["class_id"] = pd.to_numeric(chunk["class_id"], errors="coerce")
            chunk["score"] = pd.to_numeric(chunk["score"], errors="coerce")
            chunk["event_time"] = pd.to_datetime(chunk["event_time"], errors="coerce")
            chunk = chunk.dropna(subset=["track_id", "event_time", "score", "class_id"])
            chunk["class_id"] = chunk["class_id"].astype(int)
            chunk["semantic_zone"] = chunk["semantic_zone"].fillna("None").astype(str)
            chunk = chunk[chunk["class_id"] != 0]
            if args.road_only:
                chunk = chunk[chunk["semantic_zone"] == "road"]
            candidate_rows += len(chunk.index)
            if chunk.empty:
                continue

            chunk = chunk.sort_values("event_time")
            for row in chunk.itertuples(index=False):
                track_id = str(row.track_id)
                event_time = row.event_time.to_pydatetime()
                entry = tracks.setdefault(
                    track_id,
                    {
                        "n": 0,
                        "score_sum": 0.0,
                        "first": event_time,
                        "last": event_time,
                        "classes": Counter(),
                    },
                )
                entry["n"] += 1
                entry["score_sum"] += float(row.score)
                entry["classes"][int(row.class_id)] += 1
                if event_time < entry["first"]:
                    entry["first"] = event_time
                if event_time > entry["last"]:
                    entry["last"] = event_time

    counts = []
    mean_scores = []
    durations = []
    dominant_classes = Counter()
    for entry in tracks.values():
        counts.append(entry["n"])
        mean_scores.append(entry["score_sum"] / entry["n"])
        durations.append((entry["last"] - entry["first"]).total_seconds())
        dominant_classes[entry["classes"].most_common(1)[0][0]] += 1

    print("rows_scanned", rows_scanned)
    print("candidate_rows", candidate_rows)
    print("unique_tracks", len(tracks))
    print(
        "dominant_classes",
        {CLASS_LABELS.get(k, str(k)): v for k, v in dominant_classes.most_common()},
    )
    for percentile in [50, 75, 80, 85, 90, 95, 99]:
        print(f"count_p{percentile}", quantile(counts, percentile))
    for percentile in [50, 75, 80, 85, 90, 95, 99]:
        print(f"mean_score_p{percentile}", round(quantile(mean_scores, percentile), 3))
    for percentile in [50, 75, 80, 85, 90, 95, 99]:
        print(f"duration_s_p{percentile}", round(quantile(durations, percentile), 2))

    print("--- threshold sweep ---")
    for min_count in [1, 2, 3, 5, 8, 10, 15, 20, 30, 50]:
        kept = [entry for entry in tracks.values() if entry["n"] >= min_count]
        print("min_count", min_count, "tracks", len(kept))
    print("--- threshold sweep with score ---")
    for min_count in [5, 10, 15, 20]:
        for min_score in [0.5, 0.6, 0.7]:
            kept = [
                entry
                for entry in tracks.values()
                if entry["n"] >= min_count and (entry["score_sum"] / entry["n"]) >= min_score
            ]
            print("min_count", min_count, "min_score", min_score, "tracks", len(kept))


if __name__ == "__main__":
    main()
