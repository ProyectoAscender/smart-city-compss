#!/usr/bin/env python3
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import pandas as pd
from bokeh.io import curdoc
from bokeh.layouts import column, gridplot, row
from bokeh.models import (
    Button,
    CheckboxButtonGroup,
    ColumnDataSource,
    Div,
    HoverTool,
    NumeralTickFormatter,
    RadioButtonGroup,
    Range1d,
)
from bokeh.palettes import Category10
from bokeh.plotting import figure

from analytics.long_series_backend import (
    DEFAULT_MAX_POINTS,
    INTERVAL_OPTIONS,
    METRIC_OPTIONS,
    get_store,
)


EXECUTOR = ThreadPoolExecutor(max_workers=2)
DOC = curdoc()
DATA_ROOT = os.environ.get("LONG_SERIES_DATA_ROOT", "/data/traffic-data")
APP_TITLE = os.environ.get("LONG_SERIES_APP_TITLE", "Smart City Long-Series Speeds")
MAX_VISIBLE_POINTS = int(os.environ.get("LONG_SERIES_MAX_POINTS", str(DEFAULT_MAX_POINTS)))


@dataclass
class DashboardState:
    full_frame: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=["timestamp", "vehicle_type", "value"]))
    request_token: int = 0
    suppress_range_events: bool = False


STATE = DashboardState()
STORE = get_store(DATA_ROOT)
INVENTORY = STORE.inventory()

interval_labels = list(INTERVAL_OPTIONS)
metric_labels = list(METRIC_OPTIONS)
camera_labels = list(INVENTORY.cameras)
vehicle_labels = list(STORE.available_vehicle_types())

interval_selector = RadioButtonGroup(labels=interval_labels, active=1)
metric_selector = RadioButtonGroup(labels=metric_labels, active=0)
camera_selector = CheckboxButtonGroup(labels=camera_labels, active=list(range(len(camera_labels))))
refresh_button = Button(label="Refresh file index", button_type="default")
reset_zoom_button = Button(label="Reset zoom", button_type="primary")

status_div = Div(sizing_mode="stretch_width")
summary_div = Div(sizing_mode="stretch_width")

shared_range = Range1d()
sources: dict[str, ColumnDataSource] = {
    vehicle_label: ColumnDataSource(data={"timestamp": [], "value": []})
    for vehicle_label in vehicle_labels
}

color_cycle = Category10[10]
figures = []
for idx, vehicle_label in enumerate(vehicle_labels):
    plot = figure(
        title=vehicle_label.capitalize(),
        x_axis_type="datetime",
        x_range=shared_range,
        height=220,
        sizing_mode="stretch_width",
        tools="pan,wheel_zoom,box_zoom,reset,save",
        active_scroll="wheel_zoom",
        output_backend="webgl",
    )
    plot.line(
        x="timestamp",
        y="value",
        source=sources[vehicle_label],
        line_width=2.5,
        color=color_cycle[idx % len(color_cycle)],
        alpha=0.92,
    )
    plot.add_tools(
        HoverTool(
            tooltips=[
                ("Time", "@timestamp{%F %H:%M}"),
                ("Value", "@value{0,0.00}"),
            ],
            formatters={"@timestamp": "datetime"},
            mode="vline",
        )
    )
    plot.yaxis.axis_label = "Speed"
    plot.yaxis.formatter = NumeralTickFormatter(format="0,0.00")
    plot.xaxis.axis_label = "Time"
    plot.grid.grid_line_alpha = 0.22
    plot.toolbar.logo = None
    figures.append(plot)


def active_interval() -> str:
    return INTERVAL_OPTIONS[interval_labels[interval_selector.active]]


def active_metric() -> str:
    return METRIC_OPTIONS[metric_labels[metric_selector.active]]


def active_cameras() -> tuple[str, ...]:
    if not camera_labels:
        return ()
    if not camera_selector.active:
        return tuple(camera_labels)
    return tuple(camera_labels[idx] for idx in camera_selector.active)


def update_status(message: str, loading: bool = False) -> None:
    state = "Loading…" if loading else "Ready"
    status_div.text = f"""
    <div style="padding:12px 14px;border:1px solid #cbd5e1;border-radius:14px;background:#ffffffd9;">
      <div style="font:700 12px 'IBM Plex Sans', sans-serif;letter-spacing:0.08em;color:#0f766e;text-transform:uppercase;">Long-Series Dashboard</div>
      <div style="font:600 15px 'IBM Plex Sans', sans-serif;color:#0f172a;margin-top:6px;">{state}</div>
      <div style="font:400 14px 'IBM Plex Sans', sans-serif;color:#334155;margin-top:4px;">{message}</div>
    </div>
    """


