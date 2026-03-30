from __future__ import annotations

import math
from typing import Any


def build_pose_structures(
    *,
    pose_result: dict[str, Any] | None,
    exercise: str,
) -> dict[str, Any]:
    if not isinstance(pose_result, dict):
        return _empty_structure_result(exercise=exercise)

    frames = pose_result.get("keypoints")
    if not isinstance(frames, list):
        return _empty_structure_result(exercise=exercise)

    primary_side = pose_result.get("primarySide")
    if primary_side not in {"left", "right"}:
        primary_side = "left"

    structure_frames: list[dict[str, Any]] = []
    torso_count = 0
    foot_count = 0
    forearm_count = 0

    for frame in frames:
        if not isinstance(frame, dict):
            continue
        time_ms = frame.get("timeMs")
        keypoints = frame.get("keypoints")
        if not isinstance(time_ms, (int, float)) or not isinstance(keypoints, dict):
            continue

        structures = _extract_frame_structures(keypoints=keypoints, side=str(primary_side))
        if structures.get("torsoLine") is not None:
            torso_count += 1
        if structures.get("footMidpoint") is not None:
            foot_count += 1
        if structures.get("forearmLine") is not None:
            forearm_count += 1

        structure_frames.append(
            {
                "timeMs": int(time_ms),
                "tracked": bool(frame.get("tracked")),
                **structures,
            }
        )

    structure_frames = _fill_short_structure_gaps(structure_frames, max_gap_frames=3)
    structure_frames = _smooth_structure_frames(structure_frames, alpha=0.42)

    sampled = len(structure_frames)
    return {
        "exercise": exercise,
        "primarySide": primary_side,
        "frames": structure_frames,
        "quality": {
            "sampledFrames": sampled,
            "torsoLineCoverage": _coverage(torso_count, sampled),
            "footMidpointCoverage": _coverage(foot_count, sampled),
            "forearmLineCoverage": _coverage(forearm_count, sampled),
        },
    }


def _extract_frame_structures(*, keypoints: dict[str, Any], side: str) -> dict[str, Any]:
    left_shoulder = _trusted_point(keypoints, "leftShoulder")
    right_shoulder = _trusted_point(keypoints, "rightShoulder")
    left_hip = _trusted_point(keypoints, "leftHip")
    right_hip = _trusted_point(keypoints, "rightHip")
    left_knee = _trusted_point(keypoints, "leftKnee")
    right_knee = _trusted_point(keypoints, "rightKnee")
    left_ankle = _trusted_point(keypoints, "leftAnkle")
    right_ankle = _trusted_point(keypoints, "rightAnkle")
    left_elbow = _trusted_point(keypoints, "leftElbow")
    right_elbow = _trusted_point(keypoints, "rightElbow")
    left_wrist = _trusted_point(keypoints, "leftWrist")
    right_wrist = _trusted_point(keypoints, "rightWrist")

    shoulder_center = _midpoint(left_shoulder, right_shoulder) or _point_copy(
        _trusted_point(keypoints, f"{side}Shoulder")
    )
    hip_center = _midpoint(left_hip, right_hip) or _point_copy(
        _trusted_point(keypoints, f"{side}Hip")
    )
    chest_center = _midpoint(shoulder_center, hip_center)

    knee_point = _point_copy(_trusted_point(keypoints, f"{side}Knee"))
    ankle_point = _point_copy(_trusted_point(keypoints, f"{side}Ankle"))
    foot_midpoint = _estimate_foot_midpoint(ankle_point=ankle_point, knee_point=knee_point)

    elbow_point = _point_copy(_trusted_point(keypoints, f"{side}Elbow"))
    wrist_point = _point_copy(_trusted_point(keypoints, f"{side}Wrist"))

    torso_line = _line(shoulder_center, hip_center)
    thigh_line = _line(_point_copy(_trusted_point(keypoints, f"{side}Hip")), knee_point)
    shank_line = _line(knee_point, ankle_point)
    forearm_line = _line(elbow_point, wrist_point)

    return {
        "torsoLine": torso_line,
        "thighLine": thigh_line,
        "shankLine": shank_line,
        "forearmLine": forearm_line,
        "hipCenter": hip_center,
        "chestCenter": chest_center,
        "kneePoint": knee_point,
        "anklePoint": ankle_point,
        "footMidpoint": foot_midpoint,
    }


def _estimate_foot_midpoint(
    *,
    ankle_point: dict[str, float] | None,
    knee_point: dict[str, float] | None,
) -> dict[str, float] | None:
    if not isinstance(ankle_point, dict):
        return None
    if not isinstance(knee_point, dict):
        return _point_copy(ankle_point)
    dx = float(ankle_point["x"]) - float(knee_point["x"])
    dy = float(ankle_point["y"]) - float(knee_point["y"])
    norm = math.hypot(dx, dy)
    if norm <= 1e-6:
        return _point_copy(ankle_point)
    forward_x = dx / norm
    forward_y = dy / norm
    return {
        "x": float(ankle_point["x"]) + forward_x * 18.0,
        "y": float(ankle_point["y"]) + forward_y * 8.0,
    }


def _line(a: dict[str, float] | None, b: dict[str, float] | None) -> dict[str, Any] | None:
    if not isinstance(a, dict) or not isinstance(b, dict):
        return None
    dx = float(b["x"]) - float(a["x"])
    dy = float(b["y"]) - float(a["y"])
    return {
        "start": _point_copy(a),
        "end": _point_copy(b),
        "angleDeg": math.degrees(math.atan2(dy, dx)),
        "lengthPx": math.hypot(dx, dy),
    }


