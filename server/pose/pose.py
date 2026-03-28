from __future__ import annotations

import math
import os
from typing import Any

import cv2


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
                )
                frame_for_pose = frame
                pose_width = frame_width
                pose_height = frame_height
                if roi is not None and roi.width > 24 and roi.height > 24:
                    frame_for_pose = frame[roi.y1:roi.y2, roi.x1:roi.x2]
                    pose_width = roi.width
                    pose_height = roi.height

                frame_rgb = cv2.cvtColor(frame_for_pose, cv2.COLOR_BGR2RGB)
                result = pose.process(frame_rgb)
                keypoints = _extract_keypoints(
                    result=result,
                    mp=mp,
                    width=pose_width,
                    height=pose_height,
                    min_visibility=min_visibility,
                    offset_x=0 if roi is None else roi.x1,
                    offset_y=0 if roi is None else roi.y1,
                )
                anchor = _nearest_anchor(anchors, time_ms=time_ms, max_gap_ms=roi_half_life_ms)
                if keypoints and not _pose_matches_barbell(
                    keypoints=keypoints,
                    anchor=anchor,
                    exercise=exercise,
                    frame_width=frame_width,
                    frame_height=frame_height,
                ):
                    keypoints = {}
                if keypoints:
                    detected_frames += 1
                    left_score += _side_visibility_score(keypoints, "left")
                    right_score += _side_visibility_score(keypoints, "right")
                    last_pose_center = _pose_center(keypoints)
                pose_frames.append(
                    {
                        "timeMs": time_ms,
                        "keypoints": keypoints,
                        "tracked": bool(keypoints),
                        "roi": None if roi is None else {
                            "x1": roi.x1,
                            "y1": roi.y1,
                            "x2": roi.x2,
                            "y2": roi.y2,
                        },
                    }
                )
                frame_index += 1
    finally:
        cap.release()

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
) -> _PoseRoi | None:
    anchor = _nearest_anchor(anchors, time_ms=time_ms, max_gap_ms=max_gap_ms)
    if anchor is None or frame_width <= 0 or frame_height <= 0:
        return None

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

    return dx <= max_dx and min_dy <= dy <= max_dy
