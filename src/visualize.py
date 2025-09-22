#!/usr/bin/env python3
# -*- coding:utf-8 -*-
# Copyright (c) 2014-2021 Megvii Inc. All rights reserved.

import cv2
import numpy as np

__all__ = ["vis"]

alertXInit, alertYInit = 10,700

def vis(img, boxes, scores, cls_ids, conf=0.5, class_names=None):

    for i in range(len(boxes)):
        box = boxes[i]
        cls_id = int(cls_ids[i])
        score = scores[i]
        if score < conf:
            print('Saltando por confidence')
            continue
        x0 = int(box[0])
        y0 = int(box[1])
        x1 = int(box[2])
        y1 = int(box[3])

        color = (_COLORS[cls_id] * 255).astype(np.uint8).tolist()
        text = '{}:{:.1f}%'.format(class_names[cls_id], score * 100)
        txt_color = (0, 0, 0) if np.mean(_COLORS[cls_id]) > 0.5 else (255, 255, 255)
        font = cv2.FONT_HERSHEY_SIMPLEX

        txt_size = cv2.getTextSize(text, font, 0.4, 1)[0]
        cv2.rectangle(img, (x0, y0), (x1, y1), color, 2)

        txt_bk_color = (_COLORS[cls_id] * 255 * 0.7).astype(np.uint8).tolist()
        cv2.rectangle(
            img,
            (x0, y0 + 1),
            (x0 + txt_size[0] + 1, y0 + int(1.5*txt_size[1])),
            txt_bk_color,
            -1
        )
        cv2.putText(img, text, (x0, y0 + txt_size[1]), font, 0.4, txt_color, thickness=1)

    return img


def get_color(idx):
    idx = idx * 3
    color = ((37 * idx) % 255, (17 * idx) % 255, (29 * idx) % 255)

    return color
# Estado del visualizador (solo coordenadas de píxeles)
trail_last_px = {}
trail_segments = {}
MAX_SEGMENTS_PER_TRACK = None  # None = ilimitado

def _bbox_int(box_tlwh):
    x1, y1, w, h = box_tlwh
    return int(x1), int(y1), int(x1 + w), int(y1 + h)

def _bbox_center(intbox):
    x1, y1, x2, y2 = intbox
    return ((x1 + x2) // 2, (y1 + y2) // 2)

def _put_text(img, text, org, scale=0.45, color=(255,255,255), thick=1):
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX,
                scale, color, thick, cv2.LINE_AA)

def _put_text_right(img, text, topright_xy, scale=0.55, color=(255,255,255), thick=2):
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
    x = max(0, topright_xy[0] - tw - 5)
    y = topright_xy[1] + th
    cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX,
                scale, color, thick, cv2.LINE_AA)

