#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing im                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  port Iterable
from urllib.parse import urlparse

import pandas as pd
from bokeh.embed import file_html
from bokeh.layouts import column
from bokeh.models import (
    ColumnDataSource,
    DataTable,
    Div,
    HoverTool,
    NumeralTickFormatter,
    TableColumn,
)
from bokeh.palettes import Category10
from bokeh.plotting import figure
from bokeh.resources import CDN


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
PERSON_CLASS_ID = 0
CHUNK_SIZE = 200_000


@dataclass
class TrackSummary:
    track_id: str
    first_seen: datetime
    first_road: datetime | None
    last_seen: datetime
    first_seen_raw_us: int
    first_road_raw_us: int | None
    total_rows: int
    road_rows: int
    mean_score: float
    dominant_class_id: int


@dataclass
class ClassStat:
    class_id: int
    label: str
    total_tracks: int
    qualified_tracks: int
    pass_rate: float
    median_frames: float
    mean_duration_s: float
    median_score: float
    short_frac: float


@dataclass
class AnalyticsResult:
    minute_counts: pd.DataFrame
    hourly_counts: pd.DataFrame
    class_minute_counts: pd.DataFrame
    person_presence: pd.DataFrame
    class_stats: list[ClassStat]
    qualified_tracks: int
    files_scanned: int
    rows_scanned: int
    candidate_rows: int
    source_dir: Path
    road_only: bool
    min_track_frames: int
    min_mean_score: float
    dominant_classes: Counter
    video_start: datetime | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Serve a Smart City traffic dashboard based on filtered unique tracklets."
    )
    parser.add_argument(
        "--input-dir",
        default="runs/exp/20260712",
        help="Directory containing tracklets.txt files.",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind the HTTP server.")
    parser.add_argument("--port", type=int, default=8090, help="Port to bind the HTTP server.")
    parser.add_argument(
        "--title",
        default="Smart City Analytics",
        help="Page title shown in the browser.",
    )
    parser.add_argument(
        "--min-track-frames",
        type=int,
        default=10,
        help="Minimum number of qualifying rows for a track to count.",
    )
    parser.add_argument(
        "--min-mean-score",
        type=float,
        default=0.6,
        help="Minimum average detection score for a track to count.",
    )
    parser.add_argument(
        "--video-start-time",
        default=None,
        help=(
            "Real-world start time of the video, used to correct the dashboard's timeline. "
            "The CSV's own event_time column is unreliable; this value is combined with the "
            "elapsed time between frames (timestamp_raw, microseconds) instead. Accepts a full "
            "timestamp ('2026-07-12 07:00:00') or a bare time of day ('07:00'), in which case the "
            "date is inferred from the earliest event_time found in the dataset."
        ),
    )
    return parser.parse_args()


def resolve_video_start(video_start_arg: str | None, reference_date: datetime | None) -> datetime | None:
    if not video_start_arg:
        return None
    parsed = pd.to_datetime(video_start_arg).to_pydatetime()
    has_explicit_date = re.search(r"\d{4}", video_start_arg) is not None
    if not has_explicit_date and reference_date is not None:
        parsed = parsed.replace(year=reference_date.year, month=reference_date.month, day=reference_date.day)
    return parsed


def iter_tracklet_files(input_dir: Path) -> Iterable[Path]:
    return sorted(input_dir.rglob("tracklets.txt"))


def load_track_summaries(
    input_dir: Path, road_only: bool
) -> tuple[list[TrackSummary], int, int, int, int | None, datetime | None]:
    track_rows = defaultdict(int)
    track_score_sum = defaultdict(float)
    track_first_seen: dict[str, datetime] = {}
    track_last_seen: dict[str, datetime] = {}
    track_first_road: dict[str, datetime | None] = defaultdict(lambda: None)
    track_first_seen_raw: dict[str, int] = {}
    track_first_road_raw: dict[str, int | None] = defaultdict(lambda: None)
    track_classes: dict[str, Counter] = defaultdict(Counter)
    rows_scanned = 0
    candidate_rows = 0
    files_scanned = 0
    global_min_raw: int | None = None
    global_min_event_time: datetime | None = None

    for tracklet_path in iter_tracklet_files(input_dir):
        files_scanned += 1
        for chunk in pd.read_csv(
            tracklet_path,
            header=None,
            names=TRACKLET_COLUMNS,
            usecols=["track_id", "timestamp_raw", "event_time", "score", "class_id", "semantic_zone"],
            chunksize=CHUNK_SIZE,
        ):
            rows_scanned += len(chunk.index)
            chunk["class_id"] = pd.to_numeric(chunk["class_id"], errors="coerce")
            chunk["score"] = pd.to_numeric(chunk["score"], errors="coerce")
            chunk["timestamp_raw"] = pd.to_numeric(chunk["timestamp_raw"], errors="coerce")
            chunk["event_time"] = pd.to_datetime(chunk["event_time"], errors="coerce")
            chunk = chunk.dropna(subset=["track_id", "timestamp_raw", "event_time", "score", "class_id"])
            chunk["class_id"] = chunk["class_id"].astype(int)
            chunk["timestamp_raw"] = chunk["timestamp_raw"].astype("int64")
            chunk["semantic_zone"] = chunk["semantic_zone"].fillna("None").astype(str)
            chunk = chunk[chunk["class_id"] != PERSON_CLASS_ID]
            if road_only:
                chunk = chunk[chunk["semantic_zone"] == "road"]
            candidate_rows += len(chunk.index)
            if chunk.empty:
                continue

            chunk_min_raw = int(chunk["timestamp_raw"].min())
            global_min_raw = chunk_min_raw if global_min_raw is None else min(global_min_raw, chunk_min_raw)
            chunk_min_event_time = chunk["event_time"].min().to_pydatetime()
            global_min_event_time = (
                chunk_min_event_time
                if global_min_event_time is None
                else min(global_min_event_time, chunk_min_event_time)
            )

            chunk = chunk.sort_values("event_time")
            for row in chunk.itertuples(index=False):
                track_id = str(row.track_id)
                event_time = row.event_time.to_pydatetime()
                raw_us = int(row.timestamp_raw)
                track_rows[track_id] += 1
                track_score_sum[track_id] += float(row.score)
                track_classes[track_id][int(row.class_id)] += 1

                if track_id not in track_first_seen or event_time < track_first_seen[track_id]:
                    track_first_seen[track_id] = event_time
                    track_first_seen_raw[track_id] = raw_us
                if track_id not in track_last_seen or event_time > track_last_seen[track_id]:
                    track_last_seen[track_id] = event_time
                if row.semantic_zone == "road":
                    first_road = track_first_road[track_id]
                    if first_road is None or event_time < first_road:
                        track_first_road[track_id] = event_time
                        track_first_road_raw[track_id] = raw_us

    summaries: list[TrackSummary] = []
    for track_id, total_rows in track_rows.items():
        summaries.append(
            TrackSummary(
                track_id=track_id,
                first_seen=track_first_seen[track_id],
                first_road=track_first_road[track_id],
                last_seen=track_last_seen[track_id],
                first_seen_raw_us=track_first_seen_raw[track_id],
                first_road_raw_us=track_first_road_raw[track_id],
                total_rows=total_rows,
                road_rows=total_rows if road_only else total_rows,
                mean_score=track_score_sum[track_id] / total_rows,
                dominant_class_id=track_classes[track_id].most_common(1)[0][0],
            )
        )

    return summaries, files_scanned, rows_scanned, candidate_rows, global_min_raw, global_min_event_time


def compute_person_presence(
    input_dir: Path,
    global_min_raw: int | None,
    video_start: datetime | None,
) -> pd.DataFrame:
    """Presence-based person metric, immune to track-id fragmentation: for each
    10-minute bucket, sum person detection rows across all frames and divide by
    the number of distinct frame_id values observed in that bucket (any class)."""
    person_bucket_rows: Counter = Counter()
    frame_buckets: dict[datetime, set] = defaultdict(set)

    def bucket_of(raw_us: int) -> datetime | None:
        if global_min_raw is None or video_start is None:
            return None
        bucket_time = video_start + timedelta(microseconds=int(raw_us) - global_min_raw)
        minute = bucket_time.replace(second=0, microsecond=0)
        return minute.replace(minute=(minute.minute // 10) * 10)

    for tracklet_path in iter_tracklet_files(input_dir):
        for chunk in pd.read_csv(
            tracklet_path,
            header=None,
            names=TRACKLET_COLUMNS,
            usecols=["frame_id", "timestamp_raw", "class_id"],
            chunksize=CHUNK_SIZE,
        ):
            chunk["timestamp_raw"] = pd.to_numeric(chunk["timestamp_raw"], errors="coerce")
            chunk["class_id"] = pd.to_numeric(chunk["class_id"], errors="coerce")
            chunk = chunk.dropna(subset=["frame_id", "timestamp_raw"])
            chunk["timestamp_raw"] = chunk["timestamp_raw"].astype("int64")
            for row in chunk.itertuples(index=False):
                ten_minute = bucket_of(row.timestamp_raw)
                if ten_minute is None:
                    continue
                frame_buckets[ten_minute].add(row.frame_id)
                if row.class_id == PERSON_CLASS_ID:
                    person_bucket_rows[ten_minute] += 1

    rows = []
    for minute in sorted(frame_buckets):
        frame_count = len(frame_buckets[minute])
        person_rows = person_bucket_rows.get(minute, 0)
        avg_per_frame = person_rows / frame_count if frame_count else float("nan")
        rows.append((minute, person_rows, frame_count, avg_per_frame))

    return pd.DataFrame(rows, columns=["minute", "person_rows", "frame_count", "avg_per_frame"])


def load_vehicle_counts(
    input_dir: Path,
    road_only: bool,
    min_track_frames: int,
    min_mean_score: float,
    video_start_arg: str | None = None,
) -> AnalyticsResult:
    summaries, files_scanned, rows_scanned, candidate_rows, global_min_raw, global_min_event_time = (
        load_track_summaries(input_dir, road_only)
    )
    video_start = resolve_video_start(video_start_arg, global_min_event_time)
    person_presence = compute_person_presence(input_dir, global_min_raw, video_start)
    minute_counter: Counter = Counter()
    hour_counter: Counter = Counter()
    class_minute_counter: Counter = Counter()
    dominant_classes: Counter = Counter()

    qualified = [
        track
        for track in summaries
        if (track.first_road is not None or not road_only)
        and track.total_rows >= min_track_frames
        and track.mean_score >= min_mean_score
    ]
    qualified_ids = {track.track_id for track in qualified}

    for track in qualified:
        if video_start is not None and global_min_raw is not None:
            raw_us = track.first_road_raw_us if road_only else track.first_seen_raw_us
            bucket_time = video_start + timedelta(microseconds=raw_us - global_min_raw)
        else:
            bucket_time = track.first_road if road_only else track.first_seen
        minute = bucket_time.replace(second=0, microsecond=0)
        minute_counter[minute] += 1
        hour_counter[bucket_time.replace(minute=0, second=0, microsecond=0)] += 1
        ten_minute = minute.replace(minute=(minute.minute // 10) * 10)
        class_minute_counter[(ten_minute, track.dominant_class_id)] += 1
        dominant_classes[track.dominant_class_id] += 1

    minute_counts = (
        pd.DataFrame(
            sorted(minute_counter.items()),
            columns=["minute", "count"],
        )
        if minute_counter
        else pd.DataFrame(columns=["minute", "count"])
    )
    hourly_counts = (
        pd.DataFrame(
            sorted(hour_counter.items()),
            columns=["hour", "count"],
        )
        if hour_counter
        else pd.DataFrame(columns=["hour", "count"])
    )
    class_minute_counts = (
        pd.DataFrame(
            [(minute, class_id, count) for (minute, class_id), count in sorted(class_minute_counter.items())],
            columns=["minute", "class_id", "count"],
        )
        if class_minute_counter
        else pd.DataFrame(columns=["minute", "class_id", "count"])
    )

    by_class: dict[int, list[TrackSummary]] = defaultdict(list)
    for track in summaries:
        by_class[track.dominant_class_id].append(track)

    class_stats: list[ClassStat] = []
    short_window = min_track_frames + 5
    for class_id, tracks in sorted(by_class.items()):
        class_qualified = [track for track in tracks if track.track_id in qualified_ids]
        total_tracks = len(tracks)
        n_qualified = len(class_qualified)
        if n_qualified == 0:
            continue
        frames = pd.Series([track.total_rows for track in class_qualified])
        durations = pd.Series(
            [(track.last_seen - track.first_seen).total_seconds() for track in class_qualified]
        )
        scores = pd.Series([track.mean_score for track in class_qualified])
        short_count = sum(1 for f in frames if min_track_frames <= f <= short_window)
        class_stats.append(
            ClassStat(
                class_id=class_id,
                label=CLASS_LABELS.get(class_id, str(class_id)),
                total_tracks=total_tracks,
                qualified_tracks=n_qualified,
                pass_rate=n_qualified / total_tracks if total_tracks else 0.0,
                median_frames=float(frames.median()),
                mean_duration_s=float(durations.mean()),
                median_score=float(scores.median()),
                short_frac=short_count / n_qualified,
            )
        )
    class_stats.sort(key=lambda stat: stat.qualified_tracks, reverse=True)

    return AnalyticsResult(
        minute_counts=minute_counts,
        hourly_counts=hourly_counts,
        class_minute_counts=class_minute_counts,
        person_presence=person_presence,
        class_stats=class_stats,
        qualified_tracks=len(qualified),
        files_scanned=files_scanned,
        rows_scanned=rows_scanned,
        candidate_rows=candidate_rows,
        source_dir=input_dir,
        road_only=road_only,
        min_track_frames=min_track_frames,
        min_mean_score=min_mean_score,
        dominant_classes=dominant_classes,
        video_start=video_start,
    )


def build_dashboard(result: AnalyticsResult, title: str):
    if result.minute_counts.empty:
        minute_plot = figure(
            title="No qualifying tracks found",
            x_axis_type="datetime",
            sizing_mode="stretch_width",
            height=420,
            toolbar_location=None,
        )
        minute_plot.text(x=[], y=[], text=[])
        hourly_plot = None
    else:
        minute_source = ColumnDataSource(result.minute_counts)
        minute_plot = figure(
            title="Qualified Unique Tracks by Minute",
            x_axis_type="datetime",
            sizing_mode="stretch_width",
            height=470,
            tools="pan,wheel_zoom,box_zoom,reset,save",
            active_scroll="wheel_zoom",
        )
        minute_plot.line(
            x="minute",
            y="count",
            source=minute_source,
            line_width=3,
            color="#0f766e",
            alpha=0.92,
        )
        minute_plot.circle(
            x="minute",
            y="count",
            source=minute_source,
            size=6,
            color="#f59e0b",
            line_color="#78350f",
            line_width=1,
        )
        minute_plot.add_tools(
            HoverTool(
                tooltips=[
                    ("Minute", "@minute{%F %H:%M}"),
                    ("Qualified tracks", "@count{0,0}"),
                ],
                formatters={"@minute": "datetime"},
                mode="vline",
            )
        )
        minute_plot.xaxis.axis_label = "Minute"
        minute_plot.yaxis.axis_label = "Qualified unique tracks"
        minute_plot.yaxis.formatter = NumeralTickFormatter(format="0,0")
        minute_plot.grid.grid_line_alpha = 0.25
        minute_plot.toolbar.logo = None

        hourly_source = ColumnDataSource(result.hourly_counts)
        hourly_plot = figure(
            title="Hourly Summary",
            x_axis_type="datetime",
            sizing_mode="stretch_width",
            height=290,
            tools="xpan,reset,save",
            toolbar_location="right",
        )
        hourly_plot.vbar(
            x="hour",
            top="count",
            source=hourly_source,
            width=45 * 60 * 1000,
            fill_color="#14b8a6",
            line_color="#0f766e",
            fill_alpha=0.85,
        )
        hourly_plot.add_tools(
            HoverTool(
                tooltips=[
                    ("Hour", "@hour{%F %H:%M}"),
                    ("Qualified tracks", "@count{0,0}"),
                ],
                formatters={"@hour": "datetime"},
            )
        )
        hourly_plot.xaxis.axis_label = "Hour"
        hourly_plot.yaxis.axis_label = "Qualified unique tracks"
        hourly_plot.yaxis.formatter = NumeralTickFormatter(format="0,0")
        hourly_plot.grid.grid_line_alpha = 0.22
        hourly_plot.toolbar.logo = None

    class_line_plot = None
    if not result.class_minute_counts.empty:
        pivot = result.class_minute_counts.pivot_table(
            index="minute", columns="class_id", values="count", fill_value=0
        ).sort_index()
        class_line_plot = figure(
            title="Qualified Unique Tracks Summed per 10-Minute Interval — per Class",
            x_axis_type="datetime",
            sizing_mode="stretch_width",
            height=620,
            tools="pan,wheel_zoom,box_zoom,reset,save",
            active_scroll="wheel_zoom",
        )
        palette = Category10[10]
        for i, class_id in enumerate(pivot.columns):
            label = CLASS_LABELS.get(class_id, str(class_id))
            color = palette[i % len(palette)]
            class_source = ColumnDataSource(data=dict(minute=pivot.index, count=pivot[class_id]))
            class_line_plot.line(
                x="minute",
                y="count",
                source=class_source,
                line_width=2.5,
                color=color,
                alpha=0.9,
                legend_label=label,
            )
            class_line_plot.circle(
                x="minute",
                y="count",
                source=class_source,
                size=4,
                color=color,
                alpha=0.7,
                legend_label=label,
            )
        class_line_plot.add_tools(
            HoverTool(
                tooltips=[
                    ("Interval start", "@minute{%F %H:%M}"),
                    ("Qualified tracks (sum over 10 min)", "@count{0,0}"),
                ],
                formatters={"@minute": "datetime"},
                mode="mouse",
            )
        )
        class_line_plot.xaxis.axis_label = "10-minute interval (start time)"
        class_line_plot.yaxis.axis_label = "Qualified unique tracks (sum per 10 min)"
        class_line_plot.yaxis.formatter = NumeralTickFormatter(format="0,0")
        class_line_plot.y_range.start = 0
        class_line_plot.grid.grid_line_alpha = 0.2
        class_line_plot.toolbar.logo = None
        class_line_plot.legend.location = "top_left"
        class_line_plot.legend.click_policy = "hide"

    person_plot = None
    if not result.person_presence.empty:
        person_source = ColumnDataSource(result.person_presence)
        person_plot = figure(
            title="Person Presence per 10-Minute Interval (avg. persons per frame)",
            x_axis_type="datetime",
            sizing_mode="stretch_width",
            height=360,
            tools="pan,wheel_zoom,box_zoom,reset,save",
            active_scroll="wheel_zoom",
        )
        person_plot.line(
            x="minute",
            y="avg_per_frame",
            source=person_source,
            line_width=2.5,
            color="#7c3aed",
            alpha=0.9,
        )
        person_plot.circle(
            x="minute",
            y="avg_per_frame",
            source=person_source,
            size=5,
            color="#7c3aed",
            alpha=0.7,
        )
        person_plot.add_tools(
            HoverTool(
                tooltips=[
                    ("Interval start", "@minute{%F %H:%M}"),
                    ("Avg. persons per frame", "@avg_per_frame{0.00}"),
                    ("Person detection rows", "@person_rows{0,0}"),
                    ("Distinct frames", "@frame_count{0,0}"),
                ],
                formatters={"@minute": "datetime"},
                mode="vline",
            )
        )
        person_plot.xaxis.axis_label = "10-minute interval (start time)"
        person_plot.yaxis.axis_label = "Avg. persons per frame"
        person_plot.yaxis.formatter = NumeralTickFormatter(format="0.00")
        person_plot.y_range.start = 0
        person_plot.grid.grid_line_alpha = 0.2
        person_plot.toolbar.logo = None

    class_table_header = None
    class_table = None
    if result.class_stats:
        table_source = ColumnDataSource(
            data=dict(
                label=[stat.label for stat in result.class_stats],
                qualified=[stat.qualified_tracks for stat in result.class_stats],
                total=[stat.total_tracks for stat in result.class_stats],
                pass_rate=[f"{stat.pass_rate * 100:.0f}%" for stat in result.class_stats],
                median_frames=[f"{stat.median_frames:.0f}" for stat in result.class_stats],
                mean_duration=[f"{stat.mean_duration_s:.1f}s" for stat in result.class_stats],
                median_score=[f"{stat.median_score:.2f}" for stat in result.class_stats],
                short_frac=[f"{stat.short_frac * 100:.0f}%" for stat in result.class_stats],
            )
        )
        table_columns = [
            TableColumn(field="label", title="Class"),
            TableColumn(field="qualified", title="Qualified tracks"),
            TableColumn(field="total", title="Total tracks"),
            TableColumn(field="pass_rate", title="Quality pass rate"),
            TableColumn(field="median_frames", title="Median frames/track"),
            TableColumn(field="mean_duration", title="Mean duration"),
            TableColumn(field="median_score", title="Median score"),
            TableColumn(field="short_frac", title="% short tracks"),
        ]
        class_table = DataTable(
            source=table_source,
            columns=table_columns,
            sizing_mode="stretch_width",
            height=38 * (len(result.class_stats) + 1),
            index_position=None,
        )
        class_table_header = Div(
            text="""
            <h3 style="font-family:'IBM Plex Sans','Segoe UI',sans-serif;color:#0f172a;
                       margin:24px 0 4px;font-size:20px;">Track quality by class</h3>
            """,
            sizing_mode="stretch_width",
        )

    time_range = "No data"
    if not result.minute_counts.empty:
        start = result.minute_counts["minute"].min().strftime("%Y-%m-%d %H:%M")
        end = result.minute_counts["minute"].max().strftime("%Y-%m-%d %H:%M")
        time_range = f"{start} to {end}"

    dominant_text = ", ".join(
        f"{CLASS_LABELS.get(class_id, str(class_id))}: {count}"
        for class_id, count in result.dominant_classes.most_common(4)
    )
    if not dominant_text:
        dominant_text = "No qualifying classes"

    video_start_note = ""
    if result.video_start is not None:
        video_start_note = (
            "Timeline corrected to a real video start of "
            f"<code>{result.video_start.strftime('%Y-%m-%d %H:%M:%S')}</code>, using "
            "<code>timestamp_raw</code> elapsed time instead of the CSV's own "
            "<code>event_time</code>."
        )

    cards = Div(
        text=f"""
        <style>
          body {{
            margin: 0;
            font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
            background:
              radial-gradient(circle at top left, #ecfccb 0%, transparent 28%),
              linear-gradient(135deg, #f8fafc 0%, #ecfeff 100%);
            color: #102a43;
          }}
          .page {{
            max-width: 1180px;
            margin: 0 auto;
            padding: 32px 24px 48px;
          }}
          .hero {{
            display: grid;
            gap: 12px;
            margin-bottom: 24px;
          }}
          .eyebrow {{
            letter-spacing: 0.12em;
            font-size: 12px;
            text-transform: uppercase;
            color: #0f766e;
            font-weight: 700;
          }}
          .title {{
            font-size: 34px;
            line-height: 1.1;
            font-weight: 700;
            color: #0f172a;
          }}
          .subtitle {{
            font-size: 16px;
            color: #334155;
            max-width: 920px;
          }}
          .cards {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 14px;
            margin: 22px 0 18px;
          }}
          .card {{
            background: rgba(255, 255, 255, 0.85);
            border: 1px solid rgba(15, 118, 110, 0.14);
            border-radius: 18px;
            padding: 18px;
            box-shadow: 0 14px 40px rgba(15, 23, 42, 0.08);
            backdrop-filter: blur(8px);
          }}
          .label {{
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: #64748b;
            margin-bottom: 8px;
            font-weight: 700;
          }}
          .value {{
            font-size: 28px;
            font-weight: 700;
            color: #0f172a;
          }}
          @media (max-width: 640px) {{
            .title {{ font-size: 28px; }}
          }}
        </style>
        <div class="page">
          <div class="hero">
            <div class="eyebrow">Smart City Analytics</div>
            <div class="title">Unique vehicle track counts with quality filtering</div>
            <div class="subtitle">
              One vehicle contribution per <code>track_id</code>, placed at its first
              qualifying timestamp (no <code>semantic_zone</code> filtering &mdash; the
              zone/ROI condition is not applied to this count). The quality gate is
              <code>min_track_frames = {result.min_track_frames}</code> and
              <code>min_mean_score = {result.min_mean_score:.2f}</code>.
              {video_start_note}
            </div>
          </div>
          <div class="cards">
            <div class="card"><div class="label">Tracklet files</div><div class="value">{result.files_scanned}</div></div>
            <div class="card"><div class="label">Rows scanned</div><div class="value">{result.rows_scanned:,}</div></div>
            <div class="card"><div class="label">Candidate rows</div><div class="value">{result.candidate_rows:,}</div></div>
            <div class="card"><div class="label">Qualified tracks</div><div class="value">{result.qualified_tracks:,}</div></div>
            <div class="card"><div class="label">Minute points</div><div class="value">{len(result.minute_counts):,}</div></div>
            <div class="card"><div class="label">Time range</div><div class="value" style="font-size:18px">{time_range}</div></div>
            <div class="card"><div class="label">Dominant classes</div><div class="value" style="font-size:16px">{dominant_text}</div></div>
          </div>
        </div>
        """,
        sizing_mode="stretch_width",
    )

    plots = [cards, minute_plot]
    if hourly_plot is not None:
        plots.append(hourly_plot)
    if class_line_plot is not None:
        plots.append(class_line_plot)
    if person_plot is not None:
        plots.append(person_plot)
    if class_table is not None:
        plots.append(class_table_header)
        plots.append(class_table)
    return column(*plots, sizing_mode="stretch_width")


def render_dashboard(result: AnalyticsResult, title: str) -> str:
    layout = build_dashboard(result, title)
    return file_html(layout, CDN, title)


def make_handler(result: AnalyticsResult, title: str):
    class AnalyticsHandler(BaseHTTPRequestHandler):
        def _write(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
            self.send_response(status.value)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/":
                body = render_dashboard(result, title).encode("utf-8")
                self._write(HTTPStatus.OK, body, "text/html; charset=utf-8")
                return
            if parsed.path == "/api/hourly.json":
                payload = [
                    {
                        "hour": row.hour.isoformat(),
                        "count": int(row.count),
                    }
                    for row in result.hourly_counts.itertuples(index=False)
                ]
                body = json.dumps(payload, indent=2).encode("utf-8")
                self._write(HTTPStatus.OK, body, "application/json; charset=utf-8")
                return
            if parsed.path == "/api/minutely.json":
                payload = [
                    {
                        "minute": row.minute.isoformat(),
                        "count": int(row.count),
                    }
                    for row in result.minute_counts.itertuples(index=False)
                ]
                body = json.dumps(payload, indent=2).encode("utf-8")
                self._write(HTTPStatus.OK, body, "application/json; charset=utf-8")
                return
            if parsed.path == "/healthz":
                body = json.dumps(
                    {
                        "status": "ok",
                        "generated_at": datetime.utcnow().isoformat() + "Z",
                        "files_scanned": result.files_scanned,
                        "candidate_rows": result.candidate_rows,
                        "qualified_tracks": result.qualified_tracks,
                        "minute_points": len(result.minute_counts),
                        "road_only": result.road_only,
                        "min_track_frames": result.min_track_frames,
                        "min_mean_score": result.min_mean_score,
                    }
                ).encode("utf-8")
                self._write(HTTPStatus.OK, body, "application/json; charset=utf-8")
                return
            self._write(
                HTTPStatus.NOT_FOUND,
                b'{"error":"not found"}',
                "application/json; charset=utf-8",
            )

        def log_message(self, format: str, *args) -> None:
            print(f"[analytics] {self.address_string()} - {format % args}")

    return AnalyticsHandler


def main() -> None:
    args = parse_args()
    input_dir = Path(args.input_dir).resolve()
    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory does not exist: {input_dir}")

    result = load_vehicle_counts(
        input_dir=input_dir,
        road_only=False,
        min_track_frames=args.min_track_frames,
        min_mean_score=args.min_mean_score,
        video_start_arg=args.video_start_time,
    )
    print(
        "[analytics] Loaded dataset:",
        f"files={result.files_scanned}",
        f"rows={result.rows_scanned}",
        f"candidate_rows={result.candidate_rows}",
        f"qualified_tracks={result.qualified_tracks}",
        f"minute_points={len(result.minute_counts)}",
        f"video_start={result.video_start}",
        f"source={result.source_dir}",
    )

    server = ThreadingHTTPServer((args.host, args.port), make_handler(result, args.title))
    print(f"[analytics] Serving dashboard at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[analytics] Stopping server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
