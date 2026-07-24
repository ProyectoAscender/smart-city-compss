#!/usr/bin/env python3
from __future__ import annotations

import glob
import math
import threading
from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import dask.dataframe as dd
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

VEHICLE_CLASS_LABELS = OrderedDict(
    [
        (1, "car"),
        (2, "truck"),
        (3, "bus"),
        (4, "motorbike"),
        (5, "bike"),
        (6, "rider"),
    ]
)

INTERVAL_OPTIONS = OrderedDict(
    [
        ("1 min", "1min"),
        ("10 min", "10min"),
        ("1 h", "1h"),
    ]
)

METRIC_OPTIONS = OrderedDict(
    [
        ("Average speed", "mean"),
        ("Speed sum", "sum"),
    ]
)

DEFAULT_MAX_POINTS = 4_000


@dataclass(frozen=True)
class Inventory:
    root: Path
    file_count: int
    cameras: tuple[str, ...]
    first_date: str | None
    last_date: str | None
    sample_files: tuple[str, ...]


class LongSeriesStore:
    def __init__(self, data_root: str | Path, blocksize: str = "64MB") -> None:
        self.data_root = Path(data_root).expanduser().resolve()
        self.blocksize = blocksize
        self._inventory: Inventory | None = None
        self._ddf: dd.DataFrame | None = None
        self._agg_cache: dict[tuple[str, str, tuple[str, ...]], pd.DataFrame] = {}
        self._lock = threading.RLock()

    @property
    def file_glob(self) -> str:
        return str(self.data_root / "*" / "*" / "*" / "tracklets.txt")

    def clear_caches(self) -> None:
        with self._lock:
            self._inventory = None
            self._ddf = None
            self._agg_cache.clear()

    def inventory(self) -> Inventory:
        with self._lock:
            if self._inventory is not None:
                return self._inventory

            paths = sorted(Path(path) for path in glob.glob(self.file_glob))
            cameras = tuple(sorted({path.parts[-4] for path in paths}))
            dates = sorted({path.parts[-3] for path in paths})
            sample_files = tuple(str(path) for path in paths[:3])
            self._inventory = Inventory(
                root=self.data_root,
                file_count=len(paths),
                cameras=cameras,
                first_date=dates[0] if dates else None,
                last_date=dates[-1] if dates else None,
                sample_files=sample_files,
            )
            return self._inventory

    def available_vehicle_types(self) -> tuple[str, ...]:
        return tuple(VEHICLE_CLASS_LABELS.values())

    def aggregate(
        self,
        interval: str,
        metric: str,
        cameras: Iterable[str] | None = None,
    ) -> pd.DataFrame:
        camera_key = tuple(sorted(cameras or ()))
        cache_key = (interval, metric, camera_key)
        with self._lock:
            if cache_key in self._agg_cache:
                return self._agg_cache[cache_key].copy()

        frame = self._build_ddf()
        if camera_key:
            frame = frame[frame["camera_id"].isin(list(camera_key))]

        grouped = (
            frame.assign(time_bucket=frame["event_time"].dt.floor(interval))
            .groupby(["time_bucket", "vehicle_type"])["speed"]
            .agg(metric)
            .reset_index()
        )

        result = grouped.compute()
        if result.empty:
            result = pd.DataFrame(columns=["timestamp", "vehicle_type", "value"])
        else:
            result = result.rename(
                columns={"time_bucket": "timestamp", "speed": "value"}
            ).sort_values(["vehicle_type", "timestamp"])
            result["timestamp"] = pd.to_datetime(result["timestamp"], errors="coerce")
            result["value"] = pd.to_numeric(result["value"], errors="coerce")
            result = result.dropna(subset=["timestamp", "value"])
            result["vehicle_type"] = result["vehicle_type"].astype(str)

        with self._lock:
            self._agg_cache[cache_key] = result
        return result.copy()

    def slice_for_view(
        self,
        aggregate_frame: pd.DataFrame,
        start: pd.Timestamp | None,
        end: pd.Timestamp | None,
        max_points: int = DEFAULT_MAX_POINTS,
    ) -> dict[str, pd.DataFrame]:
        if aggregate_frame.empty:
            return {label: pd.DataFrame(columns=["timestamp", "value"]) for label in self.available_vehicle_types()}

        visible = aggregate_frame
        if start is not None:
            visible = visible[visible["timestamp"] >= start]
        if end is not None:
            visible = visible[visible["timestamp"] <= end]
        if visible.empty:
            visible = aggregate_frame

        result: dict[str, pd.DataFrame] = {}
        for label in self.available_vehicle_types():
            series = visible[visible["vehicle_type"] == label][["timestamp", "value"]].copy()
            result[label] = self._decimate_series(series, max_points=max_points)
        return result

    def _build_ddf(self) -> dd.DataFrame:
        with self._lock:
            if self._ddf is not None:
                return self._ddf

            inventory = self.inventory()
            if inventory.file_count == 0:
                raise FileNotFoundError(
                    f"No tracklets.txt files found under {self.data_root}"
                )

            frame = dd.read_csv(
                self.file_glob,
                header=None,
                names=TRACKLET_COLUMNS,
                usecols=["event_time", "speed", "class_id"],
                dtype={
                    "event_time": "object",
                    "speed": "float64",
                    "class_id": "float64",
                },
                include_path_column="source_path",
                assume_missing=True,
                blocksize=self.blocksize,
                on_bad_lines="skip",
            )
            frame["event_time"] = dd.to_datetime(frame["event_time"], errors="coerce")
            frame["speed"] = dd.to_numeric(frame["speed"], errors="coerce")
            frame["class_id"] = dd.to_numeric(frame["class_id"], errors="coerce")
            frame = frame.dropna(subset=["event_time", "speed", "class_id"])
            frame["class_id"] = frame["class_id"].astype("int16")
            frame = frame[frame["class_id"].isin(list(VEHICLE_CLASS_LABELS))]
            frame = frame[frame["speed"] >= 0]
            frame["vehicle_type"] = frame["class_id"].map(
                VEHICLE_CLASS_LABELS,
                meta=("vehicle_type", "object"),
            )
            frame["camera_id"] = frame["source_path"].str.extract(
                r"/([^/]+)/\d{8}/\d{4}/tracklets\.txt$",
                expand=False,
            )
            frame = frame[["event_time", "speed", "vehicle_type", "camera_id"]]
            self._ddf = frame
            return self._ddf

    @staticmethod
    def _decimate_series(
        series: pd.DataFrame,
        max_points: int = DEFAULT_MAX_POINTS,
    ) -> pd.DataFrame:
        if series.empty or len(series.index) <= max_points:
            return series

        step = math.ceil(len(series.index) / max_points)
        return series.iloc[::step].reset_index(drop=True)


@lru_cache(maxsize=8)
def get_store(data_root: str) -> LongSeriesStore:
    return LongSeriesStore(data_root=data_root)