def update_summary() -> None:
    first_ts = "No data"
    last_ts = "No data"
    if not STATE.full_frame.empty:
        first_ts = STATE.full_frame["timestamp"].min().strftime("%Y-%m-%d %H:%M")
        last_ts = STATE.full_frame["timestamp"].max().strftime("%Y-%m-%d %H:%M")
    summary_div.text = f"""
    <div style="padding:16px 18px;border:1px solid rgba(15,118,110,0.18);border-radius:18px;background:rgba(255,255,255,0.88);box-shadow:0 14px 30px rgba(15,23,42,0.08);">
      <div style="font:700 28px 'IBM Plex Sans', sans-serif;color:#0f172a;">{APP_TITLE}</div>
      <div style="font:400 15px 'IBM Plex Sans', sans-serif;color:#334155;margin-top:6px;">
        Root: <code>{INVENTORY.root}</code><br>
        Files discovered: <strong>{INVENTORY.file_count}</strong> · Cameras: <strong>{', '.join(INVENTORY.cameras) or 'none'}</strong><br>
        Current selection: <strong>{interval_labels[interval_selector.active]}</strong> · <strong>{metric_labels[metric_selector.active]}</strong><br>
        Visible source range: <strong>{first_ts}</strong> to <strong>{last_ts}</strong>
      </div>
    </div>
    """


def apply_visible_slice() -> None:
    if STATE.full_frame.empty:
        for vehicle_label in vehicle_labels:
            sources[vehicle_label].data = {"timestamp": [], "value": []}
        return

    start = pd.to_datetime(shared_range.start, unit="ms", errors="coerce") if shared_range.start is not None else None
    end = pd.to_datetime(shared_range.end, unit="ms", errors="coerce") if shared_range.end is not None else None
    series_by_vehicle = STORE.slice_for_view(
        STATE.full_frame,
        start=start,
        end=end,
        max_points=MAX_VISIBLE_POINTS,
    )
    for vehicle_label in vehicle_labels:
        frame = series_by_vehicle[vehicle_label]
        sources[vehicle_label].data = {
            "timestamp": list(frame.get("timestamp", [])),
            "value": list(frame.get("value", [])),
        }


def set_full_range() -> None:
    if STATE.full_frame.empty:
        return
    STATE.suppress_range_events = True
    shared_range.start = STATE.full_frame["timestamp"].min()
    shared_range.end = STATE.full_frame["timestamp"].max()
    STATE.suppress_range_events = False


def on_range_change(attr: str, old, new) -> None:
    if STATE.suppress_range_events:
        return
    apply_visible_slice()


shared_range.on_change("start", on_range_change)
shared_range.on_change("end", on_range_change)


def load_selection() -> None:
    STATE.request_token += 1
    token = STATE.request_token
    interval = active_interval()
    metric = active_metric()
    cameras = active_cameras()
    camera_text = ", ".join(cameras) if cameras else "all"
    update_status(
        f"Building cached aggregate for interval={interval}, metric={metric}, cameras={camera_text}.",
        loading=True,
    )

    future = EXECUTOR.submit(STORE.aggregate, interval, metric, cameras)

    def finish(fut) -> None:
        try:
            result = fut.result()
            error = None
        except Exception as exc:  # pragma: no cover - defensive path
            result = None
            error = exc

        def apply_result() -> None:
            if token != STATE.request_token:
                return
            if error is not None:
                update_status(f"Failed to load aggregate: {error}", loading=False)
                return
            STATE.full_frame = result
            set_full_range()
            apply_visible_slice()
            update_summary()
            update_status(
                f"Loaded {len(result):,} aggregated points across {len(cameras) or len(camera_labels)} camera selections. "
                f"Only the visible window is pushed to Bokeh sources.",
                loading=False,
            )

        DOC.add_next_tick_callback(apply_result)

    future.add_done_callback(finish)


def on_selection_change(attr: str, old, new) -> None:
    load_selection()


def on_selector_active(attr: str, old, new) -> None:
    load_selection()


interval_selector.on_change("active", on_selector_active)
metric_selector.on_change("active", on_selector_active)
camera_selector.on_change("active", on_selection_change)


def refresh_inventory() -> None:
    STORE.clear_caches()
    load_selection()


refresh_button.on_click(refresh_inventory)
reset_zoom_button.on_click(lambda: (set_full_range(), apply_visible_slice()))

controls = row(
    interval_selector,
    metric_selector,
    camera_selector,
    reset_zoom_button,
    refresh_button,
    sizing_mode="stretch_width",
)

layout = column(
    summary_div,
    controls,
    status_div,
    gridplot([[figures[0], figures[1]], [figures[2], figures[3]], [figures[4], figures[5]]], sizing_mode="stretch_width"),
    sizing_mode="stretch_width",
)

DOC.title = APP_TITLE
DOC.add_root(layout)
update_summary()
load_selection()
