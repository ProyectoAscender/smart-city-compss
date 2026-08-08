import numpy as np
from collections import deque
from scipy.signal import savgol_filter
from scipy.interpolate import interp1d
from src import event
import paho.mqtt.client as mqtt
import time

from pycompss.api.task import task


# MQTT broker config
MQTT_BROKER_IP   = "192.168.50.13"
MQTT_BROKER_PORT = 1883
MQTT_TOPIC       = "alerts"

mqtt_client = mqtt.Client()
try:
    mqtt_client.connect(MQTT_BROKER_IP, MQTT_BROKER_PORT)
    print(f"[main.py] Successfully connected to MQTT broker at {MQTT_BROKER_IP}:{MQTT_BROKER_PORT}")
except Exception as e:
    alerts = False
    print(f"[main.py] ERROR connecting to MQTT broker at {MQTT_BROKER_IP}:{MQTT_BROKER_PORT}: {e}")


# ── Parameters ────────────────────────────────────────────────────────────────
_WIN          = 31     # deque size — immobility detection + SG window (~1.5 s at 20-25 fps)
_SG_POLY      = 2      # quadratic: smoother than cubic, less edge overshoot on MOV<->PAR transitions
_SG_TAIL      = 3      # average velocity over the last N points of the SG output to reduce end-edge overshoot
_SG_MIN       = 0.3    # km/h — noise floor

_SPREAD_ENTER    = 0.5    # m — enter STOPPED when spread of last _WIN positions < this
_SPREAD_EXIT     = 0.8    # m — exit  STOPPED (hysteresis)

_CHECKPOINT_DIST = 2.5    # m — raw checkpoint: accumulate until this distance is reached

# ── Kalman CV parameters ──────────────────────────────────────────────────────
_KF_SIGMA_A    = 2.0   # m/s²  — process noise: expected urban vehicle acceleration
_KF_SIGMA_PX   = 5.0   # px    — measurement noise: expected bbox-centre detection error
_KF_STOP_ENTER = 1.0   # km/h  — enter stopped when KF speed falls below this
_KF_STOP_EXIT  = 1.5   # km/h  — exit  stopped when KF speed rises above this (hysteresis)

STATE_MOV, STATE_PAR = 0, 1


def _kf_R(M, px, py, sigma_px):
    """Heteroscedastic measurement noise covariance via homography Jacobian."""
    p   = M @ np.array([px, py, 1.0])
    W   = p[2]
    e_h = p[0] / W
    n_h = p[1] / W
    J = np.array([
        [(M[0, 0] - e_h * M[2, 0]) / W, (M[0, 1] - e_h * M[2, 1]) / W],
        [(M[1, 0] - n_h * M[2, 0]) / W, (M[1, 1] - n_h * M[2, 1]) / W],
    ])
    return sigma_px ** 2 * (J @ J.T)


def _sg_speed(pts, ts_arr, motion_state):
    """Savitzky-Golay speed estimate. Returns NaN if not enough data, 0 if STATE_PAR."""
    n   = len(pts)
    win = n if n % 2 else n - 1

    if motion_state == STATE_PAR or win < _SG_POLY + 2:
        return 0. if motion_state == STATE_PAR else np.nan

    try:
        ts_even = np.linspace(ts_arr[0], ts_arr[-1], win)
        dt_s    = float(ts_even[1] - ts_even[0]) / 1e6
        if dt_s <= 0:
            raise ValueError("zero dt")
        pts_even = interp1d(ts_arr, pts, axis=0, assume_sorted=True)(ts_even)
        vel      = savgol_filter(pts_even, win, _SG_POLY, deriv=1, delta=dt_s, axis=0)
        tail     = min(_SG_TAIL, len(vel))
        end_vel  = np.mean(vel[-tail:], axis=0)
        speed    = max(0., float(np.linalg.norm(end_vel)) * 3.6 - _SG_MIN)
        return speed if np.isfinite(speed) else np.nan
    except Exception:
        return np.nan


def _kalman_update(t, location, pixel_bc, M, frame_dt):
    """One Kalman CV predict+update step; mutates t._kf_x, t._kf_P, t.kf_speed.

    When STATE_PAR the filter still tracks position (so it has a good starting
    point when the car resumes) but velocity is forced to zero — stopped cars
    have no real velocity and bbox jitter must not accumulate into the state.
    """
    if t._kf_x is None:
        t._kf_x    = np.array([location[0], location[1], 0., 0.])
        t._kf_P    = np.diag([4., 4., (15. / 3.6) ** 2, (15. / 3.6) ** 2])
        t.kf_speed = np.nan
        return

    dt_kf = min(frame_dt, 2.0)

    F = np.array([[1, 0, dt_kf, 0    ],
                  [0, 1, 0,     dt_kf],
                  [0, 0, 1,     0    ],
                  [0, 0, 0,     1    ]], dtype=float)

    q = _KF_SIGMA_A ** 2
    dt2, dt3, dt4 = dt_kf ** 2, dt_kf ** 3, dt_kf ** 4
    Q = q * np.array([[dt4 / 4, 0,       dt3 / 2, 0      ],
                       [0,       dt4 / 4, 0,       dt3 / 2],
                       [dt3 / 2, 0,       dt2,     0      ],
                       [0,       dt3 / 2, 0,       dt2    ]])

    x_p = F @ t._kf_x
    P_p = F @ t._kf_P @ F.T + Q

    R_kf = _kf_R(M, float(pixel_bc[0]), float(pixel_bc[1]), _KF_SIGMA_PX)
    H    = np.array([[1., 0., 0., 0.],
                     [0., 1., 0., 0.]])
    y    = location - H @ x_p
    S    = H @ P_p @ H.T + R_kf
    K    = P_p @ H.T @ np.linalg.inv(S)
    IKH  = np.eye(4) - K @ H
    t._kf_x = x_p + K @ y
    t._kf_P = IKH @ P_p @ IKH.T + K @ R_kf @ K.T

    # Kalman-own stopped detection — independent of SG spread metric.
    # Uses the filter's own velocity estimate with hysteresis.
    kf_v = float(np.linalg.norm(t._kf_x[2:4])) * 3.6
    if   not t._kf_stopped and kf_v < _KF_STOP_ENTER: t._kf_stopped = True
    elif     t._kf_stopped and kf_v > _KF_STOP_EXIT:  t._kf_stopped = False

    if t._kf_stopped:
        t._kf_x[2:4] = 0.0
        t.kf_speed   = 0.
    else:
        t.kf_speed = kf_v if np.isfinite(kf_v) else np.nan


