from __future__ import annotations

import json
import os
from typing import Any

import httpx
from openai import OpenAI

from server.video.preprocess import extract_video_classification_frames


_ALLOWED_LIFT_TYPES = {"squat", "bench", "deadlift", "sumo_deadlift"}


def classify_lift_from_video(
    *,
    video_path: str,
    duration_ms: int | None,
) -> dict[str, Any]:
    if not _llm_should_run():
        return {
            "enabled": False,
            "used": False,
            "liftType": None,
            "analysisExercise": None,
            "confidence": 0.0,
            "reason": "llm_disabled",
            "framesSampled": 0,
        }

    frames = extract_video_classification_frames(
        video_path=video_path,
        duration_ms=duration_ms,
        max_frames=_env_int("SSC_LIFT_CLASSIFY_MAX_FRAMES", 5),
        max_edge=_env_int("SSC_LIFT_CLASSIFY_MAX_EDGE", 576),
        jpeg_quality=_env_int("SSC_LIFT_CLASSIFY_JPEG_QUALITY", 72),
    )
    if not frames:
        return {
            "enabled": True,
            "used": False,
            "liftType": None,
            "analysisExercise": None,
            "confidence": 0.0,
            "reason": "no_classification_frames",
            "framesSampled": 0,
        }

    client = _build_openai_client(
        timeout_sec=_env_float("SSC_LIFT_CLASSIFY_TIMEOUT_SEC", 30.0)
    )
    response = client.chat.completions.create(
        model=_llm_model(),
        temperature=0.0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": _build_user_content(frames=frames)},
        ],
    )
    if not response.choices:
        raise RuntimeError("lift_classification_missing_choices")
    content = response.choices[0].message.content
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("lift_classification_empty_content")
    payload = _parse_json_content(content)
    lift_type = _normalize_lift_type(payload.get("liftType"))
    confidence = _clamp_confidence(payload.get("confidence"), 0.0)
    reason = _clean_text(payload.get("reason")) or "no_reason"
    return {
        "enabled": True,
        "used": lift_type is not None,
        "liftType": lift_type,
        "analysisExercise": _analysis_exercise_for_lift_type(lift_type),
        "confidence": confidence,
        "alternate": _normalize_lift_type(payload.get("alternate")),
        "reason": reason,
        "framesSampled": len(frames),
    }


def build_lift_classification_cache_key(*, duration_ms: int | None) -> str:
    payload = {
        "version": "lift-classifier-v1",
        "model": _llm_model(),
        "systemPrompt": _system_prompt(),
        "frameConfig": {
            "maxFrames": _env_int("SSC_LIFT_CLASSIFY_MAX_FRAMES", 5),
            "maxEdge": _env_int("SSC_LIFT_CLASSIFY_MAX_EDGE", 576),
            "jpegQuality": _env_int("SSC_LIFT_CLASSIFY_JPEG_QUALITY", 72),
        },
        "durationMs": duration_ms,
    }
    return _sha256_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


def _analysis_exercise_for_lift_type(lift_type: str | None) -> str | None:
    if lift_type == "sumo_deadlift":
        return "deadlift"
    return lift_type


def _system_prompt() -> str:
    return (
        "你是一位带出过多位世界冠军的力量举教练。"
        "请只根据给定的视频帧判断当前动作属于以下四类中的哪一个："
        "squat、bench、deadlift、sumo_deadlift。"
        "只做动作类型分类，不做技术分析。"
        "sumo_deadlift 只有在站距明显宽、手臂在腿内侧、动作模式清楚时才选。"
        "如果看不清，就在 deadlift 和 sumo_deadlift 中选择更保守的 deadlift。"
        "输出 JSON，字段必须包含 liftType、confidence、alternate、reason。"
    )


def _build_user_content(*, frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                "请根据下面 3-5 张来自同一个视频的关键帧，判断动作类型。"
                "可选值只有：squat、bench、deadlift、sumo_deadlift。"
            ),
        }
    ]
    for frame in frames:
        data_url = frame.get("dataUrl")
        time_ms = frame.get("timeMs")
        if not isinstance(data_url, str) or not data_url:
            continue
        content.append({"type": "text", "text": f"时间点: {int(time_ms)} ms"})
        content.append({"type": "image_url", "image_url": {"url": data_url}})
    return content


def _build_openai_client(*, timeout_sec: float) -> OpenAI:
    base_url = (os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    api_key = os.environ["OPENAI_API_KEY"]
    verify = _ssl_verify_setting()
    http_client = httpx.Client(
        verify=verify,
        timeout=timeout_sec,
        headers={"api-key": api_key},
    )
    return OpenAI(
        api_key=api_key,
        base_url=base_url,
        http_client=http_client,
        max_retries=1,
    )


def _llm_should_run() -> bool:
    flag = (os.environ.get("SSC_LLM_ANALYSIS") or "").strip().lower()
    if flag in {"0", "false", "off", "no"}:
        return False
    if not os.environ.get("OPENAI_API_KEY"):
        return False
    return True


def _llm_model() -> str:
    return (
        os.environ.get("SSC_LLM_MODEL")
        or os.environ.get("OPENAI_MODEL")
        or "gpt-4.1-mini"
    )


def _ssl_verify_setting() -> bool:
    flag = (os.environ.get("SSC_SSL_VERIFY") or "1").strip().lower()
    return flag not in {"0", "false", "off", "no"}


def _parse_json_content(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise RuntimeError("lift_classification_non_object")
    return parsed


def _normalize_lift_type(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    lowered = value.strip().lower()
    aliases = {
        "bench press": "bench",
        "bench_press": "bench",
        "conventional deadlift": "deadlift",
        "sumo deadlift": "sumo_deadlift",
        "sumo-deadlift": "sumo_deadlift",
    }
    lowered = aliases.get(lowered, lowered)
    return lowered if lowered in _ALLOWED_LIFT_TYPES else None


def _clamp_confidence(value: Any, default: float) -> float:
    try:
        val = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, val))


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _env_int(name: str, default: int) -> int:
    v = os.environ.get(name)
    if v is None:
        return default
    try:
        return int(float(v))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    v = os.environ.get(name)
    if v is None:
        return default
    try:
        return float(v)
    except ValueError:
        return default


def _sha256_text(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()
