from __future__ import annotations

import os
from typing import Any

from server.pose.pose import infer_pose as infer_pose_mediapipe
from server.pose.pose_v2 import infer_pose_v2
from server.pose.structure import build_pose_structures


def get_pose_impl() -> str:
    impl = (os.environ.get("SSC_POSE_IMPL") or "mediapipe").strip().lower()
    if impl in {"none", "off", "disabled", "disable"}:
        return "none"
    if impl in {"rtmpose", "rtmpose_v2", "v2"}:
        return "rtmpose"
    return "mediapipe"


def infer_pose(
    *,
    video_path: str,
    exercise: str,
    duration_ms: int,
    barbell_result: dict[str, Any] | None,
) -> dict[str, Any]:
    pose_impl = get_pose_impl()
    if pose_impl == "none":
        pose_result = {
            "model": "disabled",
            "primarySide": "left",
            "keypoints": [],
            "quality": {
                "usable": False,
                "confidence": 0.0,
                "detectedFrames": 0,
                "sampledFrames": 0,
                "jointQuality": {},
            },
        }
    elif pose_impl == "rtmpose":
        pose_result = infer_pose_v2(
            video_path=video_path,
            exercise=exercise,
            duration_ms=duration_ms,
            barbell_result=barbell_result,
        )
    else:
        pose_result = infer_pose_mediapipe(
            video_path=video_path,
            exercise=exercise,
            duration_ms=duration_ms,
            barbell_result=barbell_result,
        )
    pose_result["structures"] = build_pose_structures(
        exercise=exercise,
        pose_result=pose_result,
    )
    return pose_result


__all__ = [
    "get_pose_impl",
    "infer_pose",
    "infer_pose_mediapipe",
    "infer_pose_v2",
    "build_pose_structures",
]
