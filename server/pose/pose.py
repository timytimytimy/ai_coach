from __future__ import annotations

import math
import os
from typing import Any

import cv2

from server.accel import mediapipe_runtime_device, mediapipe_runtime_note


_KEYPOINT_ALIASES = {
    "nose": "nose",
    "left_shoulder": "leftShoulder",
    "right_shoulder": "rightShoulder",
    "left_elbow": "leftElbow",
    "right_elbow": "rightElbow",
    "left_wrist": "leftWrist",
    "right_wrist": "rightWrist",
    "left_hip": "leftHip",
    "right_hip": "rightHip",
    "left_knee": "leftKnee",
    "right_knee": "rightKnee",
    "left_ankle": "leftAnkle",
    "right_ankle": "rightAnkle",
}

_SKELETON = [
    ("leftShoulder", "rightShoulder"),
    ("leftShoulder", "leftHip"),
    ("rightShoulder", "rightHip"),
    ("leftHip", "rightHip"),
    ("leftShoulder", "leftElbow"),
    ("leftElbow", "leftWrist"),
    ("rightShoulder", "rightElbow"),
    ("rightElbow", "rightWrist"),
    ("leftHip", "leftKnee"),
    ("leftKnee", "leftAnkle"),
    ("rightHip", "rightKnee"),
    ("rightKnee", "rightAnkle"),
]

_TRUST_MIN_VISIBILITY = {
    "nose": 0.45,
    "leftShoulder": 0.48,
    "rightShoulder": 0.48,
    "leftElbow": 0.50,
    "rightElbow": 0.50,
    "leftWrist": 0.58,
    "rightWrist": 0.58,
    "leftHip": 0.48,
    "rightHip": 0.48,
    "leftKnee": 0.52,
    "rightKnee": 0.52,
    "leftAnkle": 0.60,
    "rightAnkle": 0.60,
}


class _PoseRoi:
    def __init__(self, x1: int, y1: int, x2: int, y2: int) -> None:
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2

    @property
    def width(self) -> int:
        return max(0, self.x2 - self.x1)

    @property
    def height(self) -> int:
        return max(0, self.y2 - self.y1)


