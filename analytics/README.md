# Smart City Analytics

This folder contains a small analytics app that reads `tracklets.txt` files,
filters out people (`class_id = 0`), keeps only `road` rows by default, and
counts each qualified `track_id` once using its first qualifying timestamp.

The default quality gate is:

- `min_track_frames = 10`
- `min_mean_score = 0.6`

Those defaults came from the distribution observed in `runs/exp/20260712` and
are configurable at runtime.

## Local run

Install the dependencies first if needed:

```bash
python3 -m pip install -r analytics/requirements.txt
```

Then start the server:

```bash
bash analytics/run_local.sh
```

Useful flags:

```bash
python3 analytics/app.py \
  --input-dir runs/exp/20260712 \
  --min-track-frames 15 \
  --min-mean-score 0.6
```

The CSV's `event_time` column is derived from the camera's own clock, which does not
necessarily match the real-world time the video was recorded. If you know the real
start time, pass it with `--video-start-time` and the dashboard's timeline (minute/hour/
per-class charts, "Time range" card) will be rebuilt from `timestamp_raw` (elapsed
microseconds between frames) offset from that start instead of trusting `event_time`:

```bash
python3 analytics/app.py \
  --input-dir runs/exp/20260712 \
  --video-start-time "07:00:00"
```

A bare time of day (`"07:00:00"`) is combined with the date of the earliest `event_time`
found in the dataset; pass a full timestamp (`"2026-07-12 07:00:00"`) to also override the date.

## Docker run

```bash
bash analytics/run_docker.sh
```

By default it reads from `runs/exp/20260712` locally, or `/data/runs/exp/20260712`
inside the container.

## Statistical analysis

To recompute a threshold recommendation on a dataset:

```bash
python3 analytics/tracklet_stats.py --input-dir runs/exp/20260712
```

## Long-Series Speed Dashboard

The folder also includes a separate Bokeh server app for very long speed time
series over archive-style trees:

```text
<root>/
├── 0003/YYYYMMDD/HHMM/tracklets.txt
└── 0004/YYYYMMDD/HHMM/tracklets.txt
```

It uses Dask to lazily read only the columns needed for speed analytics, caches
aggregates by interval and metric, and only pushes the visible window to Bokeh
sources so zooming stays responsive.

### Local run

```bash
bash analytics/run_long_series_local.sh /path/to/archive/root
```

The app is served on `http://localhost:5006/long_series_dashboard`.

### Docker run

```bash
bash analytics/run_long_series_docker.sh /path/to/archive/root
```

This launches the container detached (`docker run -d`) and binds
`http://localhost:5006/long_series_dashboard`.

### Controls

- Time bucket: `1 min`, `10 min`, `1 h`
- Metric: `Average speed`, `Speed sum`
- Cameras: multi-select buttons discovered from the directory tree

Each subplot is one vehicle type, with shared zoom and wheel zoom enabled.
