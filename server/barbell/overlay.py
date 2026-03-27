from __future__ import annotations

from collections import Counter
from typing import Any


def build_overlay_from_barbell(
    barbell_result: dict[str, Any] | None,
    *,
    anchor: str = "plate",
    max_gap_ms: int = 180,
    min_conf: float = 0.05,
    min_segment_frames: int = 2,
    smooth_window: int = 3,
) -> dict[str, Any]:
    base = {
        "anchor": anchor,
        "maxGapMs": int(max_gap_ms),
        "frames": [],
    }

    if not barbell_result:
        return {
            **base,
            "error": "missing barbell trajectory",
        }

    frames = barbell_result.get("frames")
    if not isinstance(frames, list) or not frames:
        return {
            **base,
            "error": "missing barbell frames",
        }

    frame_width = _coerce_int(barbell_result.get("frameWidth"))
    frame_height = _coerce_int(barbell_result.get("frameHeight"))
    raw = [_extract_overlay_frame(f, anchor=anchor, min_conf=min_conf) for f in frames]
    bridged = _bridge_short_gaps(raw, max_gap_ms=max_gap_ms)
    segment_ids = _assign_segments(bridged, max_gap_ms=max_gap_ms, min_segment_frames=min_segment_frames)
    smoothed = _smooth_segments(bridged, segment_ids, window=smooth_window)

    out_frames: list[dict[str, Any]] = []
    points = 0
    segments = set[int]()
    for frame, seg_id, sm in zip(bridged, segment_ids, smoothed):
        payload: dict[str, Any] = {"timeMs": frame["timeMs"], "segmentId": seg_id}
        if sm is None:
            payload["point"] = None
            payload["bbox"] = None
            payload["conf"] = None
        else:
            points += 1
            segments.add(seg_id)
            payload["point"] = {"x": sm["x"], "y": sm["y"]}
            payload["bbox"] = {
                "x1": sm["x1"],
                "y1": sm["y1"],
                "x2": sm["x2"],
                "y2": sm["y2"],
            }
            payload["conf"] = frame["conf"]
        out_frames.append(payload)

    overlay = {
        **base,
        "frameWidth": frame_width,
        "frameHeight": frame_height,
        "frames": out_frames,
        "points": points,
        "segments": len(segments),
    }
    if points == 0:
        overlay["error"] = "no canonical overlay points"
    return overlay


def _bridge_short_gaps(
    frames: list[dict[str, Any]],
    *,
    max_gap_ms: int,
) -> list[dict[str, Any]]:
    out = [dict(frame) for frame in frames]
    i = 0
    while i < len(out):
        if out[i]["x"] is not None and out[i]["y"] is not None:
            i += 1
            continue

        start = i
        while i < len(out) and (out[i]["x"] is None or out[i]["y"] is None):
            i += 1
        end = i

        prev_i = start - 1
        next_i = end
        if prev_i < 0 or next_i >= len(out):
            continue

        prev_f = out[prev_i]
        next_f = out[next_i]
        if prev_f["x"] is None or prev_f["y"] is None or next_f["x"] is None or next_f["y"] is None:
            continue

        total_dt = int(next_f["timeMs"]) - int(prev_f["timeMs"])
        if total_dt <= 0 or total_dt > max_gap_ms:
            continue

        if _distance_px(prev_f, next_f) > _jump_gate_px(prev_f, next_f):
            continue

        for j in range(start, end):
            cur_t = int(out[j]["timeMs"])
            alpha = (cur_t - int(prev_f["timeMs"])) / max(1.0, float(total_dt))
            out[j] = {
                "timeMs": cur_t,
                "x": _lerp(prev_f["x"], next_f["x"], alpha),
                "y": _lerp(prev_f["y"], next_f["y"], alpha),
                "x1": _lerp(prev_f["x1"], next_f["x1"], alpha),
                "y1": _lerp(prev_f["y1"], next_f["y1"], alpha),
                "x2": _lerp(prev_f["x2"], next_f["x2"], alpha),
                "y2": _lerp(prev_f["y2"], next_f["y2"], alpha),
                "conf": min(float(prev_f["conf"]), float(next_f["conf"])) * 0.5,
            }
    return out


def _extract_overlay_frame(frame: Any, *, anchor: str, min_conf: float) -> dict[str, Any]:
    time_ms = 0
    if isinstance(frame, dict):
        time_val = frame.get("timeMs")
        if isinstance(time_val, (int, float)):
            time_ms = int(time_val)
        node = frame.get(anchor)
        parsed = _parse_node(node, min_conf=min_conf)
        if parsed is not None:
            return {
                "timeMs": time_ms,
                **parsed,
            }
    return {
        "timeMs": time_ms,
        "x": None,
        "y": None,
        "x1": None,
        "y1": None,
        "x2": None,
        "y2": None,
        "conf": None,
    }