def infer_pose(
    *,
    video_path: str,
    exercise: str,
    duration_ms: int,
    barbell_result: dict[str, Any] | None,
) -> dict[str, Any]:
    try:
        import mediapipe as mp  # type: ignore
    except ImportError:
        return _empty_pose_result(
            exercise=exercise,
            duration_ms=duration_ms,
            reason="mediapipe is not installed",
        )

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return _empty_pose_result(
            exercise=exercise,
            duration_ms=duration_ms,
            reason="failed to open video for pose inference",
        )

    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    source_fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    sample_fps = min(source_fps, max(1.0, _env_float("SSC_POSE_SAMPLE_FPS", 12.0)))
    every_n = max(1, int(round(source_fps / sample_fps))) if source_fps > 0 else 1
    min_visibility = max(0.0, min(1.0, _env_float("SSC_POSE_MIN_VISIBILITY", 0.45)))
    min_detection_confidence = max(0.1, min(1.0, _env_float("SSC_POSE_MIN_DETECTION_CONF", 0.5)))
    min_tracking_confidence = max(0.1, min(1.0, _env_float("SSC_POSE_MIN_TRACKING_CONF", 0.5)))
    model_complexity = max(0, min(2, _env_int("SSC_POSE_MODEL_COMPLEXITY", 1)))
    roi_half_life_ms = max(120, _env_int("SSC_POSE_ROI_MAX_GAP_MS", 450))
    anchors = _extract_barbell_anchors(barbell_result)

    pose_frames: list[dict[str, Any]] = []
    sampled_frames = 0
    detected_frames = 0
    left_score = 0.0
    right_score = 0.0
    last_pose_center: tuple[float, float] | None = None
    last_pose_box: _PoseRoi | None = None

    try:
        with mp.solutions.pose.Pose(
            static_image_mode=False,
            model_complexity=model_complexity,
            enable_segmentation=False,
            smooth_landmarks=True,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        ) as pose:
            frame_index = 0
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                if frame_index % every_n != 0:
                    frame_index += 1
                    continue
                sampled_frames += 1
                time_ms = int(round(frame_index * 1000.0 / source_fps)) if source_fps > 0 else int(round(sampled_frames * 1000.0 / sample_fps))
                roi = _pose_roi_for_time(
                    anchors=anchors,
                    time_ms=time_ms,
                    frame_width=frame_width,
                    frame_height=frame_height,
                    max_gap_ms=roi_half_life_ms,
                    last_pose_center=last_pose_center,
                    last_pose_box=last_pose_box,
                )
                anchor = _nearest_anchor(anchors, time_ms=time_ms, max_gap_ms=roi_half_life_ms)
                keypoints, used_roi = _infer_pose_with_fallbacks(
                    frame=frame,
                    pose=pose,
                    mp=mp,
                    min_visibility=min_visibility,
                    roi=roi,
                    anchor=anchor,
                    exercise=exercise,
                    frame_width=frame_width,
                    frame_height=frame_height,
                    last_pose_box=last_pose_box,
                )
                if keypoints:
                    detected_frames += 1
                    left_score += _side_visibility_score(keypoints, "left")
                    right_score += _side_visibility_score(keypoints, "right")
                    last_pose_center = _pose_center(keypoints)
                    last_pose_box = _pose_box(keypoints, frame_width=frame_width, frame_height=frame_height)
                pose_frames.append(
                    {
                        "timeMs": time_ms,
                        "keypoints": keypoints,
                        "tracked": bool(keypoints),
                        "roi": None if used_roi is None else {
                            "x1": used_roi.x1,
                            "y1": used_roi.y1,
                            "x2": used_roi.x2,
                            "y2": used_roi.y2,
                        },
                    }
                )
                frame_index += 1
    finally:
        cap.release()

    pose_frames = _fill_short_pose_gaps(pose_frames, max_gap_frames=3)
    pose_frames = _smooth_pose_frames(pose_frames, alpha=0.38)

    primary_side = "left" if left_score >= right_score else "right"
    detection_ratio = (detected_frames / sampled_frames) if sampled_frames else 0.0
    usable = detected_frames >= 8 and detection_ratio >= 0.35
    reason = "ok" if usable else "insufficient pose detections"
    return {
        "quality": {
            "usable": usable,
            "confidence": round(detection_ratio, 4),
            "reason": reason,
            "sampledFrames": sampled_frames,
            "detectedFrames": detected_frames,
            "device": mediapipe_runtime_device(),
            "runtimeNote": mediapipe_runtime_note(),
            "model": "mediapipe-pose",
            "jointQuality": _build_joint_quality_summary(pose_frames),
        },
        "keypoints": pose_frames,
        "overlay": {
            "frames": pose_frames,
            "frameWidth": frame_width,
            "frameHeight": frame_height,
            "sampleFps": sample_fps,
            "sourceFps": source_fps,
            "skeleton": _SKELETON,
        },
        "exercise": exercise,
        "durationMs": duration_ms,
        "primarySide": primary_side,
    }


def _empty_pose_result(*, exercise: str, duration_ms: int, reason: str) -> dict[str, Any]:
    return {
        "quality": {
            "usable": False,
            "confidence": 0.0,
            "reason": reason,
        },
        "keypoints": [],
        "overlay": {"frames": [], "skeleton": _SKELETON},
        "exercise": exercise,
        "durationMs": duration_ms,
    }


def _extract_keypoints(
    *,
    result: Any,
    mp: Any,
    width: int,
    height: int,
    min_visibility: float,
    offset_x: int,
    offset_y: int,
) -> dict[str, dict[str, float]]:
    pose_landmarks = getattr(result, "pose_landmarks", None)
    if pose_landmarks is None or not getattr(pose_landmarks, "landmark", None):
        return {}

    out: dict[str, dict[str, float]] = {}
    for raw_name, alias in _KEYPOINT_ALIASES.items():
        landmark_index = getattr(mp.solutions.pose.PoseLandmark, raw_name.upper())
        landmark = pose_landmarks.landmark[int(landmark_index)]
        visibility = float(getattr(landmark, "visibility", 0.0) or 0.0)
        presence = float(getattr(landmark, "presence", 1.0) or 1.0)
        if visibility < min_visibility or presence < min_visibility:
            continue
        x = min(max(float(landmark.x) * width + offset_x, 0.0), float(width + offset_x))
        y = min(max(float(landmark.y) * height + offset_y, 0.0), float(height + offset_y))
        out[alias] = {
            "x": x,
            "y": y,
            "visibility": visibility,
            "presence": presence,
            "z": float(getattr(landmark, "z", 0.0) or 0.0),
            "trusted": _is_trusted_point(alias, visibility),
        }
    return out


