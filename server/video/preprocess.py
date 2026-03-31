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


def extract_video_classification_frames(
    *,
    video_path: str,
    duration_ms: int | None,
    max_frames: int = 5,
    max_edge: int = 640,
    jpeg_quality: int = 78,
) -> list[dict[str, Any]]:
    frame_times = _select_classification_frame_times(
        duration_ms=duration_ms,
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
                start_i = int(float(start))
                end_i = int(float(end))
                if end_i < start_i:
                    start_i, end_i = end_i, start_i
                window = max(1, end_i - start_i)
                candidates.extend(
                    [
                        max(0, start_i - window // 2),
                        start_i,
                        start_i + window // 4,
                        start_i + window // 2,
                        start_i + (window * 3) // 4,
                        end_i,
                        end_i + window // 2,
                    ]
                )

    rep_phase_candidates = _select_rep_phase_times(phases=phases)
    candidates.extend(rep_phase_candidates)

    if isinstance(duration_ms, int) and duration_ms > 0:
        ratios = [0.03, 0.12, 0.22, 0.35, 0.5, 0.65, 0.78, 0.9, 0.97]
        candidates.extend(
            max(0, min(duration_ms - 1, int(round(duration_ms * ratio))))
            for ratio in ratios
        )

    normalized: list[int] = []
    for t in sorted(set(max(0, int(v)) for v in candidates)):
        if not normalized or abs(t - normalized[-1]) >= 180:
            normalized.append(t)

    if len(normalized) <= max_frames:
        return normalized

    if max_frames <= 1:
        return [normalized[len(normalized) // 2]]

    if rep_phase_candidates:
        prioritized: list[int] = []
        for t in rep_phase_candidates:
            t = max(0, int(t))
            if t in normalized and t not in prioritized:
                prioritized.append(t)
            if len(prioritized) >= max_frames:
                break
        if len(prioritized) >= max_frames:
            return sorted(prioritized[:max_frames])
        remaining = [t for t in normalized if t not in prioritized]
        slots = max_frames - len(prioritized)
        if remaining and slots > 0:
            if slots == 1:
                prioritized.append(remaining[len(remaining) // 2])
            else:
                step = (len(remaining) - 1) / float(max(slots - 1, 1))
                for i in range(slots):
                    prioritized.append(remaining[round(i * step)])
        return sorted(set(prioritized[:max_frames]))

    step = (len(normalized) - 1) / float(max_frames - 1)
    picked = [normalized[round(i * step)] for i in range(max_frames)]
    return sorted(set(picked))


def _select_rep_phase_times(*, phases: list[dict[str, Any]]) -> list[int]:
    if not phases:
        return []

    ordered: list[int] = []
    phase_priority = {
        "descent": 0,
        "bottom": 1,
        "chest_touch": 1,
        "slack_pull": 0,
        "floor_break": 1,
        "ascent": 2,
        "press": 2,
        "knee_pass": 3,
        "lockout": 4,
    }
    grouped: dict[int, list[dict[str, Any]]] = {}
    for phase in phases:
        if not isinstance(phase, dict):
            continue
        rep_index = phase.get("repIndex")
        start = phase.get("startMs")
        end = phase.get("endMs")
        if not isinstance(rep_index, int) or not isinstance(start, int) or not isinstance(end, int):
            continue
        if end < start:
            continue
        grouped.setdefault(rep_index, []).append(phase)

    for rep_index in sorted(grouped):
        rep_phases = sorted(
            grouped[rep_index],
            key=lambda item: (
                int(item.get("startMs") or 0),
                phase_priority.get(str(item.get("name") or ""), 99),
            ),
        )
        for phase in rep_phases:
            start = int(phase["startMs"])
            end = int(phase["endMs"])
            span = max(1, end - start)
            name = str(phase.get("name") or "")
            samples = [start + span // 2]
            if name in {"descent", "ascent", "press", "knee_pass"}:
                samples = [start, start + span // 2, end]
            elif name in {"bottom", "chest_touch", "slack_pull", "floor_break", "lockout"}:
                samples = [start, start + span // 2]
            for t in samples:
                if not ordered or abs(t - ordered[-1]) >= 120:
                    ordered.append(t)
    return ordered


def _select_classification_frame_times(
    *,
    duration_ms: int | None,
    max_frames: int,
) -> list[int]:
    if not isinstance(duration_ms, int) or duration_ms <= 0:
        return []
    ratios = [0.08, 0.24, 0.45, 0.68, 0.86]
    times = [max(0, min(duration_ms - 1, int(round(duration_ms * ratio)))) for ratio in ratios[:max_frames]]
    normalized: list[int] = []
    for t in sorted(set(times)):
        if not normalized or abs(t - normalized[-1]) >= 350:
            normalized.append(t)
    return normalized[:max_frames]


def _resize_frame(frame: Any, *, max_edge: int) -> Any:
    h, w = frame.shape[:2]
    longest = max(h, w)
    if longest <= max_edge:
        return frame
    scale = max_edge / float(longest)
    return cv2.resize(frame, (int(round(w * scale)), int(round(h * scale))))
