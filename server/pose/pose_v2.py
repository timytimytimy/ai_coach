from __future__ import annotations

import os
import ssl
from typing import Any

import cv2

from server.accel import default_rtmpose_backend, default_rtmpose_device
from server.pose.pose import (
    _PoseRoi,
    _build_joint_quality_summary,
    _empty_pose_result,
    _expand_roi,
    _extract_barbell_anchors,
    _fill_short_pose_gaps,
    _is_trusted_point,
    _nearest_anchor,
    _pose_box,
    _pose_center,
    _pose_matches_barbell,
    _pose_roi_for_time,
    _side_visibility_score,
    _smooth_pose_frames,
)

_RTMPOSE_KEYPOINTS = {
    0: "nose",
    5: "leftShoulder",
    6: "rightShoulder",
    7: "leftElbow",
    8: "rightElbow",
    9: "leftWrist",
    10: "rightWrist",
    11: "leftHip",
    12: "rightHip",
    13: "leftKnee",
    14: "rightKnee",
    15: "leftAnkle",
    16: "rightAnkle",
}

_RTMPOSE_SKELETON = [
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

_body_model: Any = None
_DISTAL_MIN_SCORES = {
    "leftWrist": 0.50,
    "rightWrist": 0.50,
    "leftAnkle": 0.58,
    "rightAnkle": 0.58,
}


def infer_pose_v2(
    *,
    video_path: str,
    exercise: str,
    duration_ms: int,
    barbell_result: dict[str, Any] | None,
) -> dict[str, Any]:
    try:
        body = _get_rtmpose_body()
    except Exception as exc:
        return _empty_pose_result(
            exercise=exercise,
            duration_ms=duration_ms,
            reason=f"rtmpose unavailable: {exc}",
        )

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return _empty_pose_result(
            exercise=exercise,
            duration_ms=duration_ms,
            reason="failed to open video for RTMPose inference",
        )

    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    source_fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    sample_fps = min(source_fps, max(1.0, _env_float("SSC_RTMPOSE_SAMPLE_FPS", 12.0)))
    every_n = max(1, int(round(source_fps / sample_fps))) if source_fps > 0 else 1
    min_score = max(0.0, min(1.0, _env_float("SSC_RTMPOSE_MIN_SCORE", 0.30)))
    roi_max_gap_ms = max(120, _env_int("SSC_RTMPOSE_ROI_MAX_GAP_MS", 450))

    anchors = _extract_barbell_anchors(barbell_result)
    pose_frames: list[dict[str, Any]] = []
    sampled_frames = 0
    detected_frames = 0
    left_score = 0.0
    right_score = 0.0
    last_pose_center: tuple[float, float] | None = None
    last_pose_box: _PoseRoi | None = None

    try:
        frame_index = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if frame_index % every_n != 0:
                frame_index += 1
                continue

            sampled_frames += 1
            time_ms = (
                int(round(frame_index * 1000.0 / source_fps))
                if source_fps > 0
                else int(round(sampled_frames * 1000.0 / sample_fps))
            )
            anchor = _nearest_anchor(anchors, time_ms=time_ms, max_gap_ms=roi_max_gap_ms)
            roi = _pose_roi_for_time(
                anchors=anchors,
                time_ms=time_ms,
                frame_width=frame_width,
                frame_height=frame_height,
                max_gap_ms=roi_max_gap_ms,
                last_pose_center=last_pose_center,
                last_pose_box=last_pose_box,
            )

            keypoints, used_roi = _infer_best_pose_candidate(
                frame=frame,
                body=body,
                anchor=anchor,
                exercise=exercise,
                frame_width=frame_width,
                frame_height=frame_height,
                min_score=min_score,
                roi=roi,
                last_pose_center=last_pose_center,
            )
            if keypoints:
                detected_frames += 1
                left_score += _side_visibility_score(keypoints, "left")
                right_score += _side_visibility_score(keypoints, "right")
                last_pose_center = _pose_center(keypoints)
                last_pose_box = _pose_box(
                    keypoints,
                    frame_width=frame_width,
                    frame_height=frame_height,
                )

            pose_frames.append(
                {
                    "timeMs": time_ms,
                    "keypoints": keypoints,
                    "tracked": bool(keypoints),
                    "roi": None
                    if used_roi is None
                    else {
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
    pose_frames = _smooth_pose_frames(pose_frames, alpha=0.42)

    primary_side = "left" if left_score >= right_score else "right"
    detection_ratio = (detected_frames / sampled_frames) if sampled_frames else 0.0
    usable = detected_frames >= 8 and detection_ratio >= 0.35
    reason = "ok" if usable else "insufficient RTMPose detections"

    return {
        "quality": {
            "usable": usable,
            "confidence": round(detection_ratio, 4),
            "reason": reason,
            "sampledFrames": sampled_frames,
            "detectedFrames": detected_frames,
            "model": "rtmpose-topdown",
            "backend": getattr(body, "backend", default_rtmpose_backend()),
            "device": getattr(body, "device", default_rtmpose_device()),
            "jointQuality": _build_joint_quality_summary(pose_frames),
        },
        "keypoints": pose_frames,
        "overlay": {
            "frames": pose_frames,
            "frameWidth": frame_width,
            "frameHeight": frame_height,
            "sampleFps": sample_fps,
            "sourceFps": source_fps,
            "skeleton": _RTMPOSE_SKELETON,
        },
        "exercise": exercise,
        "durationMs": duration_ms,
        "primarySide": primary_side,
    }


def _get_rtmpose_body() -> Any:
    global _body_model
    if _body_model is not None:
        return _body_model

    if os.environ.get("SSC_RTMPOSE_INSECURE_DOWNLOAD", "1") == "1":
        ssl._create_default_https_context = ssl._create_unverified_context

    from rtmlib import Body

    backend = default_rtmpose_backend()
    device = default_rtmpose_device()
    _body_model = Body(
        mode=os.environ.get("SSC_RTMPOSE_MODE", "lightweight"),
        backend=backend,
        device=device,
    )
    return _body_model


def _infer_best_pose_candidate(
    *,
    frame: Any,
    body: Any,
    anchor: dict[str, float] | None,
    exercise: str,
    frame_width: int,
    frame_height: int,
    min_score: float,
    roi: _PoseRoi | None,
    last_pose_center: tuple[float, float] | None,
) -> tuple[dict[str, dict[str, float]], _PoseRoi | None]:
    candidates: list[_PoseRoi | None] = []
    if roi is not None:
        candidates.append(roi)
        expanded = _expand_roi(roi, frame_width=frame_width, frame_height=frame_height, scale=1.18)
        if expanded is not None:
            candidates.append(expanded)
    candidates.append(None)

    seen: set[tuple[int, int, int, int] | None] = set()
    best_points: dict[str, dict[str, float]] = {}
    best_roi: _PoseRoi | None = None
    best_score = float("-inf")

    for candidate in candidates:
        key = None if candidate is None else (candidate.x1, candidate.y1, candidate.x2, candidate.y2)
        if key in seen:
            continue
        seen.add(key)

        frame_for_pose = frame
        offset_x = 0
        offset_y = 0
        used_roi = candidate
        if candidate is not None and candidate.width > 24 and candidate.height > 24:
            frame_for_pose = frame[candidate.y1:candidate.y2, candidate.x1:candidate.x2]
            offset_x = candidate.x1
            offset_y = candidate.y1

        keypoints_arr, scores_arr = body(frame_for_pose)
        if len(keypoints_arr) == 0:
            continue

        for person_points, person_scores in zip(keypoints_arr, scores_arr):
            mapped = _map_rtmpose_person(
                person_points=person_points,
                person_scores=person_scores,
                min_score=min_score,
                offset_x=offset_x,
                offset_y=offset_y,
            )
            if not mapped:
                continue
            if not _pose_matches_barbell(
                keypoints=mapped,
                anchor=anchor,
                exercise=exercise,
                frame_width=frame_width,
                frame_height=frame_height,
            ):
                continue
            candidate_score = _score_pose_candidate(
                keypoints=mapped,
                anchor=anchor,
                last_pose_center=last_pose_center,
            )
            if candidate_score > best_score:
                best_points = mapped
                best_score = candidate_score
                best_roi = used_roi

    return best_points, best_roi


def _map_rtmpose_person(
    *,
    person_points: Any,
    person_scores: Any,
    min_score: float,
    offset_x: int,
    offset_y: int,
) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for index, alias in _RTMPOSE_KEYPOINTS.items():
        if index >= len(person_points) or index >= len(person_scores):
            continue
        x, y = person_points[index]
        score = float(person_scores[index])
        required_score = max(min_score, _DISTAL_MIN_SCORES.get(alias, min_score))
        if score < required_score:
            continue
        out[alias] = {
            "x": float(x) + offset_x,
            "y": float(y) + offset_y,
            "visibility": score,
            "presence": score,
            "z": 0.0,
            "trusted": _is_trusted_point(alias, score),
        }
    return out


def _score_pose_candidate(
    *,
    keypoints: dict[str, dict[str, float]],
    anchor: dict[str, float] | None,
    last_pose_center: tuple[float, float] | None,
) -> float:
    center = _pose_center(keypoints)
    if center is None:
        return float("-inf")

    score = 0.0
    if anchor is not None:
        dx = abs(center[0] - float(anchor["cx"]))
        dy = abs(center[1] - float(anchor["cy"]))
        score -= dx * 1.0
        score -= dy * 0.35
    if last_pose_center is not None:
        score -= abs(center[0] - last_pose_center[0]) * 0.9
        score -= abs(center[1] - last_pose_center[1]) * 0.4

    score += _side_visibility_score(keypoints, "left") * 10.0
    score += _side_visibility_score(keypoints, "right") * 10.0
    score += len(keypoints) * 3.0
    return score


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