def _side_visibility_score(keypoints: dict[str, dict[str, float]], side: str) -> float:
    names = (
        f"{side}Shoulder",
        f"{side}Hip",
        f"{side}Knee",
        f"{side}Ankle",
    )
    total = 0.0
    count = 0
    for name in names:
        point = keypoints.get(name)
        if not isinstance(point, dict):
            continue
        visibility = point.get("visibility")
        if isinstance(visibility, (int, float)):
            total += float(visibility)
            count += 1
    return total / count if count else 0.0


def _is_trusted_point(alias: str, visibility: float) -> bool:
    return visibility >= _TRUST_MIN_VISIBILITY.get(alias, 0.5)


def _build_joint_quality_summary(
    pose_frames: list[dict[str, Any]],
) -> dict[str, dict[str, float | int]]:
    if not pose_frames:
        return {}

    sampled = len(pose_frames)
    counts = {
        alias: {"present": 0, "trusted": 0, "visibilitySum": 0.0}
        for alias in _TRUST_MIN_VISIBILITY
    }
    for frame in pose_frames:
        keypoints = frame.get("keypoints")
        if not isinstance(keypoints, dict):
            continue
        for alias, point in keypoints.items():
            if alias not in counts or not isinstance(point, dict):
                continue
            counts[alias]["present"] += 1
            visibility = point.get("visibility")
            if isinstance(visibility, (int, float)):
                counts[alias]["visibilitySum"] += float(visibility)
            if point.get("trusted") is True:
                counts[alias]["trusted"] += 1

    out: dict[str, dict[str, float | int]] = {}
    for alias, item in counts.items():
        present = int(item["present"])
        trusted = int(item["trusted"])
        avg_visibility = (float(item["visibilitySum"]) / present) if present else 0.0
        out[alias] = {
            "presentFrames": present,
            "trustedFrames": trusted,
            "presentCoverage": round(present / sampled, 4),
            "trustedCoverage": round(trusted / sampled, 4),
            "avgVisibility": round(avg_visibility, 4),
        }
    return out


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(float(raw))
    except ValueError:
        return default


def _extract_barbell_anchors(barbell_result: dict[str, Any] | None) -> list[dict[str, float]]:
    frames = barbell_result.get("frames") if isinstance(barbell_result, dict) else None
    if not isinstance(frames, list):
        return []
    out: list[dict[str, float]] = []
    for frame in frames:
        if not isinstance(frame, dict):
            continue
        time_ms = frame.get("timeMs")
        plate = frame.get("plate")
        if not isinstance(time_ms, (int, float)) or not isinstance(plate, dict):
            continue
        center = plate.get("center")
        bbox = plate.get("bbox")
        if not isinstance(center, dict) or not isinstance(bbox, dict):
            continue
        cx = center.get("x")
        cy = center.get("y")
        x1 = bbox.get("x1")
        x2 = bbox.get("x2")
        if not all(isinstance(v, (int, float)) for v in (cx, cy, x1, x2)):
            continue
        out.append(
            {
                "timeMs": float(time_ms),
                "cx": float(cx),
                "cy": float(cy),
                "plateWidth": max(1.0, float(x2) - float(x1)),
            }
        )
    return out


def _pose_roi_for_time(
    *,
    anchors: list[dict[str, float]],
    time_ms: int,
    frame_width: int,
    frame_height: int,
    max_gap_ms: int,
    last_pose_center: tuple[float, float] | None,
    last_pose_box: _PoseRoi | None,
) -> _PoseRoi | None:
    anchor = _nearest_anchor(anchors, time_ms=time_ms, max_gap_ms=max_gap_ms)
    if anchor is None or frame_width <= 0 or frame_height <= 0:
        return _expand_roi(last_pose_box, frame_width=frame_width, frame_height=frame_height, scale=1.25)

    cx = float(anchor["cx"])
    plate_width = max(20.0, float(anchor["plateWidth"]))
    cy = float(anchor["cy"])

    center_x = cx
    center_y = cy
    if last_pose_center is not None:
        px, py = last_pose_center
        if abs(px - cx) <= max(frame_width * 0.28, plate_width * 3.5):
            center_x = px
        if abs(py - cy) <= frame_height * 0.40:
            center_y = py
    elif last_pose_box is not None:
        center_x = (last_pose_box.x1 + last_pose_box.x2) / 2.0
        center_y = (last_pose_box.y1 + last_pose_box.y2) / 2.0

    half_width = max(frame_width * 0.24, plate_width * 2.8)
    top_span = max(frame_height * 0.48, plate_width * 3.2)
    bottom_span = max(frame_height * 0.36, plate_width * 2.8)

    x1 = center_x - half_width
    x2 = center_x + half_width

    x1_i = max(0, int(math.floor(x1)))
    x2_i = min(frame_width, int(math.ceil(x2)))
    min_width = max(160, int(frame_width * 0.35))
    if x2_i - x1_i < min_width:
        pad = (min_width - (x2_i - x1_i)) // 2 + 1
        x1_i = max(0, x1_i - pad)
        x2_i = min(frame_width, x2_i + pad)

    return _PoseRoi(
        x1=x1_i,
        y1=max(0, int(math.floor(center_y - top_span))),
        x2=x2_i,
        y2=min(frame_height, int(math.ceil(center_y + bottom_span))),
    )