def _parse_node(node: Any, *, min_conf: float) -> dict[str, Any] | None:
    if not isinstance(node, dict):
        return None
    if node.get("tracked") is True:
        return None

    center = node.get("center")
    bbox = node.get("bbox")
    conf = node.get("conf")
    if not isinstance(center, dict) or not isinstance(bbox, dict) or not isinstance(conf, (int, float)):
        return None
    if float(conf) < min_conf:
        return None

    x = center.get("x")
    y = center.get("y")
    x1 = bbox.get("x1")
    y1 = bbox.get("y1")
    x2 = bbox.get("x2")
    y2 = bbox.get("y2")
    if not all(isinstance(v, (int, float)) for v in (x, y, x1, y1, x2, y2)):
        return None

    return {
        "x": float(x),
        "y": float(y),
        "x1": float(x1),
        "y1": float(y1),
        "x2": float(x2),
        "y2": float(y2),
        "conf": float(conf),
    }


def _assign_segments(
    frames: list[dict[str, Any]],
    *,
    max_gap_ms: int,
    min_segment_frames: int,
) -> list[int | None]:
    segment_ids: list[int | None] = [None] * len(frames)
    next_segment = 0
    prev_valid: dict[str, Any] | None = None

    for idx, frame in enumerate(frames):
        if frame["x"] is None or frame["y"] is None:
            continue

        start_new = prev_valid is None
        if prev_valid is not None:
            dt_ms = int(frame["timeMs"]) - int(prev_valid["timeMs"])
            jump_px = _distance_px(frame, prev_valid)
            jump_gate_px = _jump_gate_px(frame, prev_valid)
            if dt_ms <= 0 or dt_ms > max_gap_ms or jump_px > jump_gate_px:
                start_new = True

        if start_new:
            next_segment += 1
        segment_ids[idx] = next_segment
        prev_valid = frame

    counts = Counter(seg for seg in segment_ids if seg is not None)
    for idx, seg in enumerate(segment_ids):
        if seg is not None and counts[seg] < min_segment_frames:
            segment_ids[idx] = None
    return segment_ids


def _smooth_segments(
    frames: list[dict[str, Any]],
    segment_ids: list[int | None],
    *,
    window: int,
) -> list[dict[str, float] | None]:
    if window <= 1:
        return [_frame_payload(frame) if seg is not None else None for frame, seg in zip(frames, segment_ids)]

    out: list[dict[str, float] | None] = [None] * len(frames)
    seg_to_indices: dict[int, list[int]] = {}
    for idx, seg in enumerate(segment_ids):
        if seg is None:
            continue
        seg_to_indices.setdefault(seg, []).append(idx)

    half = max(0, int(window) // 2)
    for indices in seg_to_indices.values():
        for local_idx, idx in enumerate(indices):
            lo = max(0, local_idx - half)
            hi = min(len(indices), local_idx + half + 1)
            sample = [frames[indices[j]] for j in range(lo, hi)]
            out[idx] = {
                "x": _avg(sample, "x"),
                "y": _avg(sample, "y"),
                "x1": _avg(sample, "x1"),
                "y1": _avg(sample, "y1"),
                "x2": _avg(sample, "x2"),
                "y2": _avg(sample, "y2"),
            }
    return out


def _frame_payload(frame: dict[str, Any]) -> dict[str, float]:
    return {
        "x": float(frame["x"]),
        "y": float(frame["y"]),
        "x1": float(frame["x1"]),
        "y1": float(frame["y1"]),
        "x2": float(frame["x2"]),
        "y2": float(frame["y2"]),
    }


def _avg(frames: list[dict[str, Any]], key: str) -> float:
    return sum(float(frame[key]) for frame in frames) / max(1, len(frames))


def _lerp(a: Any, b: Any, alpha: float) -> float:
    return float(a) + (float(b) - float(a)) * float(alpha)


def _distance_px(a: dict[str, Any], b: dict[str, Any]) -> float:
    dx = float(a["x"]) - float(b["x"])
    dy = float(a["y"]) - float(b["y"])
    return (dx * dx + dy * dy) ** 0.5


def _jump_gate_px(a: dict[str, Any], b: dict[str, Any]) -> float:
    aw = abs(float(a["x2"]) - float(a["x1"]))
    ah = abs(float(a["y2"]) - float(a["y1"]))
    bw = abs(float(b["x2"]) - float(b["x1"]))
    bh = abs(float(b["y2"]) - float(b["y1"]))
    scale = max(aw, ah, bw, bh, 1.0)
    return max(36.0, scale * 1.5)


def _coerce_int(v: Any) -> int | None:
    if not isinstance(v, (int, float)):
        return None
    out = int(v)
    return out if out > 0 else None