def speed_task(t, view_transformer, ts):
    pixel_bc = t.to_bc()[0:2]
    raw_loc  = view_transformer.pixel_to_map(pixel=[(pixel_bc[0], pixel_bc[1])])[0]

    if not hasattr(t, '_pos_win'):
        t._pos_win         = deque(maxlen=_WIN)
        t.motion_state     = STATE_MOV
        t._last_raw        = raw_loc
        t._last_ts         = ts
        t._accum_dist      = 0.
        t._accum_time      = 0.
        t.raw_speed        = None
        t.checkpoint_speed = None
        t._kf_x            = None
        t._kf_P            = None
        t.kf_speed         = np.nan
        t._kf_stopped      = False

    # Reject positions implying > 180 km/h (50 m/s) — homography outliers.
    dt_s     = max((ts - t._last_ts) / 1e6, 1e-6)
    frame_dt = dt_s  # preserved for Kalman — SG block redefines dt_s
    if np.linalg.norm(raw_loc - t._last_raw) / dt_s > 50.0:
        t.location = t._last_raw
    else:
        t.location = raw_loc
    t._last_raw = raw_loc
    t._last_ts  = ts

    # Raw / checkpoint speeds
    prev_entry = t._pos_win[-1] if t._pos_win else None
    t._pos_win.append((ts, t.location.copy()))

    if prev_entry is not None:
        step_dist = float(np.linalg.norm(t.location - prev_entry[1]))
        step_time = max((ts - prev_entry[0]) / 1e6, 1e-6)
        t.raw_speed    = step_dist / step_time * 3.6
        t._accum_dist += step_dist
        t._accum_time += step_time
        if t._accum_dist >= _CHECKPOINT_DIST:
            t.checkpoint_speed = t._accum_dist / t._accum_time * 3.6
            t._accum_dist = 0.
            t._accum_time = 0.
        else:
            t.checkpoint_speed = None
    else:
        t.raw_speed        = None
        t.checkpoint_speed = None

    pts    = np.array([p[1] for p in t._pos_win])
    ts_arr = np.array([p[0] for p in t._pos_win])

    # Immobility detection — wait for half the window before deciding
    if len(pts) >= _WIN // 2:
        spread = float(np.sqrt(pts[:, 0].var() + pts[:, 1].var()))
        if   t.motion_state == STATE_MOV and spread < _SPREAD_ENTER: t.motion_state = STATE_PAR
        elif t.motion_state == STATE_PAR and spread > _SPREAD_EXIT:  t.motion_state = STATE_MOV

    t.speed = _sg_speed(pts, ts_arr, t.motion_state)
    _kalman_update(t, t.location, pixel_bc, view_transformer.M, frame_dt)

    return t, f"#{t.track_id}  SG:{t.speed:.1f}  KF:{t.kf_speed:.1f} km/h"


def semantics_task(t, polys, ts, frameId, alerts):
    t.event = event.Event(t, polys, ts, frameId, t.track_id)
    if alerts and t.event.alertFlag:
        mqtt_client.publish(MQTT_TOPIC, t.event.to_json(), qos=0)
        return t, str(t.event)
    return t, "No alerts"


def process_tracklets(t, view_transformer, timers, get_semantic, get_speed, alerts, polys, ts, frameId):
    t_i = time.time()
    if get_speed:
        t, online_speeds = speed_task(t, view_transformer, ts)
    else:
        online_speeds = "# Speed disabled"
    t_speed = time.time() - t_i

    t_i = time.time()
    if get_semantic:
        t, alertInfo = semantics_task(t, polys, ts, frameId, ts)
    else:
        alertInfo = "Semantics disabled."
    t_semantics = time.time() - t_i

    return t, alertInfo, online_speeds, t_speed, t_semantics


def mqttClose():
    try:
        mqtt_client.disconnect()
        print(f"[main.py] Done closing connection with MQTT broker.\n")
    except Exception as e:
        print(f"[main.py] ERROR disconnecting from MQTT broker: {e}")