def _infer_pose_with_fallbacks(
    *,
    frame: Any,
    pose: Any,
    mp: Any,
    min_visibility: float,
    roi: _PoseRoi | None,
    anchor: dict[str, float] | None,
    exercise: str,
    frame_width: int,
    frame_height: int,
    last_pose_box: _PoseRoi | None,
) -> tuple[dict[str, dict[str, float]], _PoseRoi | None]:
    candidates: list[_PoseRoi | None] = []
    if roi is not None and roi.width > 24 and roi.height > 24:
        candidates.append(roi)
        expanded = _expand_roi(roi, frame_width=frame_width, frame_height=frame_height, scale=1.18)
        if expanded is not None:
            candidates.append(expanded)
    if last_pose_box is not None:
        prev_box = _expand_roi(last_pose_box, frame_width=frame_width, frame_height=frame_height, scale=1.15)
        if prev_box is not None:
            candidates.append(prev_box)
    candidates.append(None)

    seen: set[tuple[int, int, int, int] | None] = set()
    for candidate in candidates:
        key = None if candidate is None else (candidate.x1, candidate.y1, candidate.x2, candidate.y2)
        if key in seen:
            continue
        seen.add(key)
        keypoints = _infer_keypoints_for_region(
            frame=frame,
            pose=pose,
            mp=mp,
            min_visibility=min_visibility,
            roi=candidate,
            frame_width=frame_width,
            frame_height=frame_height,
        )
        if keypoints and _pose_matches_barbell(
            keypoints=keypoints,
            anchor=anchor,
            exercise=exercise,
            frame_width=frame_width,
            frame_height=frame_height,
        ):
            return keypoints, candidate
    return {}, roi


def _infer_keypoints_for_region(
    *,
    frame: Any,
    pose: Any,
    mp: Any,
    min_visibility: float,
    roi: _PoseRoi | None,
    frame_width: int,
    frame_height: int,
) -> dict[str, dict[str, float]]:
    frame_for_pose = frame
    pose_width = frame_width
    pose_height = frame_height
    offset_x = 0
    offset_y = 0
    if roi is not None and roi.width > 24 and roi.height > 24:
        frame_for_pose = frame[roi.y1:roi.y2, roi.x1:roi.x2]
        pose_width = roi.width
        pose_height = roi.height
        offset_x = roi.x1
        offset_y = roi.y1
    frame_rgb = cv2.cvtColor(frame_for_pose, cv2.COLOR_BGR2RGB)
    result = pose.process(frame_rgb)
    return _extract_keypoints(
        result=result,
        mp=mp,
        width=pose_width,
        height=pose_height,
        min_visibility=min_visibility,
        offset_x=offset_x,
        offset_y=offset_y,
    )


def _expand_roi(
    roi: _PoseRoi | None,
    *,
    frame_width: int,
    frame_height: int,
    scale: float,
) -> _PoseRoi | None:
    if roi is None:
        return None
    cx = (roi.x1 + roi.x2) / 2.0
    cy = (roi.y1 + roi.y2) / 2.0
    half_w = max(32.0, roi.width * scale / 2.0)
    half_h = max(48.0, roi.height * scale / 2.0)
    return _PoseRoi(
        x1=max(0, int(math.floor(cx - half_w))),
        y1=max(0, int(math.floor(cy - half_h))),
        x2=min(frame_width, int(math.ceil(cx + half_w))),
        y2=min(frame_height, int(math.ceil(cy + half_h))),
    )


