from __future__ import annotations

from typing import Any

import cv2


def analyze_video_quality(*, video_path: str) -> dict[str, Any]:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return _empty_quality_result("无法打开视频，未能完成质量检查。")

    source_fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    sample_fps = min(source_fps, max(1.0, _env_float("SSC_VIDEO_QUALITY_SAMPLE_FPS", 3.0)))
    every_n = max(1, int(round(source_fps / sample_fps))) if source_fps > 0 else 1

    sampled_frames = 0
    brightness_values: list[float] = []
    contrast_values: list[float] = []
    blur_values: list[float] = []
    dark_frame_count = 0
    overexposed_frame_count = 0

    try:
        frame_index = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if frame_index % every_n != 0:
                frame_index += 1
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            sampled_frames += 1

            brightness = float(gray.mean())
            contrast = float(gray.std())
            blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            dark_ratio = float((gray < 28).mean())
            overexposed_ratio = float((gray > 245).mean())

            brightness_values.append(brightness)
            contrast_values.append(contrast)
            blur_values.append(blur)
            if dark_ratio >= 0.40:
                dark_frame_count += 1
            if overexposed_ratio >= 0.18:
                overexposed_frame_count += 1

            frame_index += 1
    finally:
        cap.release()

    if not sampled_frames:
        return _empty_quality_result("视频为空，未能完成质量检查。")

    brightness_mean = _mean(brightness_values)
    contrast_mean = _mean(contrast_values)
    blur_score = _mean(blur_values)
    dark_frame_pct = dark_frame_count / sampled_frames
    overexposed_frame_pct = overexposed_frame_count / sampled_frames

    warnings: list[dict[str, str]] = []
    if brightness_mean < 70.0 or dark_frame_pct >= 0.35:
        warnings.append(
            {
                "code": "too_dark",
                "label": "画面偏暗",
                "message": "画面整体偏暗，可能影响杠铃和姿态识别。",
            }
        )
    if blur_score < 80.0:
        warnings.append(
            {
                "code": "blurry",
                "label": "画面偏模糊",
                "message": "视频清晰度偏低，关键点和杠铃边缘可能不稳定。",
            }
        )
    if contrast_mean < 32.0:
        warnings.append(
            {
                "code": "low_contrast",
                "label": "画面对比度偏低",
                "message": "人物和器械边界不够清晰，可能增加漏检。",
            }
        )
    if overexposed_frame_pct >= 0.20 and brightness_mean >= 110.0:
        warnings.append(
            {
                "code": "backlit_or_overexposed",
                "label": "逆光或高光过强",
                "message": "强背光或高光区域较多，可能导致姿态和杠铃检测漂移。",
            }
        )

    usable = not any(item["code"] in {"too_dark", "blurry"} for item in warnings)
    confidence = 1.0 - min(0.75, len(warnings) * 0.2)
    if blur_score < 40.0:
        confidence -= 0.1
    confidence = max(0.05, min(1.0, confidence))

    return {
        "quality": {
            "usable": usable,
            "confidence": round(confidence, 4),
            "primaryWarning": warnings[0]["message"] if warnings else None,
        },
        "metrics": {
            "sampledFrames": sampled_frames,
            "sourceFps": source_fps,
            "sampleFps": sample_fps,
            "frameCount": frame_count,
            "frameWidth": width,
            "frameHeight": height,
            "brightnessMean": round(brightness_mean, 2),
            "contrastMean": round(contrast_mean, 2),
            "blurScore": round(blur_score, 2),
            "darkFramePct": round(dark_frame_pct, 4),
            "overexposedFramePct": round(overexposed_frame_pct, 4),
        },
        "warnings": warnings,
    }


def build_video_quality_summary(video_quality: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(video_quality, dict):
        return {
            "videoQualityUsable": True,
            "videoQualityConfidence": None,
            "videoQualityWarningCount": 0,
            "videoQualityWarningCodes": [],
        }
    quality = video_quality.get("quality")
    warnings = video_quality.get("warnings")
    return {
        "videoQualityUsable": bool((quality or {}).get("usable", True)),
        "videoQualityConfidence": (
            float(quality["confidence"])
            if isinstance((quality or {}).get("confidence"), (int, float))
            else None
        ),
        "videoQualityWarningCount": len(warnings) if isinstance(warnings, list) else 0,
        "videoQualityWarningCodes": [
            item["code"]
            for item in warnings
            if isinstance(item, dict) and isinstance(item.get("code"), str)
        ] if isinstance(warnings, list) else [],
    }


def _empty_quality_result(message: str) -> dict[str, Any]:
    return {
        "quality": {
            "usable": False,
            "confidence": 0.0,
            "primaryWarning": message,
        },
        "metrics": {},
        "warnings": [
            {
                "code": "quality_unavailable",
                "label": "质量检查不可用",
                "message": message,
            }
        ],
    }


def _mean(values: list[float]) -> float:
    return (sum(values) / len(values)) if values else 0.0


def _env_float(name: str, default: float) -> float:
    import os

    v = os.environ.get(name)
    if v is None:
        return default
    try:
        return float(v)
    except ValueError:
        return default
