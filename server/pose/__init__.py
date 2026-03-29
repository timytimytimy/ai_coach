from __future__ import annotations

import os
from typing import Any

from server.pose.pose import infer_pose as infer_pose_mediapipe
from server.pose.pose_v2 import infer_pose_v2


def get_pose_impl() -> str:
    impl = (os.environ.get("SSC_POSE_IMPL") or "mediapipe").strip().lower()
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
    if get_pose_impl() == "rtmpose":
        return infer_pose_v2(
            video_path=video_path,
            exercise=exercise,
            duration_ms=duration_ms,
            barbell_result=barbell_result,
        )
    return infer_pose_mediapipe(
        video_path=video_path,
        exercise=exercise,
        duration_ms=duration_ms,
        barbell_result=barbell_result,
    )


__all__ = ["get_pose_impl", "infer_pose", "infer_pose_mediapipe", "infer_pose_v2"]