def _nearest_anchor(
    anchors: list[dict[str, float]],
    *,
    time_ms: int,
    max_gap_ms: int,
) -> dict[str, float] | None:
    best: dict[str, float] | None = None
    best_delta = float(max_gap_ms) + 1.0
    for anchor in anchors:
        delta = abs(float(anchor["timeMs"]) - float(time_ms))
        if delta < best_delta:
            best = anchor
            best_delta = delta
    return best if best is not None and best_delta <= max_gap_ms else None


def _pose_center(keypoints: dict[str, dict[str, float]]) -> tuple[float, float] | None:
    names = (
        "leftShoulder",
        "rightShoulder",
        "leftHip",
        "rightHip",
    )
    xs: list[float] = []
    ys: list[float] = []
    for name in names:
        point = keypoints.get(name)
        if not isinstance(point, dict):
            continue
        x = point.get("x")
        y = point.get("y")
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            xs.append(float(x))
            ys.append(float(y))
    if not xs or not ys:
        return None
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def _pose_box(
    keypoints: dict[str, dict[str, float]],
    *,
    frame_width: int,
    frame_height: int,
) -> _PoseRoi | None:
    xs: list[float] = []
    ys: list[float] = []
    for point in keypoints.values():
        if not isinstance(point, dict):
            continue
        x = point.get("x")
        y = point.get("y")
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            xs.append(float(x))
            ys.append(float(y))
    if not xs or not ys:
        return None
    pad_x = max(28.0, (max(xs) - min(xs)) * 0.25)
    pad_y = max(36.0, (max(ys) - min(ys)) * 0.22)
    return _PoseRoi(
        x1=max(0, int(math.floor(min(xs) - pad_x))),
        y1=max(0, int(math.floor(min(ys) - pad_y))),
        x2=min(frame_width, int(math.ceil(max(xs) + pad_x))),
        y2=min(frame_height, int(math.ceil(max(ys) + pad_y))),
    )


def _fill_short_pose_gaps(
    frames: list[dict[str, Any]],
    *,
    max_gap_frames: int,
) -> list[dict[str, Any]]:
    out = [dict(frame) for frame in frames]
    i = 0
    while i < len(out):
        current = out[i]
        if current.get("keypoints"):
            i += 1
            continue
        start_gap = i
        while i < len(out) and not out[i].get("keypoints"):
            i += 1
        end_gap = i - 1
        gap_len = end_gap - start_gap + 1
        prev_index = start_gap - 1
        next_index = i
        if gap_len > max_gap_frames or prev_index < 0 or next_index >= len(out):
            continue
        prev_points = out[prev_index].get("keypoints")
        next_points = out[next_index].get("keypoints")
        if not isinstance(prev_points, dict) or not isinstance(next_points, dict):
            continue
        common_keys = set(prev_points).intersection(next_points)
        if len(common_keys) < 4:
            continue
        for gap_index in range(start_gap, end_gap + 1):
            ratio = (gap_index - prev_index) / (next_index - prev_index)
            interpolated: dict[str, dict[str, float]] = {}
            for key in common_keys:
                prev_point = prev_points.get(key)
                next_point = next_points.get(key)
                if not isinstance(prev_point, dict) or not isinstance(next_point, dict):
                    continue
                if not all(isinstance(prev_point.get(k), (int, float)) and isinstance(next_point.get(k), (int, float)) for k in ("x", "y")):
                    continue
                interpolated[key] = {
                    "x": float(prev_point["x"]) + (float(next_point["x"]) - float(prev_point["x"])) * ratio,
                    "y": float(prev_point["y"]) + (float(next_point["y"]) - float(prev_point["y"])) * ratio,
                    "visibility": min(
                        float(prev_point.get("visibility", 1.0)),
                        float(next_point.get("visibility", 1.0)),
                    ),
                    "presence": min(
                        float(prev_point.get("presence", 1.0)),
                        float(next_point.get("presence", 1.0)),
                    ),
                    "z": float(prev_point.get("z", 0.0))
                    + (float(next_point.get("z", 0.0)) - float(prev_point.get("z", 0.0))) * ratio,
                }
            if len(interpolated) >= 4:
                out[gap_index]["keypoints"] = interpolated
                out[gap_index]["tracked"] = True
                out[gap_index]["interpolated"] = True
    return out


