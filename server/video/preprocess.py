from __future__ import annotations

import base64
from typing import Any

import cv2


def extract_llm_keyframes(
    *,
    video_path: str,
    duration_ms: int | None,
    phases: list[dict[str, Any]],
    rule_analysis: dict[str, Any] | None,
    max_frames: int = 6,
    max_edge: int = 768,
    jpeg_quality: int = 82,
) -> list[dict[str, Any]]:
    frame_times = _select_keyframe_times(
        duration_ms=duration_ms,
        phases=phases,
        rule_analysis=rule_analysis,
        max_frames=max_frames,
    )
    if not frame_times:
        return []

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return []

    out: list[dict[str, Any]] = []
    try:
        for time_ms in frame_times:
            cap.set(cv2.CAP_PROP_POS_MSEC, float(time_ms))
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            frame = _resize_frame(frame, max_edge=max_edge)
            ok, buf = cv2.imencode(
                ".jpg",
                frame,
                [int(cv2.IMWRITE_JPEG_QUALITY), int(jpeg_quality)],
            )
            if not ok:
                continue
            encoded = base64.b64encode(buf.tobytes()).decode("ascii")
            out.append(
                {
                    "timeMs": int(time_ms),
                    "mimeType": "image/jpeg",
                    "dataUrl": f"data:image/jpeg;base64,{encoded}",
                }
            )
    finally:
        cap.release()
    return out


def _select_keyframe_times(
    *,
    duration_ms: int | None,
    phases: list[dict[str, Any]],
    rule_analysis: dict[str, Any] | None,
    max_frames: int,
) -> list[int]:
    candidates: list[int] = []
    issues = rule_analysis.get("issues") if isinstance(rule_analysis, dict) else None
    if isinstance(issues, list):
        for issue in issues[:3]:
            if not isinstance(issue, dict):
                continue
            tr = issue.get("timeRangeMs")
            if not isinstance(tr, dict):
                continue
            start = tr.get("start")
            end = tr.get("end")
            if isinstance(start, (int, float)) and isinstance(end, (int, float)):
                mid = int((float(start) + float(end)) / 2.0)
                candidates.extend([int(start), mid, int(end)])

    for phase in phases[:8]:
        if not isinstance(phase, dict):
            continue
        start = phase.get("startMs")
        end = phase.get("endMs")
        if isinstance(start, int) and isinstance(end, int) and end >= start:
            candidates.append((start + end) // 2)

    if isinstance(duration_ms, int) and duration_ms > 0:
        candidates.extend([0, duration_ms // 2, max(0, duration_ms - 1)])

    normalized: list[int] = []
    for t in sorted(set(max(0, int(v)) for v in candidates)):
        if not normalized or abs(t - normalized[-1]) >= 400:
            normalized.append(t)

    if len(normalized) <= max_frames:
        return normalized

    if max_frames <= 1:
        return [normalized[len(normalized) // 2]]

    step = (len(normalized) - 1) / float(max_frames - 1)
    picked = []
    for i in range(max_frames):
        picked.append(normalized[round(i * step)])
    return sorted(set(picked))


def _resize_frame(frame: Any, *, max_edge: int) -> Any:
    h, w = frame.shape[:2]
    longest = max(h, w)
    if longest <= max_edge:
        return frame
    scale = max_edge / float(longest)
    return cv2.resize(frame, (int(round(w * scale)), int(round(h * scale))))