def plot_tracking(image, online_targets, frame_id=0, fps=0., ids2=None, get_semantic=False):
    global trail_last_px, trail_segments

    im = np.ascontiguousarray(np.copy(image))
    cv2.putText(im, f'SC - FrameId: {frame_id} fps: {fps:.2f}',
                (0, 30), cv2.FONT_HERSHEY_PLAIN, 2, (0, 0, 255), 2)

    alertCounter = 0

    for i, t in enumerate(online_targets):
        # --- Solo activados y con edad válida
        if not getattr(t, 'is_activated', False):
            print('Saltando por is activated')

            continue

        # --- Si muere (state 2/3) borramos TODO su rastro en el visualizador
        if getattr(t, "state", None) in (2, 3):
            print('Saltando por state')
            trail_last_px.pop(t.track_id, None)
            trail_segments.pop(t.track_id, None)
            continue

        # --- Ignorar recien llegados
        if getattr(t, "frames_since_update", 0) > 3:
            print('Saltando por fsu')
            continue

        # --- Filtrar clase 1
        if getattr(t, 'cl', None) == 1:
            # print('Filtrando peatones')
            continue

        # --- Caja y color
        x1, y1, x2, y2 = _bbox_int(t.tlwh)
        intbox = (x1, y1, x2, y2)
        color = get_color(abs(int(t.track_id)))
        line_thickness = 3

        # (Opcional) semántica
        if get_semantic and getattr(t, 'event', None) is not None and getattr(t.event, 'alertFlag', False):
            line_thickness = 4
            label = f'{t.event.category} - {t.event.severity} - {t.track_id}'
            alertCounter += 1
            alertX, alertY = 10, 40 + alertCounter * 25
            cv2.putText(im, label, (alertX, alertY),
                        cv2.FONT_HERSHEY_SIMPLEX, .9, (0, 0, 255), 2, cv2.LINE_AA)

        # --- Dibujo de caja
        cv2.rectangle(im, (x1, y1), (x2, y2), color, line_thickness)

        # score
        if getattr(t, 'score', None) is not None:
            _put_text_right(im, f'{t.score:.2f}', (x2 - 5, y1 + 5), scale=0.55)

        # median_speed dentro (esquina inf-izq, más pequeño)
        if getattr(t, 'median_speed', None) is not None:
            _put_text(im, f'{t.median_speed:.1f}', (x1 + 4, y2 - 4),
                      scale=0.5, color=(0,255,255), thick=1)

        # ID abajo-dcha dentro (más pequeño)
        _put_text_right(im, f'{str(t.track_id)}', (x2 - 5, y2 - 20),
                        scale=0.5, color=(0,255,0), thick=1)

        # vector de velocidades fuera, pegado a esquina inf-izq
        if getattr(t, 'speeds', None) is not None and len(t.speeds) > 0:
            speeds_txt = ", ".join(f"{v:.1f}" for v in np.asarray(t.speeds).ravel().tolist())
            _put_text(im, speeds_txt, (x1 + 5, y2 + 15),
                      scale=0.4, color=(200,200,200), thick=1)

        # === Trayectoria en píxeles ===
        curr_px = _bbox_center(intbox)
        prev_px = trail_last_px.get(t.track_id)

        if prev_px is not None:
            seg_list = trail_segments.setdefault(t.track_id, [])
            # ahora solo guardamos pares de píxeles; distancia vendrá de t.distances
            seg_list.append((prev_px, curr_px))
            if isinstance(MAX_SEGMENTS_PER_TRACK, int) and len(seg_list) > MAX_SEGMENTS_PER_TRACK:
                seg_list[:] = seg_list[-MAX_SEGMENTS_PER_TRACK:]

        trail_last_px[t.track_id] = curr_px

        # Dibujar segmentos con distancias desde t.distances
        if t.track_id in trail_segments:
            segs = trail_segments[t.track_id]
            dists = getattr(t, 'distances', [])
            for idx, (p1, p2) in enumerate(segs):
                cv2.line(im, p1, p2, color, 2)
                if idx < len(dists) and dists[idx] is not None:
                    mid = ((p1[0] + p2[0]) // 2, (p1[1] + p2[1]) // 2)
                    _put_text(im, f'{dists[idx]:.1f}m', (mid[0] + 4, mid[1] - 4),
                              scale=0.45, color=(255,255,255), thick=1)

    return im


_COLORS = np.array(
    [
        0.000, 0.447, 0.741,
        0.850, 0.325, 0.098,
        0.929, 0.694, 0.125,
        0.494, 0.184, 0.556,
        0.466, 0.674, 0.188,
        0.301, 0.745, 0.933,
        0.635, 0.078, 0.184,
        0.300, 0.300, 0.300,
        0.600, 0.600, 0.600,
        1.000, 0.000, 0.000,
        1.000, 0.500, 0.000,
        0.749, 0.749, 0.000,
        0.000, 1.000, 0.000,
        0.000, 0.000, 1.000,
        0.667, 0.000, 1.000,
        0.333, 0.333, 0.000,
        0.333, 0.667, 0.000,
        0.333, 1.000, 0.000,
        0.667, 0.333, 0.000,
        0.667, 0.667, 0.000,
        0.667, 1.000, 0.000,
        1.000, 0.333, 0.000,
        1.000, 0.667, 0.000,
        1.000, 1.000, 0.000,
        0.000, 0.333, 0.500,
        0.000, 0.667, 0.500,
        0.000, 1.000, 0.500,
        0.333, 0.000, 0.500,
        0.333, 0.333, 0.500,
        0.333, 0.667, 0.500,
        0.333, 1.000, 0.500,
        0.667, 0.000, 0.500,
        0.667, 0.333, 0.500,
        0.667, 0.667, 0.500,
        0.667, 1.000, 0.500,
        1.000, 0.000, 0.500,
        1.000, 0.333, 0.500,
        1.000, 0.667, 0.500,
        1.000, 1.000, 0.500,
        0.000, 0.333, 1.000,
        0.000, 0.667, 1.000,
        0.000, 1.000, 1.000,
        0.333, 0.000, 1.000,
        0.333, 0.333, 1.000,
        0.333, 0.667, 1.000,
        0.333, 1.000, 1.000,
        0.667, 0.000, 1.000,
        0.667, 0.333, 1.000,
        0.667, 0.667, 1.000,
        0.667, 1.000, 1.000,
        1.000, 0.000, 1.000,
        1.000, 0.333, 1.000,
        1.000, 0.667, 1.000,
        0.333, 0.000, 0.000,
        0.500, 0.000, 0.000,
        0.667, 0.000, 0.000,
        0.833, 0.000, 0.000,
        1.000, 0.000, 0.000,
        0.000, 0.167, 0.000,
        0.000, 0.333, 0.000,
        0.000, 0.500, 0.000,
        0.000, 0.667, 0.000,
        0.000, 0.833, 0.000,
        0.000, 1.000, 0.000,
        0.000, 0.000, 0.167,
        0.000, 0.000, 0.333,
        0.000, 0.000, 0.500,
        0.000, 0.000, 0.667,
        0.000, 0.000, 0.833,
        0.000, 0.000, 1.000,
        0.000, 0.000, 0.000,
        0.143, 0.143, 0.143,
        0.286, 0.286, 0.286,
        0.429, 0.429, 0.429,
        0.571, 0.571, 0.571,
        0.714, 0.714, 0.714,
        0.857, 0.857, 0.857,
        0.000, 0.447, 0.741,
        0.314, 0.717, 0.741,
        0.50, 0.5, 0
    ]
).astype(np.float32).reshape(-1, 3)