def _smooth_pose_frames(
    frames: list[dict[str, Any]],
    *,
    alpha: float,
) -> list[dict[str, Any]]:
    out = [dict(frame) for frame in frames]
    state: dict[str, tuple[float, float, float]] = {}
    for frame in out:
        keypoints = frame.get("keypoints")
        if not isinstance(keypoints, dict) or not keypoints:
            continue
        smoothed: dict[str, dict[str, float]] = {}
        for key, point in keypoints.items():
            if not isinstance(point, dict):
                continue
            x = point.get("x")
            y = point.get("y")
            if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
                continue
            px, py, pz = state.get(key, (float(x), float(y), float(point.get("z", 0.0) or 0.0)))
            nx = px + (float(x) - px) * alpha
            ny = py + (float(y) - py) * alpha
            nz = pz + (float(point.get("z", 0.0) or 0.0) - pz) * alpha
            state[key] = (nx, ny, nz)
            smoothed[key] = {
                **point,
                "x": nx,
                "y": ny,
                "z": nz,
            }
        frame["keypoints"] = smoothed
    return out


def _pose_matches_barbell(
    *,
    keypoints: dict[str, dict[str, float]],
    anchor: dict[str, float] | None,
    exercise: str,
    frame_width: int,
    frame_height: int,
) -> bool:
    if anchor is None:
        return True
    center = _pose_center(keypoints)
    if center is None:
        return False

    pose_x, pose_y = center
    bar_x = float(anchor["cx"])
    bar_y = float(anchor["cy"])
    plate_width = max(20.0, float(anchor["plateWidth"]))

    dx = abs(pose_x - bar_x)
    dy = pose_y - bar_y

    max_dx = max(frame_width * 0.18, plate_width * 2.2)
    if exercise == "bench":
        min_dy = -max(frame_height * 0.18, plate_width * 1.5)
        max_dy = max(frame_height * 0.22, plate_width * 2.2)
    else:
        min_dy = -max(frame_height * 0.12, plate_width * 1.4)
        max_dy = max(frame_height * 0.40, plate_width * 4.8)
    if not (dx <= max_dx and min_dy <= dy <= max_dy):
        return False

    # The lifter interacting with the bar should keep at least one upper-limb
    # landmark reasonably near the plate/bar end. This rejects bystanders whose
    # torso falls inside the ROI but whose hands/arms are nowhere near the bar.
    return _upper_limb_matches_barbell(
        keypoints=keypoints,
        anchor=anchor,
        exercise=exercise,
        frame_width=frame_width,
        frame_height=frame_height,
    )


def _upper_limb_matches_barbell(
    *,
    keypoints: dict[str, dict[str, float]],
    anchor: dict[str, float],
    exercise: str,
    frame_width: int,
    frame_height: int,
) -> bool:
    bar_x = float(anchor["cx"])
    bar_y = float(anchor["cy"])
    plate_width = max(20.0, float(anchor["plateWidth"]))

    arm_points = _arm_anchor_points(keypoints)
    if not arm_points:
        # When upper-limb landmarks are missing, don't hard reject the pose.
        # MediaPipe can lose wrists/elbows under occlusion, especially on
        # side-view squats and rack-heavy footage.
        return True

    max_dx = max(frame_width * 0.15, plate_width * 2.0)
    if exercise == "bench":
        max_dy = max(frame_height * 0.18, plate_width * 2.2)
    else:
        max_dy = max(frame_height * 0.24, plate_width * 3.2)

    for point in arm_points:
        dx = abs(float(point["x"]) - bar_x)
        dy = abs(float(point["y"]) - bar_y)
        if dx <= max_dx and dy <= max_dy:
            return True
    return False


def _arm_anchor_points(keypoints: dict[str, dict[str, float]]) -> list[dict[str, float]]:
    primary_names = (
        "leftWrist",
        "rightWrist",
        "leftElbow",
        "rightElbow",
    )
    fallback_names = (
        "leftShoulder",
        "rightShoulder",
    )

    out: list[dict[str, float]] = []
    for name in primary_names:
        point = keypoints.get(name)
        if not isinstance(point, dict):
            continue
        x = point.get("x")
        y = point.get("y")
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            out.append({"x": float(x), "y": float(y)})
    if out:
        return out

    for name in fallback_names:
        point = keypoints.get(name)
        if not isinstance(point, dict):
            continue
        x = point.get("x")
        y = point.get("y")
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            out.append({"x": float(x), "y": float(y)})
    return out