def _point_copy(point: dict[str, Any] | None) -> dict[str, float] | None:
    if not isinstance(point, dict):
        return None
    x = point.get("x")
    y = point.get("y")
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        return None
    return {"x": float(x), "y": float(y)}


def _midpoint(
    a: dict[str, Any] | None,
    b: dict[str, Any] | None,
) -> dict[str, float] | None:
    if not isinstance(a, dict) or not isinstance(b, dict):
        return None
    ax = a.get("x")
    ay = a.get("y")
    bx = b.get("x")
    by = b.get("y")
    if not all(isinstance(v, (int, float)) for v in (ax, ay, bx, by)):
        return None
    return {"x": (float(ax) + float(bx)) / 2.0, "y": (float(ay) + float(by)) / 2.0}


def _trusted_point(points: dict[str, Any], name: str) -> dict[str, Any] | None:
    point = points.get(name)
    if not isinstance(point, dict):
        return None
    if point.get("trusted") is False:
        return None
    return point


def _coverage(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def _empty_structure_result(*, exercise: str) -> dict[str, Any]:
    return {
        "exercise": exercise,
        "primarySide": "left",
        "frames": [],
        "quality": {
            "sampledFrames": 0,
            "torsoLineCoverage": 0.0,
            "footMidpointCoverage": 0.0,
            "forearmLineCoverage": 0.0,
        },
    }


def _fill_short_structure_gaps(
    frames: list[dict[str, Any]],
    *,
    max_gap_frames: int,
) -> list[dict[str, Any]]:
    if max_gap_frames <= 0 or len(frames) < 3:
        return frames

    fields = [
        "torsoLine",
        "thighLine",
        "shankLine",
        "forearmLine",
        "hipCenter",
        "chestCenter",
        "kneePoint",
        "anklePoint",
        "footMidpoint",
    ]
    out = [dict(frame) for frame in frames]

    for field in fields:
        index = 0
        while index < len(out):
            if out[index].get(field) is not None:
                index += 1
                continue
            start = index
            while index < len(out) and out[index].get(field) is None:
                index += 1
            end = index
            gap = end - start
            prev_idx = start - 1
            next_idx = end
            if (
                gap <= max_gap_frames
                and prev_idx >= 0
                and next_idx < len(out)
                and out[prev_idx].get(field) is not None
                and out[next_idx].get(field) is not None
            ):
                for missing_idx in range(start, end):
                    ratio = float(missing_idx - prev_idx) / float(next_idx - prev_idx)
                    out[missing_idx][field] = _interpolate_value(
                        out[prev_idx][field],
                        out[next_idx][field],
                        ratio,
                    )
    return out


def _smooth_structure_frames(
    frames: list[dict[str, Any]],
    *,
    alpha: float,
) -> list[dict[str, Any]]:
    if not frames:
        return frames
    alpha = max(0.0, min(1.0, alpha))
    out: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    for frame in frames:
        current = dict(frame)
        if previous is not None:
            for field in (
                "torsoLine",
                "thighLine",
                "shankLine",
                "forearmLine",
                "hipCenter",
                "chestCenter",
                "kneePoint",
                "anklePoint",
                "footMidpoint",
            ):
                current[field] = _smooth_value(
                    previous.get(field),
                    current.get(field),
                    alpha=alpha,
                )
        out.append(current)
        previous = current
    return out


def _smooth_value(previous: Any, current: Any, *, alpha: float) -> Any:
    if current is None:
        return previous
    if previous is None:
        return current
    if isinstance(current, dict) and isinstance(previous, dict):
        if {"x", "y"} <= set(current.keys()) and {"x", "y"} <= set(previous.keys()):
            return {
                "x": _blend(float(previous["x"]), float(current["x"]), alpha),
                "y": _blend(float(previous["y"]), float(current["y"]), alpha),
            }
        if {"start", "end"} <= set(current.keys()) and {"start", "end"} <= set(previous.keys()):
            start = _smooth_value(previous.get("start"), current.get("start"), alpha=alpha)
            end = _smooth_value(previous.get("end"), current.get("end"), alpha=alpha)
            if not isinstance(start, dict) or not isinstance(end, dict):
                return current
            dx = float(end["x"]) - float(start["x"])
            dy = float(end["y"]) - float(start["y"])
            return {
                "start": start,
                "end": end,
                "angleDeg": math.degrees(math.atan2(dy, dx)),
                "lengthPx": math.hypot(dx, dy),
            }
    return current


def _interpolate_value(a: Any, b: Any, ratio: float) -> Any:
    if a is None or b is None:
        return a if b is None else b
    if isinstance(a, dict) and isinstance(b, dict):
        if {"x", "y"} <= set(a.keys()) and {"x", "y"} <= set(b.keys()):
            return {
                "x": _lerp(float(a["x"]), float(b["x"]), ratio),
                "y": _lerp(float(a["y"]), float(b["y"]), ratio),
            }
        if {"start", "end"} <= set(a.keys()) and {"start", "end"} <= set(b.keys()):
            start = _interpolate_value(a.get("start"), b.get("start"), ratio)
            end = _interpolate_value(a.get("end"), b.get("end"), ratio)
            if not isinstance(start, dict) or not isinstance(end, dict):
                return None
            dx = float(end["x"]) - float(start["x"])
            dy = float(end["y"]) - float(start["y"])
            return {
                "start": start,
                "end": end,
                "angleDeg": math.degrees(math.atan2(dy, dx)),
                "lengthPx": math.hypot(dx, dy),
            }
    return a


def _blend(previous: float, current: float, alpha: float) -> float:
    return previous * (1.0 - alpha) + current * alpha


def _lerp(a: float, b: float, ratio: float) -> float:
    return a + (b - a) * ratio
