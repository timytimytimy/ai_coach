from __future__ import annotations

import json
import os
import re
import time
from typing import Any
from functools import lru_cache

import httpx
from openai import APITimeoutError, OpenAI
from pydantic import ValidationError

from server.fusion.schema import FusionAnalysis
from server.video import extract_llm_keyframes


class _LlmRequestFailure(RuntimeError):
    def __init__(self, message: str, *, request_meta: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.request_meta = request_meta or {}


def build_fused_analysis(
    *,
    exercise: str,
    features: dict[str, Any],
    phases: list[dict[str, Any]],
    pose_result: dict[str, Any] | None,
    video_quality: dict[str, Any] | None,
    rule_analysis: dict[str, Any],
    video_path: str | None = None,
    duration_ms: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not _llm_should_run():
        return (
            {**rule_analysis, "source": "rules"},
            {"enabled": False, "used": False, "reason": "llm_disabled"},
        )

    try:
        payload, request_meta = _call_openai_chat(
            exercise=exercise,
            features=features,
            phases=phases,
            pose_result=pose_result,
            video_quality=video_quality,
            rule_analysis=rule_analysis,
            video_path=video_path,
            duration_ms=duration_ms,
        )
        screening = _normalize_screening_checklist(
            payload.get("screeningChecklist"),
            exercise=exercise,
        )
        analysis = _normalize_llm_analysis(
            payload=payload,
            fallback=rule_analysis,
            screening=screening,
        )
        return (
            {**analysis, "source": "llm"},
            {
                "enabled": True,
                "used": True,
                "provider": "openai",
                "model": _llm_model(),
                "screeningChecklist": screening,
                "screeningSummary": {
                    "total": len(screening),
                    "present": sum(
                        1 for item in screening if _screening_final_status(item) == "present"
                    ),
                    "possible": sum(
                        1 for item in screening if _screening_final_status(item) == "possible"
                    ),
                    "absent": sum(
                        1 for item in screening if _screening_final_status(item) == "absent"
                    ),
                    "notSupported": sum(
                        1
                        for item in screening
                        if _screening_final_status(item) == "not_supported"
                    ),
                },
                "visualInput": {
                    "included": bool(video_path),
                },
                "knowledgeBase": {
                    "included": bool(_knowledge_excerpt(exercise)),
                    "source": "力量举技术筛查手册",
                },
                "requestMetrics": request_meta,
            },
        )
    except _LlmRequestFailure as exc:
        return (
            {**rule_analysis, "source": "rules"},
            {
                "enabled": True,
                "used": False,
                "provider": "openai",
                "model": _llm_model(),
                "error": str(exc),
                "visualInput": {
                    "included": bool(video_path),
                },
                "knowledgeBase": {
                    "included": bool(_knowledge_excerpt(exercise)),
                    "source": "力量举技术筛查手册",
                },
                "requestMetrics": exc.request_meta,
            },
        )
    except Exception as exc:
        return (
            {**rule_analysis, "source": "rules"},
            {
                "enabled": True,
                "used": False,
                "provider": "openai",
                "model": _llm_model(),
                "error": str(exc),
                "visualInput": {
                    "included": bool(video_path),
                },
                "knowledgeBase": {
                    "included": bool(_knowledge_excerpt(exercise)),
                    "source": "力量举技术筛查手册",
                },
                "requestMetrics": None,
            },
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


def _call_openai_chat(
    *,
    exercise: str,
    features: dict[str, Any],
    phases: list[dict[str, Any]],
    pose_result: dict[str, Any] | None,
    video_quality: dict[str, Any] | None,
    rule_analysis: dict[str, Any],
    video_path: str | None,
    duration_ms: int | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    attempts = [
        {
            "timeout_sec": _env_float("SSC_LLM_TIMEOUT_SEC", 60.0),
            "max_frames": _env_int("SSC_LLM_MAX_FRAMES", 3),
            "max_edge": _env_int("SSC_LLM_KEYFRAME_MAX_EDGE", 576),
            "jpeg_quality": _env_int("SSC_LLM_KEYFRAME_JPEG_QUALITY", 72),
        },
        {
            "timeout_sec": _env_float("SSC_LLM_RETRY_TIMEOUT_SEC", 45.0),
            "max_frames": _env_int("SSC_LLM_RETRY_MAX_FRAMES", 1),
            "max_edge": _env_int("SSC_LLM_RETRY_KEYFRAME_MAX_EDGE", 448),
            "jpeg_quality": _env_int("SSC_LLM_RETRY_KEYFRAME_JPEG_QUALITY", 60),
        },
    ]
    total_started = time.monotonic()
    last_error: Exception | None = None
    attempt_history: list[dict[str, Any]] = []
    for index, attempt in enumerate(attempts):
        started = time.monotonic()
        try:
            client = _build_openai_client(timeout_sec=attempt["timeout_sec"])
            user_content = _build_user_content(
                exercise=exercise,
                features=features,
                phases=phases,
                pose_result=pose_result,
                video_quality=video_quality,
                rule_analysis=rule_analysis,
                video_path=video_path,
                duration_ms=duration_ms,
                max_frames=attempt["max_frames"],
                max_edge=attempt["max_edge"],
                jpeg_quality=attempt["jpeg_quality"],
            )
            response = client.chat.completions.create(
                model=_llm_model(),
                temperature=0.2,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _system_prompt()},
                    {"role": "user", "content": user_content},
                ],
            )
            if not response.choices:
                raise RuntimeError("openai_missing_choices")
            message = response.choices[0].message
            content = message.content
            if not isinstance(content, str) or not content.strip():
                raise RuntimeError("openai_empty_content")
            latency_ms = int(round((time.monotonic() - started) * 1000.0))
            usage = _extract_usage(response)
            attempt_history.append(
                {
                    "index": index + 1,
                    "timeoutSec": attempt["timeout_sec"],
                    "maxFrames": attempt["max_frames"],
                    "maxEdge": attempt["max_edge"],
                    "jpegQuality": attempt["jpeg_quality"],
                    "latencyMs": latency_ms,
                    "status": "succeeded",
                }
            )
            return _parse_json_content(content), {
                "latencyMs": int(round((time.monotonic() - total_started) * 1000.0)),
                "attemptCount": index + 1,
                "attempts": attempt_history,
                "usage": usage,
            }
        except (APITimeoutError, httpx.TimeoutException) as exc:
            latency_ms = int(round((time.monotonic() - started) * 1000.0))
            last_error = exc
            attempt_history.append(
                {
                    "index": index + 1,
                    "timeoutSec": attempt["timeout_sec"],
                    "maxFrames": attempt["max_frames"],
                    "maxEdge": attempt["max_edge"],
                    "jpegQuality": attempt["jpeg_quality"],
                    "latencyMs": latency_ms,
                    "status": "timeout",
                    "error": str(exc),
                }
            )
            if index == len(attempts) - 1:
                break
            continue
    if last_error is not None:
        raise _LlmRequestFailure(
            "Request timed out after retry "
            f"(frames={attempts[0]['max_frames']}->{attempts[-1]['max_frames']}, "
            f"timeout={attempts[0]['timeout_sec']}->{attempts[-1]['timeout_sec']}s).",
            request_meta={
                "latencyMs": int(round((time.monotonic() - total_started) * 1000.0)),
                "attemptCount": len(attempt_history),
                "attempts": attempt_history,
                "usage": None,
            },
        ) from last_error
    raise _LlmRequestFailure(
        "openai_request_failed",
        request_meta={
            "latencyMs": int(round((time.monotonic() - total_started) * 1000.0)),
            "attemptCount": len(attempt_history),
            "attempts": attempt_history,
            "usage": None,
        },
    )


def build_fused_analysis_cache_key(
    *,
    exercise: str,
    features: dict[str, Any],
    phases: list[dict[str, Any]],
    pose_result: dict[str, Any] | None,
    video_quality: dict[str, Any] | None,
    rule_analysis: dict[str, Any],
    has_video: bool,
) -> str:
    payload = {
        "version": "fusion-cache-v1",
        "model": _llm_model(),
        "systemPrompt": _system_prompt(),
        "userPrompt": _user_prompt(
            exercise=exercise,
            features=features,
            phases=phases,
            pose_result=pose_result,
            video_quality=video_quality,
            rule_analysis=rule_analysis,
        ),
        "hasVideo": has_video,
        "visualConfig": {
            "maxFrames": _env_int("SSC_LLM_MAX_FRAMES", 3),
            "maxEdge": _env_int("SSC_LLM_KEYFRAME_MAX_EDGE", 576),
            "jpegQuality": _env_int("SSC_LLM_KEYFRAME_JPEG_QUALITY", 72),
            "retryMaxFrames": _env_int("SSC_LLM_RETRY_MAX_FRAMES", 1),
            "retryMaxEdge": _env_int("SSC_LLM_RETRY_KEYFRAME_MAX_EDGE", 448),
            "retryJpegQuality": _env_int("SSC_LLM_RETRY_KEYFRAME_JPEG_QUALITY", 60),
        },
    }
    return _sha256_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


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


def _system_prompt() -> str:
    return (
        "你是一位带出过多位世界冠军的力量举教练，长期从事深蹲、卧推、硬拉教学和比赛指导。"
        "你现在要像真正的高水平教练一样先看动作，再结合数据做校正，而不是先复述规则。"
        "你只能基于给定的视频关键帧、结构化证据和技术手册生成结论，不能编造新的测量值。"
        "视频视觉判断是主观察源；杠铃轨迹、VBT、pose 和规则候选只用于验证、校正、补充，不是先验结论。"
        "如果提供了技术筛查手册，请优先按手册中的筛查点、理想状态、错误代偿、纠正逻辑来归纳问题和建议。"
        "如果手册中提供了边界判定与去重规则，必须优先遵守，避免把同一现象拆成重复问题。"
        "如果手册中说明某类问题属于‘不能直接看见本体、只能通过外在表现推断’，你必须遵守这种边界。"
        "对肩胛控制、上背支撑、桥塌、brace、张力预设、腋下锁杠这类问题，不要假装直接看见了肌肉或关节本体。"
        "这类问题应该描述为基于连续动作表现、平台稳定性、路径变化、左右时序和相关证据做出的推断。"
        "如果证据不够强，优先输出为 possible 或继续观察，不要高置信硬下结论。"
        "你必须先对给定 taxonomy 中的每一个问题做逐项筛查，再输出最终 1-3 个主问题。"
        "逐项筛查时，先给出 visualAssessment，再给出 structuredAssessment，最后给出 finalAssessment。"
        "如果视频里明显看得出问题，但结构化证据较弱，可以给 possible；如果规则提到了问题但视频里看不出来，也可以降级或否决。"
        "你的文案口吻要像认真、直接、专业但有人味的力量举教练，不要像机器报告。"
        "输出必须是 JSON 对象。"
        "最多输出 3 个问题。"
        "优先给用户能直接理解的中文 title 和中文证据。"
    )


def _user_prompt(
    *,
    exercise: str,
    features: dict[str, Any],
    phases: list[dict[str, Any]],
    pose_result: dict[str, Any] | None,
    video_quality: dict[str, Any] | None,
    rule_analysis: dict[str, Any],
) -> str:
    payload = {
        "task": "基于给定的视频关键帧、技术手册和结构化证据，生成最终技术分析 JSON。先做视觉筛查，再用结构化证据校正。保留稳定 schema，不要输出 markdown。",
        "constraints": [
            "不要编造新的数值",
            "每个问题必须有 visualEvidence 和 kinematicEvidence",
            "只有证据不足时才输出低置信度问题",
            "如果 pose 质量不足，不要把 pose 当主要依据",
            "title 用简短中文，cue 用一句中文，drills 最多两个短语",
            "如果手册中已经定义了更贴切的筛查名称和纠正逻辑，优先沿用手册语义",
            "问题 name 尽量使用稳定 taxonomy 中的 code，不要随意创造新 code",
            "先输出 screeningChecklist，对 issueTaxonomy 中每个 code 逐项筛查",
            "screeningChecklist 中每一项都要包含 visualAssessment、structuredAssessment、finalAssessment，这三个字段的值只能是 present/possible/absent/not_supported",
            "screeningChecklist 中每一项都必须包含 confidence 和 reason",
            "confidence 用 0 到 1 之间的小数，表示你对 finalAssessment 的把握程度",
            "reason 用一句简短中文，说明为什么这样判，优先说视频观察，再补结构化证据或证据不足原因",
            "finalAssessment 必须是在视频视觉判断基础上，再结合结构化证据做出的最终裁决",
            "最终 issues 必须从 screeningChecklist 里 finalAssessment 为 present 或 possible 的项目中挑选，不能凭空新增",
            "输出 coachFeedback，包含 focus、why、nextSet、keepWatching",
            "focus 要像教练总结这组最该先改的一句话",
            "why 要解释为什么这样判断，可以结合视频表现和数值趋势",
            "nextSet 要告诉用户下一组具体怎么做",
            "keepWatching 最多 3 条，优先放证据还不够强、但值得继续观察的点",
            "不要把规则候选当成既定结论；如果规则候选和视频观察冲突，允许以视频观察为主并说明结构化证据不足或不支持",
            "对肩胛控制、上背支撑、桥塌、brace、张力预设、腋下锁杠这类问题，不要写成‘直接看见本体出了问题’，要写成基于外在动作表现的推断",
            "如果这类问题只有轻微趋势，默认降级为 possible 或 keepWatching，不要轻易列为高置信主问题",
        ],
        "analysisProtocol": [
            "第一步：先基于视频关键帧和手册做视觉筛查，判断每个 taxonomy 项在画面里是否可见、可疑或不可支持",
            "第二步：再用杠铃轨迹、VBT、pose、phase、quality 等结构化证据验证或修正视觉判断",
            "第三步：最后只输出 1 到 3 个最值得先改的主问题，并给教练式反馈",
        ],
        "exercise": exercise,
        "issueTaxonomy": _issue_taxonomy(exercise),
        "knowledgeBase": _knowledge_excerpt(exercise),
        "structuredEvidence": {
            "features": _feature_snapshot(features),
            "phases": _phase_snapshot(phases),
            "poseQuality": (pose_result or {}).get("quality"),
            "videoQuality": _video_quality_snapshot(video_quality),
        },
        "ruleCandidates": _rule_candidate_snapshot(rule_analysis),
    }
    return json.dumps(payload, ensure_ascii=False)


def _extract_usage(response: Any) -> dict[str, int] | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    prompt_tokens = _safe_int(getattr(usage, "prompt_tokens", None))
    completion_tokens = _safe_int(getattr(usage, "completion_tokens", None))
    total_tokens = _safe_int(getattr(usage, "total_tokens", None))
    if prompt_tokens is None and completion_tokens is None and total_tokens is None:
        return None
    return {
        "promptTokens": prompt_tokens or 0,
        "completionTokens": completion_tokens or 0,
        "totalTokens": total_tokens or 0,
    }


def _build_user_content(
    *,
    exercise: str,
    features: dict[str, Any],
    phases: list[dict[str, Any]],
    pose_result: dict[str, Any] | None,
    video_quality: dict[str, Any] | None,
    rule_analysis: dict[str, Any],
    video_path: str | None,
    duration_ms: int | None,
    max_frames: int,
    max_edge: int,
    jpeg_quality: int,
) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": _user_prompt(
                exercise=exercise,
                features=features,
                phases=phases,
                pose_result=pose_result,
                video_quality=video_quality,
                rule_analysis=rule_analysis,
            ),
        }
    ]
    if not video_path:
        return content

    keyframes = extract_llm_keyframes(
        video_path=video_path,
        duration_ms=duration_ms,
        phases=phases,
        rule_analysis=rule_analysis,
        max_frames=max_frames,
        max_edge=max_edge,
        jpeg_quality=jpeg_quality,
    )
    if not keyframes:
        return content

    content.append(
        {
            "type": "text",
            "text": "下面附上从原始视频中抽取的关键帧。请先像教练一样看片，再用后面的结构化证据做验证和校正，不要直接复述规则候选。",
        }
    )
    for frame in keyframes:
        data_url = frame.get("dataUrl")
        time_ms = frame.get("timeMs")
        if not isinstance(data_url, str) or not data_url:
            continue
        content.append(
            {
                "type": "text",
                "text": f"关键帧时间点: {int(time_ms) if isinstance(time_ms, int) else 0} ms",
            }
        )
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": data_url},
            }
        )
    return content


def _feature_snapshot(features: dict[str, Any]) -> dict[str, Any]:
    rep_summaries = features.get("repSummaries")
    compact_reps: list[dict[str, Any]] = []
    if isinstance(rep_summaries, list):
        for rep in rep_summaries[:6]:
            if not isinstance(rep, dict):
                continue
            compact_reps.append(
                {
                    "repIndex": rep.get("repIndex"),
                    "timeRangeMs": rep.get("timeRangeMs"),
                    "avgVelocityMps": rep.get("avgVelocityMps"),
                    "peakVelocityMps": rep.get("peakVelocityMps"),
                    "durationMs": rep.get("durationMs"),
                    "barPathDriftCm": rep.get("barPathDriftCm"),
                    "stickingRegion": rep.get("stickingRegion"),
                    "torsoLeanDeltaDeg": rep.get("torsoLeanDeltaDeg"),
                    "startTorsoLeanDeg": rep.get("startTorsoLeanDeg"),
                    "endTorsoLeanDeg": rep.get("endTorsoLeanDeg"),
                    "minKneeAngleDeg": rep.get("minKneeAngleDeg"),
                    "minHipAngleDeg": rep.get("minHipAngleDeg"),
                    "minElbowAngleDeg": rep.get("minElbowAngleDeg"),
                    "avgWristStackOffsetPx": rep.get("avgWristStackOffsetPx"),
                }
            )
    return {
        "exercise": features.get("exercise"),
        "repCount": features.get("repCount"),
        "avgRepVelocityMps": features.get("avgRepVelocityMps"),
        "bestRepVelocityMps": features.get("bestRepVelocityMps"),
        "barPathDriftCm": features.get("barPathDriftCm"),
        "velocityLossPct": features.get("velocityLossPct"),
        "repVelocityCvPct": features.get("repVelocityCvPct"),
        "avgAscentDurationMs": features.get("avgAscentDurationMs"),
        "poseUsable": features.get("poseUsable"),
        "poseFrameCount": features.get("poseFrameCount"),
        "posePrimarySide": features.get("posePrimarySide"),
        "poseJointQuality": features.get("poseJointQuality"),
        "maxTorsoLeanDeg": features.get("maxTorsoLeanDeg"),
        "avgTorsoLeanDeltaDeg": features.get("avgTorsoLeanDeltaDeg"),
        "minKneeAngleDeg": features.get("minKneeAngleDeg"),
        "minHipAngleDeg": features.get("minHipAngleDeg"),
        "minElbowAngleDeg": features.get("minElbowAngleDeg"),
        "avgWristStackOffsetPx": features.get("avgWristStackOffsetPx"),
        "trustedAnkleCoverage": features.get("trustedAnkleCoverage"),
        "trustedWristCoverage": features.get("trustedWristCoverage"),
        "videoQualityUsable": features.get("videoQualityUsable"),
        "videoQualityWarningCodes": features.get("videoQualityWarningCodes"),
        "repSummaries": compact_reps,
    }


def _phase_snapshot(phases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for phase in phases[:16]:
        if not isinstance(phase, dict):
            continue
        out.append(
            {
                "name": phase.get("name"),
                "repIndex": phase.get("repIndex"),
                "startMs": phase.get("startMs"),
                "endMs": phase.get("endMs"),
            }
        )
    return out


def _video_quality_snapshot(video_quality: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(video_quality, dict):
        return None
    quality = video_quality.get("quality")
    warnings = video_quality.get("warnings")
    return {
        "quality": quality if isinstance(quality, dict) else None,
        "warnings": warnings if isinstance(warnings, list) else None,
    }


def _rule_candidate_snapshot(rule_analysis: dict[str, Any]) -> dict[str, Any]:
    issues = rule_analysis.get("issues")
    candidates: list[dict[str, Any]] = []
    if isinstance(issues, list):
        for issue in issues[:4]:
            if not isinstance(issue, dict):
                continue
            candidates.append(
                {
                    "code": _clean_issue_name(issue.get("name")),
                    "title": _clean_text(issue.get("title")),
                    "confidence": _clamp_confidence(issue.get("confidence"), 0.0),
                    "evidenceSource": _normalize_evidence_source(issue.get("evidenceSource")),
                    "timeRangeMs": issue.get("timeRangeMs"),
                }
            )
    return {
        "note": "这些只是系统召回出来的候选关注点，不是最终结论。请先看片，再决定是否采纳、降级或否决。",
        "candidates": candidates,
        "cue": _clean_text(rule_analysis.get("cue")),
        "cameraQualityWarning": _clean_text(rule_analysis.get("cameraQualityWarning")),
    }


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
        raise RuntimeError("openai_non_object_response")
    return parsed


def _normalize_llm_analysis(
    *,
    payload: dict[str, Any],
    fallback: dict[str, Any],
    screening: list[dict[str, Any]],
) -> dict[str, Any]:
    issues = _merge_duplicate_issues(
        _normalize_issues(payload.get("issues"), fallback.get("issues"))
    )
    normalized_cue, normalized_drills, normalized_load_adjustment = (
        _normalize_recommendations(
            primary_issue=issues[0] if issues else None,
            cue=payload.get("cue"),
            drills=payload.get("drills"),
            load_adjustment=payload.get("loadAdjustment"),
            fallback=fallback,
        )
    )
    merged = {
        "liftType": payload.get("liftType") or fallback.get("liftType"),
        "confidence": _clamp_confidence(
            payload.get("confidence"), fallback.get("confidence", 0.5)
        ),
        "issues": issues,
        "coachFeedback": _normalize_coach_feedback(
            candidate=payload.get("coachFeedback"),
            fallback=fallback.get("coachFeedback"),
            issues=issues,
            screening=screening,
        ),
        "cue": normalized_cue,
        "drills": normalized_drills,
        "loadAdjustment": normalized_load_adjustment,
        "cameraQualityWarning": _clean_text(payload.get("cameraQualityWarning"))
        if payload.get("cameraQualityWarning") is not None
        else fallback.get("cameraQualityWarning"),
    }
    try:
        validated = FusionAnalysis.model_validate(merged)
        return _humanize_analysis_texts(validated.model_dump())
    except ValidationError:
        return fallback


def _normalize_issues(candidate: Any, fallback: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    source = candidate if isinstance(candidate, list) else fallback
    if not isinstance(source, list):
        return fallback if isinstance(fallback, list) else []
    for issue in source[:3]:
        if not isinstance(issue, dict):
            continue
        name = _canonical_issue_name(
            _clean_issue_name(issue.get("name")),
            title=_clean_text(issue.get("title")),
        )
        if not name:
            continue
        time_range = issue.get("timeRangeMs")
        if not isinstance(time_range, dict):
            continue
        start = _safe_int(time_range.get("start"))
        end = _safe_int(time_range.get("end"))
        if start is None or end is None:
            continue
        out.append(
            {
                "name": name,
                "title": _issue_title(name),
                "severity": _normalize_severity(issue.get("severity")),
                "confidence": _clamp_confidence(issue.get("confidence"), 0.6),
                "evidenceSource": _normalize_evidence_source(
                    issue.get("evidenceSource")
                ),
                "visualEvidence": _normalize_string_list(issue.get("visualEvidence")),
                "kinematicEvidence": _normalize_string_list(
                    issue.get("kinematicEvidence")
                ),
                "timeRangeMs": {"start": start, "end": max(start, end)},
            }
        )
    if out:
        return out
    return fallback if isinstance(fallback, list) else []


def _merge_duplicate_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(issues) <= 1:
        return issues

    merged: list[dict[str, Any]] = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        target_index = None
        for idx, existing in enumerate(merged):
            if _should_merge_issue_pair(existing, issue):
                target_index = idx
                break
        if target_index is None:
            merged.append(issue)
            continue
        merged[target_index] = _merge_issue_pair(merged[target_index], issue)
    return merged[:3]


def _normalize_screening_checklist(
    candidate: Any,
    *,
    exercise: str,
) -> list[dict[str, Any]]:
    taxonomy = _issue_taxonomy(exercise)
    taxonomy_map = {str(item["code"]): str(item["title"]) for item in taxonomy}
    allowed_status = {"present", "possible", "absent", "not_supported"}

    by_code: dict[str, dict[str, Any]] = {}
    if isinstance(candidate, list):
        for raw in candidate:
            if not isinstance(raw, dict):
                continue
            code = _canonical_issue_name(
                _clean_issue_name(raw.get("code") or raw.get("name")),
                title=_clean_text(raw.get("title")),
            )
            if not code or code not in taxonomy_map:
                continue
            visual_status = _normalize_screening_status(
                raw.get("visualAssessment") or raw.get("visualStatus"),
                allowed_status=allowed_status,
            )
            structured_status = _normalize_screening_status(
                raw.get("structuredAssessment") or raw.get("structuredStatus"),
                allowed_status=allowed_status,
            )
            final_status = _normalize_screening_status(
                raw.get("finalAssessment") or raw.get("status"),
                allowed_status=allowed_status,
            )
            if final_status is None:
                final_status = (
                    "possible"
                    if _clamp_confidence(raw.get("confidence"), 0.0) >= 0.5
                    else "absent"
                )
            if visual_status is None:
                visual_status = final_status
            if structured_status is None:
                structured_status = final_status
            confidence = _normalize_screening_confidence(
                raw.get("confidence"),
                final_status=final_status,
            )
            evidence_source = _normalize_evidence_source(raw.get("evidenceSource"))
            by_code[code] = {
                "code": code,
                "title": taxonomy_map[code],
                "visualAssessment": visual_status,
                "structuredAssessment": structured_status,
                "finalAssessment": final_status,
                "status": final_status,
                "confidence": confidence,
                "reason": _default_screening_reason(
                    title=taxonomy_map[code],
                    visual_status=visual_status,
                    structured_status=structured_status,
                    final_status=final_status,
                    evidence_source=evidence_source,
                    candidate_reason=_clean_text(raw.get("reason")),
                ),
                "evidenceSource": evidence_source,
            }

    normalized: list[dict[str, Any]] = []
    for item in taxonomy:
        code = str(item["code"])
        title = str(item["title"])
        existing = by_code.get(code)
        if existing is not None:
            normalized.append(existing)
            continue
        normalized.append(
            {
                "code": code,
                "title": title,
                "visualAssessment": "not_supported",
                "structuredAssessment": "not_supported",
                "finalAssessment": "not_supported",
                "status": "not_supported",
                "confidence": _normalize_screening_confidence(
                    None,
                    final_status="not_supported",
                ),
                "reason": _default_screening_reason(
                    title=title,
                    visual_status="not_supported",
                    structured_status="not_supported",
                    final_status="not_supported",
                    evidence_source="fusion",
                    candidate_reason=None,
                ),
                "evidenceSource": "fusion",
            }
        )
    return normalized


def _normalize_coach_feedback(
    *,
    candidate: Any,
    fallback: Any,
    issues: list[dict[str, Any]],
    screening: list[dict[str, Any]],
) -> dict[str, Any]:
    fallback_dict = fallback if isinstance(fallback, dict) else {}
    default = _default_coach_feedback(issues=issues, screening=screening)
    if not isinstance(candidate, dict):
        return {
            "focus": _clean_text(fallback_dict.get("focus")) or default["focus"],
            "why": _clean_text(fallback_dict.get("why")) or default["why"],
            "nextSet": _clean_text(fallback_dict.get("nextSet")) or default["nextSet"],
            "keepWatching": _normalize_keep_watching(
                fallback_dict.get("keepWatching"),
                default["keepWatching"],
            ),
        }
    return {
        "focus": _clean_text(candidate.get("focus"))
        or _clean_text(fallback_dict.get("focus"))
        or default["focus"],
        "why": _clean_text(candidate.get("why"))
        or _clean_text(fallback_dict.get("why"))
        or default["why"],
        "nextSet": _clean_text(candidate.get("nextSet"))
        or _clean_text(fallback_dict.get("nextSet"))
        or default["nextSet"],
        "keepWatching": _normalize_keep_watching(
            candidate.get("keepWatching"),
            _normalize_keep_watching(
                fallback_dict.get("keepWatching"),
                default["keepWatching"],
            ),
        ),
    }


def _normalize_keep_watching(candidate: Any, fallback: list[str]) -> list[str]:
    normalized = _normalize_string_list(candidate)
    if normalized:
        return normalized[:3]
    return fallback[:3]


def _default_coach_feedback(
    *,
    issues: list[dict[str, Any]],
    screening: list[dict[str, Any]],
) -> dict[str, Any]:
    primary = issues[0] if issues else {}
    primary_name = str(primary.get("name") or "")
    focus_map = {
        "rep_to_rep_velocity_drop": "这组最明显的问题是后半组重复质量掉得比较快。",
        "mid_ascent_sticking_point": "这组最需要先改的是出底到起立中段这段发力连续性。",
        "slow_concentric_speed": "这组起立整体偏慢，尤其后半组更吃力。",
        "grindy_ascent": "这组起立过程偏拖，后半段发力不够干脆。",
        "torso_position_shift": "这组起立时躯干姿态有点散，胸背稳定性不够。",
        "bar_path_drift": "这组杠铃路径不够稳，起立时有往前跑的趋势。",
    }
    why_map = {
        "rep_to_rep_velocity_drop": "前几次还能维持节奏，后面几次速度和完成质量一起往下掉，疲劳会把问题放大。",
        "mid_ascent_sticking_point": "你不是单纯底部起不来，而是出底后到中段会明显减速，所以看起来像卡一下再继续上。",
        "slow_concentric_speed": "问题不只是速度慢，而是起立发力没有持续顶上去，越到后面越容易拖长。",
        "grindy_ascent": "单次起立时间被拉长，说明这组的发力连续性和完成效率都在往下掉。",
        "torso_position_shift": "出底后躯干角度变化偏大，说明你在用姿态变化帮自己把杠顶起来。",
        "bar_path_drift": "杠没有一直稳在同一条发力线上，路径一散，后面的发力效率就会下降。",
    }
    next_set_map = {
        "rep_to_rep_velocity_drop": "下一组先把每次重复的准备和起立节奏做一致，不要越做越急，也不要越做越散。",
        "mid_ascent_sticking_point": "下一组把注意力放在出底后继续顶住、继续加速，不要到底部发力一下就松掉。",
        "slow_concentric_speed": "下一组把重点放在持续加速上，让力量从底部一直延续到站直。",
        "grindy_ascent": "下一组先把起立做得更连贯，宁可稳一点，也不要中段突然泄力。",
        "torso_position_shift": "下一组先把胸口和背撑住，再让髋膝一起向上展开。",
        "bar_path_drift": "下一组盯住中足上方这条线，起立时别让杠向前漂。",
    }
    keep_watching = _default_keep_watching(screening=screening, issues=issues)
    return {
        "focus": focus_map.get(primary_name, "这组先优先处理最明显的技术问题。"),
        "why": why_map.get(primary_name, "当前证据提示主要问题集中在起立质量和重复稳定性。"),
        "nextSet": next_set_map.get(primary_name, "下一组先把最关键的一条提示做到位，再看动作有没有马上变顺。"),
        "keepWatching": keep_watching,
    }


def _default_keep_watching(
    *,
    screening: list[dict[str, Any]],
    issues: list[dict[str, Any]],
) -> list[str]:
    issue_codes = {str(item.get("name")) for item in issues if isinstance(item, dict)}
    out: list[str] = []
    for item in screening:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "")
        if code in issue_codes or _screening_final_status(item) != "possible":
            continue
        title = _clean_text(item.get("title"))
        if title:
            out.append(f"{title}还需要继续观察")
        if len(out) >= 3:
            break
    return out


def _humanize_analysis_texts(analysis: dict[str, Any]) -> dict[str, Any]:
    out = {**analysis}
    issues = out.get("issues")
    if isinstance(issues, list):
        normalized_issues = []
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            normalized_issues.append(
                {
                    **issue,
                    "visualEvidence": _humanize_string_list(issue.get("visualEvidence")),
                    "kinematicEvidence": _humanize_string_list(issue.get("kinematicEvidence")),
                }
            )
        out["issues"] = normalized_issues

    coach = out.get("coachFeedback")
    if isinstance(coach, dict):
        out["coachFeedback"] = {
            **coach,
            "focus": _humanize_text(coach.get("focus")),
            "why": _humanize_text(coach.get("why")),
            "nextSet": _humanize_text(coach.get("nextSet")),
            "keepWatching": _humanize_string_list(coach.get("keepWatching")),
        }

    out["cue"] = _humanize_text(out.get("cue"))
    if out.get("cameraQualityWarning") is not None:
        out["cameraQualityWarning"] = _humanize_text(out.get("cameraQualityWarning"))
    return out


def _screening_final_status(item: dict[str, Any]) -> str:
    status = str(item.get("finalAssessment") or item.get("status") or "").strip().lower()
    if status in {"present", "possible", "absent", "not_supported"}:
        return status
    return "not_supported"


def _normalize_screening_status(
    value: Any,
    *,
    allowed_status: set[str],
) -> str | None:
    status = str(value or "").strip().lower()
    if status in allowed_status:
        return status
    return None


def _normalize_screening_confidence(value: Any, *, final_status: str) -> float:
    if isinstance(value, (int, float)):
        return _clamp_confidence(value, 0.0)
    defaults = {
        "present": 0.78,
        "possible": 0.56,
        "absent": 0.68,
        "not_supported": 0.18,
    }
    return defaults.get(final_status, 0.5)


def _default_screening_reason(
    *,
    title: str,
    visual_status: str,
    structured_status: str,
    final_status: str,
    evidence_source: str,
    candidate_reason: str | None,
) -> str:
    cleaned = _clean_text(candidate_reason)
    if cleaned:
        return _humanize_text(cleaned)

    if final_status == "present":
        if visual_status == "present" and structured_status == "present":
            return f"视频里能直接看到“{title}”的迹象，结构化证据也支持这一点。"
        if visual_status == "present":
            return f"视频里能直接看到“{title}”的迹象，当前先按视觉证据成立处理。"
        if structured_status == "present":
            return f"结构化证据对“{title}”支持较强，当前按可成立问题处理。"
    if final_status == "possible":
        if visual_status == "possible" and structured_status in {"possible", "not_supported", "absent"}:
            return f"“{title}”有一定趋势，但当前证据还不够强，先继续观察。"
        return f"“{title}”目前只有部分证据支持，还不足以下高置信结论。"
    if final_status == "absent":
        return f"当前没有看到足够证据支持“{title}”。"
    if final_status == "not_supported":
        if evidence_source == "pose":
            return f"当前画面或姿态覆盖不足，暂时无法稳定判断“{title}”。"
        return f"当前视频条件或证据类型不足，暂时无法稳定判断“{title}”。"
    return f"当前对“{title}”的证据还不充分。"


def _humanize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = _humanize_text(item)
        if text:
            out.append(text)
    return out


def _humanize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text:
        return ""
    text = re.sub(r"[（(]\s*\d+(?:\.\d+)?\s*-\s*\d+(?:\.\d+)?\s*ms\s*[）)]", "", text)
    text = re.sub(
        r"(\d+(?:\.\d+)?)\s*ms",
        lambda m: f"{float(m.group(1)) / 1000.0:.1f}s",
        text,
    )
    text = re.sub(
        r"(\d+\.\d{3,})(?=\s*(m/s|%|°|cm|s)\b)",
        lambda m: f"{float(m.group(1)):.2f}",
        text,
    )
    text = re.sub(r"(\d+\.\d{3,})", lambda m: f"{float(m.group(1)):.2f}", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _should_merge_issue_pair(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_name = str(left.get("name") or "")
    right_name = str(right.get("name") or "")
    left_family = _issue_family(left_name)
    right_family = _issue_family(right_name)
    if left_family != right_family:
        return False
    left_range = left.get("timeRangeMs")
    right_range = right.get("timeRangeMs")
    if not isinstance(left_range, dict) or not isinstance(right_range, dict):
        return False
    return _time_ranges_overlap_enough(left_range, right_range, min_overlap_ratio=0.55)


def _merge_issue_pair(primary: dict[str, Any], secondary: dict[str, Any]) -> dict[str, Any]:
    chosen = primary
    other = secondary
    if _issue_priority(secondary) > _issue_priority(primary):
        chosen = secondary
        other = primary

    merged_visual = _merge_string_lists(
        chosen.get("visualEvidence"),
        other.get("visualEvidence"),
        limit=3,
    )
    merged_kinematic = _merge_string_lists(
        chosen.get("kinematicEvidence"),
        other.get("kinematicEvidence"),
        limit=3,
    )
    tr_chosen = chosen.get("timeRangeMs")
    tr_other = other.get("timeRangeMs")
    merged_range = tr_chosen if isinstance(tr_chosen, dict) else tr_other
    if isinstance(tr_chosen, dict) and isinstance(tr_other, dict):
        merged_range = {
            "start": min(int(tr_chosen.get("start", 0)), int(tr_other.get("start", 0))),
            "end": max(int(tr_chosen.get("end", 0)), int(tr_other.get("end", 0))),
        }

    return {
        **chosen,
        "confidence": max(
            _clamp_confidence(chosen.get("confidence"), 0.6),
            _clamp_confidence(other.get("confidence"), 0.6),
        ),
        "visualEvidence": merged_visual,
        "kinematicEvidence": merged_kinematic,
        "timeRangeMs": merged_range,
    }


def _issue_family(name: str) -> str:
    if name in {"slow_concentric_speed", "grindy_ascent"}:
        return "ascent_speed"
    if name in {"mid_ascent_sticking_point"}:
        return "sticking"
    if name in {"rep_to_rep_velocity_drop", "rep_inconsistency"}:
        return "consistency"
    if name in {"bar_path_drift"}:
        return "bar_path"
    if name in {"torso_position_shift"}:
        return "pose_posture"
    return name


def _time_ranges_overlap_enough(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    min_overlap_ratio: float,
) -> bool:
    ls = _safe_int(left.get("start"))
    le = _safe_int(left.get("end"))
    rs = _safe_int(right.get("start"))
    re = _safe_int(right.get("end"))
    if None in {ls, le, rs, re}:
        return False
    overlap = max(0, min(le, re) - max(ls, rs))
    if overlap <= 0:
        return False
    left_len = max(1, le - ls)
    right_len = max(1, re - rs)
    ratio = overlap / float(min(left_len, right_len))
    return ratio >= min_overlap_ratio


def _issue_priority(issue: dict[str, Any]) -> tuple[int, float]:
    severity_rank = {"high": 3, "medium": 2, "low": 1}
    return (
        severity_rank.get(str(issue.get("severity")), 0),
        _clamp_confidence(issue.get("confidence"), 0.0),
    )


def _merge_string_lists(left: Any, right: Any, *, limit: int) -> list[str]:
    out: list[str] = []
    for seq in (left, right):
        if not isinstance(seq, list):
            continue
        for item in seq:
            text = _clean_text(item)
            if text and text not in out:
                out.append(text)
                if len(out) >= limit:
                    return out
    return out


def _normalize_drills(candidate: Any, fallback: Any) -> list[str]:
    drills = _normalize_string_list(candidate)
    if drills:
        return drills[:2]
    if isinstance(fallback, list):
        return [str(item) for item in fallback if isinstance(item, str)][:2]
    return []


def _normalize_recommendations(
    *,
    primary_issue: dict[str, Any] | None,
    cue: Any,
    drills: Any,
    load_adjustment: Any,
    fallback: dict[str, Any],
) -> tuple[str, list[str], str]:
    issue_name = (
        str(primary_issue.get("name"))
        if isinstance(primary_issue, dict) and isinstance(primary_issue.get("name"), str)
        else None
    )
    rec = _taxonomy_recommendation(issue_name)

    fallback_cue = _clean_text(fallback.get("cue")) or rec["cue"]
    fallback_drills = (
        [str(item) for item in fallback.get("drills", []) if isinstance(item, str)][:2]
        if isinstance(fallback.get("drills"), list)
        else list(rec["drills"])
    )
    fallback_load = (
        _clean_text(fallback.get("loadAdjustment")) or rec["loadAdjustment"]
    )

    normalized_cue = _normalize_cue_text(cue, default=fallback_cue, recommendation=rec)
    normalized_drills = _normalize_drill_list(
        drills,
        default=fallback_drills,
        recommendation=rec,
    )
    normalized_load = _normalize_load_adjustment(
        load_adjustment,
        default=fallback_load,
        recommendation=rec,
    )
    return normalized_cue, normalized_drills, normalized_load


def _normalize_cue_text(value: Any, *, default: str, recommendation: dict[str, Any]) -> str:
    text = _clean_text(value)
    if not text:
        return default
    canonical = str(recommendation["cue"])
    if text == canonical:
        return text
    if _cue_semantically_matches(text, canonical):
        return canonical
    return canonical


def _normalize_drill_list(
    value: Any,
    *,
    default: list[str],
    recommendation: dict[str, Any],
) -> list[str]:
    drills = _normalize_drills(value, default)
    canonical: list[str] = []
    for drill in drills:
        mapped = _canonical_drill_name(drill)
        if mapped and mapped not in canonical:
            canonical.append(mapped)
    if canonical:
        return canonical[:2]
    return list(recommendation["drills"])


def _normalize_load_adjustment(
    value: Any,
    *,
    default: str,
    recommendation: dict[str, Any],
) -> str:
    text = _clean_text(value)
    allowed = {
        "keep_load",
        "next_set_minus_5_percent",
        "hold_load_and_repeat_if_form_breaks",
        "reduce_set_volume_if_quality_drops",
        "hold_load",
    }
    return str(recommendation["loadAdjustment"])


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = _clean_text(item)
        if text:
            out.append(text)
    return out[:3]


def _normalize_severity(value: Any) -> str:
    if value in {"low", "medium", "high"}:
        return str(value)
    return "medium"


def _normalize_evidence_source(value: Any) -> str:
    if value in {"rule", "vbt", "barbell", "pose", "fusion"}:
        return str(value)
    return "fusion"


def _clean_issue_name(value: Any) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    return text.replace("-", "_").replace(" ", "_").lower()


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _canonical_drill_name(raw: str) -> str | None:
    text = raw.strip().lower()
    mapping = {
        "pause squat": "pause squat",
        "paused squat": "pause squat",
        "tempo squat": "tempo squat",
        "pin squat": "pin squat",
        "squat doubles": "squat doubles",
        "paused bench": "paused bench",
        "spoto press": "spoto press",
        "tempo deadlift": "tempo deadlift",
        "leg drive setup practice": "leg drive setup practice",
        "paused deadlift": "paused deadlift",
        "banded deadlift": "banded deadlift",
        "straight-arm lat activation": "straight-arm lat activation",
        "high bar squat": "high bar squat",
        "bulgarian split squat": "bulgarian split squat",
        "sumo wedge drill": "sumo wedge drill",
        "paused sumo deadlift": "paused sumo deadlift",
        "setup tension drill": "setup tension drill",
        "quad-strength accessory": "quad-strength accessory",
        "quad-dominant accessory": "quad-dominant accessory",
        "overload lockout work": "overload lockout work",
    }
    if text in mapping:
        return mapping[text]
    if "暂停深蹲" in raw:
        return "pause squat"
    if "节奏深蹲" in raw:
        return "tempo squat"
    if "销位深蹲" in raw:
        return "pin squat"
    if "双次深蹲" in raw:
        return "squat doubles"
    if "暂停卧推" in raw:
        return "paused bench"
    if "斯波特卧推" in raw:
        return "spoto press"
    if "节奏硬拉" in raw:
        return "tempo deadlift"
    if "腿驱动" in raw:
        return "leg drive setup practice"
    if "暂停硬拉" in raw:
        return "paused deadlift"
    if "弹力带硬拉" in raw:
        return "banded deadlift"
    if "背阔激活" in raw or "直臂下压" in raw:
        return "straight-arm lat activation"
    if "高杠深蹲" in raw:
        return "high bar squat"
    if "保加利亚分腿蹲" in raw:
        return "bulgarian split squat"
    if "相扑楔入" in raw or "楔入练习" in raw:
        return "sumo wedge drill"
    if "暂停相扑硬拉" in raw:
        return "paused sumo deadlift"
    if "张力预设" in raw or "预设张力" in raw:
        return "setup tension drill"
    if "股四" in raw or "股四头" in raw:
        return "quad-strength accessory"
    if "股四主导" in raw:
        return "quad-dominant accessory"
    if "锁定强化" in raw:
        return "overload lockout work"
    return None


def _cue_semantically_matches(text: str, canonical: str) -> bool:
    left = text.replace("，", "").replace("。", "").replace(" ", "")
    right = canonical.replace("，", "").replace("。", "").replace(" ", "")
    return left == right


def _safe_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    return None


def _clamp_confidence(value: Any, default: Any) -> float:
    base = value if isinstance(value, (int, float)) else default
    try:
        return max(0.0, min(1.0, float(base)))
    except (TypeError, ValueError):
        return 0.5


def _sha256_text(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _ssl_verify_setting() -> bool | str:
    flag = (
        os.environ.get("OPENAI_SSL_VERIFY")
        or os.environ.get("SSC_LLM_SSL_VERIFY")
        or "1"
    ).strip().lower()
    if flag in {"0", "false", "off", "no"}:
        return False
    cafile = os.environ.get("OPENAI_CA_BUNDLE") or os.environ.get("SSC_LLM_CA_BUNDLE")
    if cafile:
        return cafile
    return True


def _issue_title(name: str) -> str:
    return {
        "slow_concentric_speed": "起立速度偏慢",
        "grindy_ascent": "起立过程过于吃力",
        "bar_path_drift": "杠铃路径漂移",
        "mid_ascent_sticking_point": "起立中段卡顿",
        "torso_position_shift": "起立时躯干角度变化偏大",
        "upper_back_support_loss": "上背支撑不足",
        "trunk_brace_loss_in_squat": "躯干刚性不足",
        "rep_to_rep_velocity_drop": "后续重复明显掉速",
        "rep_inconsistency": "重复间稳定性不足",
        "insufficient_rule_evidence": "当前证据不足",
        "pelvic_wink": "底部骨盆眨眼",
        "unstable_foot_pressure": "足底重心不稳",
        "stance_setup_mismatch": "站距站姿不匹配",
        "uncontrolled_descent": "下放速度失控",
        "hip_shoot_in_squat": "深蹲起立先抬臀",
        "forward_weight_shift": "深蹲重心前跑",
        "bench_head_lift": "卧推抬头",
        "bench_arch_collapse": "桥塌陷",
        "bench_leg_drive_instability": "下肢张力不足",
        "bench_upper_back_instability": "上背稳定不足",
        "bench_left_right_imbalance": "卧推左右发力不一致",
        "bench_wrist_stack_break": "手腕承重线不稳",
        "bench_touchpoint_instability": "触胸点不稳定",
        "bench_elbow_flare_mismatch": "肘部展开时机不匹配",
        "bench_scapular_control_loss": "肩胛控制丢失",
        "hip_shoot_at_start": "启动抬臀",
        "deadlift_tension_preset_failure": "启动前张力预设不足",
        "deadlift_knee_hip_desync": "髋膝联动不足",
        "bar_drift": "杠铃前飘",
        "lat_lock_missing": "腋下锁杠不足",
        "deadlift_trunk_brace_loss": "硬拉躯干刚性不足",
        "lower_back_rounding": "下背弯曲",
        "lockout_rounding": "锁定姿态不稳",
        "overextended_lockout": "锁定过度后仰",
        "sumo_hip_height_mismatch": "相扑硬拉臀位过高",
        "sumo_wedge_missing": "相扑硬拉预发力不足",
    }.get(name, name.replace("_", " "))


def _taxonomy_recommendation(issue_name: str | None) -> dict[str, Any]:
    defaults = {
        "cue": "优先保持路径稳定和节奏一致",
        "drills": ["tempo variation"],
        "loadAdjustment": "keep_load",
    }
    table: dict[str, dict[str, Any]] = {
        "slow_concentric_speed": {
            "cue": "起立时保持持续加速，不要只在底部发力一下就泄掉",
            "drills": ["pause squat", "squat doubles"],
            "loadAdjustment": "next_set_minus_5_percent",
        },
        "grindy_ascent": {
            "cue": "起立时保持持续加速，不要只在底部发力一下就泄掉",
            "drills": ["pause squat", "squat doubles"],
            "loadAdjustment": "next_set_minus_5_percent",
        },
        "mid_ascent_sticking_point": {
            "cue": "出底后继续向上推地，别在中段泄力",
            "drills": ["pause squat", "tempo squat"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
        "bar_path_drift": {
            "cue": "全程把杠稳在中足上方，起立时不要让杠向前跑",
            "drills": ["tempo squat", "pin squat"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
        "torso_position_shift": {
            "cue": "起立前半程先把胸口和背部顶住杠，再让髋膝一起展开",
            "drills": ["pause squat", "tempo squat"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
        "upper_back_support_loss": {
            "cue": "起立时先把上背顶住杠，胸口别先掉，再让髋膝一起把杠送上去",
            "drills": ["pause squat", "pin squat"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
        "trunk_brace_loss_in_squat": {
            "cue": "下去前锁住，起来时别松，让胸廓到骨盆一直像一整块",
            "drills": ["pause squat", "front squat"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
        "rep_to_rep_velocity_drop": {
            "cue": "每次重复都用同样的准备和节奏，不要越做越急或越做越散",
            "drills": ["tempo squat"],
            "loadAdjustment": "reduce_set_volume_if_quality_drops",
        },
        "rep_inconsistency": {
            "cue": "每次重复都用同样的准备和节奏，不要越做越急或越做越散",
            "drills": ["tempo squat"],
            "loadAdjustment": "reduce_set_volume_if_quality_drops",
        },
        "pelvic_wink": {
            "cue": "下蹲到底时保持骨盆和腰椎中立，不要用骨盆后卷去换深度",
            "drills": ["pause squat", "tempo squat"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
        "unstable_foot_pressure": {
            "cue": "全程把重心稳在全脚掌，别让足底压力前后乱飘",
            "drills": ["tempo squat"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
        "stance_setup_mismatch": {
            "cue": "先把站距和脚尖角度调到让髋膝联动最顺的位置，再去追求深度",
            "drills": ["pause squat"],
            "loadAdjustment": "hold_load",
        },
        "uncontrolled_descent": {
            "cue": "下放速度先控住，给底部留出可控反弹空间",
            "drills": ["tempo squat", "pause squat"],
            "loadAdjustment": "hold_load",
        },
        "hip_shoot_in_squat": {
            "cue": "出底时先把胸口和背撑住，让髋膝一起向上展开",
            "drills": ["pause squat", "box squat"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
        "forward_weight_shift": {
            "cue": "让人和杠一起稳在中足上方，不要把压力一路送到前脚掌",
            "drills": ["box squat", "tempo squat"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
        "bench_head_lift": {
            "cue": "全程保持下巴找胸骨，不要在离心和发力时抬头",
            "drills": ["paused bench"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
        "bench_arch_collapse": {
            "cue": "保持胸骨抬高，让桥在离心和推起中都不被压塌",
            "drills": ["paused bench", "spoto press"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
        "bench_leg_drive_instability": {
            "cue": "先把脚下张力和腿驱动固定住，再让上肢发力",
            "drills": ["paused bench", "spoto press"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
        "bench_upper_back_instability": {
            "cue": "先把肩胛压稳、上背顶牢，再开始每一次下放和上推",
            "drills": ["spoto press", "paused bench"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
        "bench_left_right_imbalance": {
            "cue": "让两侧肩胛和胸背张力先对称，再去发力推杠",
            "drills": ["paused bench"],
            "loadAdjustment": "hold_load",
        },
        "bench_wrist_stack_break": {
            "cue": "让手腕、前臂和杠铃承重线叠稳，别让手腕先塌掉",
            "drills": ["paused bench", "spoto press"],
            "loadAdjustment": "hold_load",
        },
        "bench_touchpoint_instability": {
            "cue": "每次都把杠稳定下到同一个触胸点，再沿同一路径推回去",
            "drills": ["paused bench", "spoto press"],
            "loadAdjustment": "hold_load",
        },
        "bench_elbow_flare_mismatch": {
            "cue": "离心和推起时让前臂承重线稳定，不要过早外展或过度夹肘",
            "drills": ["paused bench", "spoto press"],
            "loadAdjustment": "hold_load",
        },
        "bench_scapular_control_loss": {
            "cue": "让肩胛下沉后稳定贴住凳面，整次离心和推起都别丢控制",
            "drills": ["paused bench", "spoto press"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
        "hip_shoot_at_start": {
            "cue": "启动前先把腿蹬满，再让杠离地，别一上来先抬臀",
            "drills": ["tempo deadlift"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
        "deadlift_tension_preset_failure": {
            "cue": "拉之前先把自己和杠连成一个整体，再让杠离地",
            "drills": ["paused deadlift", "setup tension drill"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
        "deadlift_knee_hip_desync": {
            "cue": "启动时让膝和髋一起参与，不要只用髋去拽杠",
            "drills": ["paused deadlift", "quad-dominant accessory"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
        "bar_drift": {
            "cue": "让杠更贴近身体上升，别在启动和过膝时往前飘",
            "drills": ["paused deadlift", "banded deadlift"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
        "lat_lock_missing": {
            "cue": "先把腋下压住杠，再让腿和髋去完成启动",
            "drills": ["straight-arm lat activation", "paused deadlift"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
        "deadlift_trunk_brace_loss": {
            "cue": "从预拉到过膝都把躯干锁成一整块，别让杠一离地身体就先散",
            "drills": ["paused deadlift", "setup tension drill"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
        "lower_back_rounding": {
            "cue": "启动前先把腿和躯干一起顶住，避免下背先塌掉",
            "drills": ["paused deadlift", "quad-dominant accessory"],
            "loadAdjustment": "next_set_minus_5_percent",
        },
        "lockout_rounding": {
            "cue": "锁定时先把髋伸直站稳，不要靠圆肩或后仰去凑完成",
            "drills": ["banded deadlift", "overload lockout work"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
        "overextended_lockout": {
            "cue": "锁定只需要站直到位，不要再继续后仰去找完成感",
            "drills": ["banded deadlift", "paused deadlift"],
            "loadAdjustment": "hold_load",
        },
        "sumo_hip_height_mismatch": {
            "cue": "相扑准备位先找能把股四和髋同时接上的臀位，不要一上来就把臀抬太高",
            "drills": ["high bar squat", "bulgarian split squat"],
            "loadAdjustment": "hold_load",
        },
        "sumo_wedge_missing": {
            "cue": "先把脚、髋、腋下和杠楔在一起，再让杠离地",
            "drills": ["sumo wedge drill", "paused sumo deadlift"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
    }
    if issue_name and issue_name in table:
        return table[issue_name]
    return defaults


def _issue_taxonomy(exercise: str) -> list[dict[str, str]]:
    common = [
        {"code": "slow_concentric_speed", "title": "起立速度偏慢"},
        {"code": "mid_ascent_sticking_point", "title": "起立中段卡顿"},
            {"code": "bar_path_drift", "title": "杠铃路径漂移"},
            {"code": "torso_position_shift", "title": "起立时躯干角度变化偏大"},
            {"code": "upper_back_support_loss", "title": "上背支撑不足"},
            {"code": "trunk_brace_loss_in_squat", "title": "躯干刚性不足"},
            {"code": "rep_to_rep_velocity_drop", "title": "后续重复明显掉速"},
        {"code": "rep_inconsistency", "title": "重复间稳定性不足"},
        {"code": "insufficient_rule_evidence", "title": "当前证据不足"},
    ]
    if exercise == "squat":
        return common + [
            {"code": "pelvic_wink", "title": "底部骨盆眨眼"},
            {"code": "unstable_foot_pressure", "title": "足底重心不稳"},
            {"code": "stance_setup_mismatch", "title": "站距站姿不匹配"},
            {"code": "uncontrolled_descent", "title": "下放速度失控"},
            {"code": "hip_shoot_in_squat", "title": "深蹲起立先抬臀"},
            {"code": "forward_weight_shift", "title": "深蹲重心前跑"},
        ]
    if exercise == "bench":
        return [
            {"code": "bench_head_lift", "title": "卧推抬头"},
            {"code": "bench_arch_collapse", "title": "桥塌陷"},
            {"code": "bench_leg_drive_instability", "title": "下肢张力不足"},
            {"code": "bench_upper_back_instability", "title": "上背稳定不足"},
            {"code": "bench_left_right_imbalance", "title": "卧推左右发力不一致"},
            {"code": "bench_wrist_stack_break", "title": "手腕承重线不稳"},
            {"code": "bench_touchpoint_instability", "title": "触胸点不稳定"},
            {"code": "bench_elbow_flare_mismatch", "title": "肘部展开时机不匹配"},
            {"code": "bench_scapular_control_loss", "title": "肩胛控制丢失"},
        ]
    if exercise == "deadlift":
        return [
            {"code": "hip_shoot_at_start", "title": "启动抬臀"},
            {"code": "deadlift_tension_preset_failure", "title": "启动前张力预设不足"},
            {"code": "deadlift_knee_hip_desync", "title": "髋膝联动不足"},
            {"code": "bar_drift", "title": "杠铃前飘"},
            {"code": "lat_lock_missing", "title": "腋下锁杠不足"},
            {"code": "deadlift_trunk_brace_loss", "title": "硬拉躯干刚性不足"},
            {"code": "lower_back_rounding", "title": "下背弯曲"},
            {"code": "lockout_rounding", "title": "锁定姿态不稳"},
            {"code": "overextended_lockout", "title": "锁定过度后仰"},
            {"code": "sumo_hip_height_mismatch", "title": "相扑硬拉臀位过高"},
            {"code": "sumo_wedge_missing", "title": "相扑硬拉预发力不足"},
        ]
    return common


def _canonical_issue_name(name: str | None, *, title: str | None) -> str | None:
    if not name and not title:
        return None
    candidate = name or ""
    title_text = (title or "").strip()
    if candidate in {
        "slow_concentric_speed",
        "grindy_ascent",
        "mid_ascent_sticking_point",
        "bar_path_drift",
        "torso_position_shift",
        "upper_back_support_loss",
        "trunk_brace_loss_in_squat",
        "rep_to_rep_velocity_drop",
        "rep_inconsistency",
        "insufficient_rule_evidence",
        "pelvic_wink",
        "unstable_foot_pressure",
        "stance_setup_mismatch",
        "uncontrolled_descent",
        "hip_shoot_in_squat",
        "forward_weight_shift",
        "bench_head_lift",
        "bench_arch_collapse",
        "bench_leg_drive_instability",
        "bench_upper_back_instability",
        "bench_left_right_imbalance",
        "bench_wrist_stack_break",
        "bench_touchpoint_instability",
        "bench_elbow_flare_mismatch",
        "bench_scapular_control_loss",
        "hip_shoot_at_start",
        "deadlift_tension_preset_failure",
        "deadlift_knee_hip_desync",
        "bar_drift",
        "lat_lock_missing",
        "deadlift_trunk_brace_loss",
        "lower_back_rounding",
        "lockout_rounding",
        "overextended_lockout",
        "sumo_hip_height_mismatch",
        "sumo_wedge_missing",
    }:
        return candidate

    text = f"{candidate} {title_text}".lower()
    mappings = [
        (("速度偏慢", "slow", "grindy", "吃力"), "slow_concentric_speed"),
        (("卡顿", "sticking", "中段减速"), "mid_ascent_sticking_point"),
        (("路径", "漂移", "飘杠", "drift"), "bar_path_drift"),
        (("躯干", "前倾", "胸背姿态"), "torso_position_shift"),
        (("上背支撑", "上背没顶住", "胸背没顶住", "胸口先掉", "背散了"), "upper_back_support_loss"),
        (("躯干刚性", "brace", "核心没收紧", "腰腹松", "漏气", "核心松掉"), "trunk_brace_loss_in_squat"),
        (("掉速", "速度损失"), "rep_to_rep_velocity_drop"),
        (("稳定性", "不一致", "波动"), "rep_inconsistency"),
        (("骨盆眨眼", "骨盆翻转", "butt wink"), "pelvic_wink"),
        (("足底重心", "重心不稳"), "unstable_foot_pressure"),
        (("站距", "站姿"), "stance_setup_mismatch"),
        (("下放", "失控", "太快"), "uncontrolled_descent"),
        (("先抬臀", "抬臀式起立", "good morning squat", "good_morning_squat", "屁股先起"), "hip_shoot_in_squat"),
        (("重心前跑", "前脚掌", "重心前移", "追杠"), "forward_weight_shift"),
        (("抬头",), "bench_head_lift"),
        (("桥塌", "塌桥", "arch collapse"), "bench_arch_collapse"),
        (("下肢张力", "腿驱动"), "bench_leg_drive_instability"),
        (("上背稳定", "肩胛"), "bench_upper_back_instability"),
        (("左右", "不平衡"), "bench_left_right_imbalance"),
        (("手腕", "承重线", "stack"), "bench_wrist_stack_break"),
        (("触胸点", "落点", "touch point"), "bench_touchpoint_instability"),
        (("肘部展开", "外展时机", "flare"), "bench_elbow_flare_mismatch"),
        (("肩胛控制", "肩胛前倾", "肩胛翻", "肩胛跑掉"), "bench_scapular_control_loss"),
        (("抬臀",), "hip_shoot_at_start"),
        (("张力预设", "预设张力", "启动前张力", "接住杠铃"), "deadlift_tension_preset_failure"),
        (("髋膝联动", "只用髋", "膝没接上"), "deadlift_knee_hip_desync"),
        (("前飘", "飘杠"), "bar_drift"),
        (("腋下锁杠", "锁杠不足", "背阔没锁"), "lat_lock_missing"),
        (("硬拉躯干刚性", "硬拉核心松", "离地后散掉", "杠一离地身体就散"), "deadlift_trunk_brace_loss"),
        (("下背弯", "腰部弯"), "lower_back_rounding"),
        (("锁定", "圆肩"), "lockout_rounding"),
        (("后仰锁定", "锁定过头", "过度后仰"), "overextended_lockout"),
        (("相扑", "臀位过高", "宽站传统"), "sumo_hip_height_mismatch"),
        (("相扑", "楔入", "预发力不足", "楔在一起"), "sumo_wedge_missing"),
        (("证据不足",), "insufficient_rule_evidence"),
    ]
    for keys, code in mappings:
        if any(k in text for k in keys):
            return code
    return name


@lru_cache(maxsize=1)
def _load_knowledge_base_text() -> str:
    candidates = [
        os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "..",
                "model",
                "力量举技术筛查手册_v2_app版.md",
            )
        ),
        os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "..",
                "model",
                "力量举技术筛查手册.md",
            )
        ),
    ]
    for path in candidates:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
    return ""


def _knowledge_excerpt(exercise: str) -> str:
    text = _load_knowledge_base_text()
    if not text:
        return ""
    section = _extract_exercise_section(text, exercise)
    boundary = _extract_boundary_section(text)
    indirect = _extract_indirect_inference_section(text)
    parts = [part for part in [indirect, section, boundary] if part]
    if parts:
        return "\n\n".join(parts)[:7000]
    if section:
        return section
    return text[:4000]


def _extract_exercise_section(text: str, exercise: str) -> str:
    markers = {
        "squat": [
            ["## 3. 深蹲 Taxonomy", "## 4. 卧推 Taxonomy"],
            ["## 第一章：深蹲技术筛查", "## 第二章：卧推技术筛查"],
        ],
        "bench": [
            ["## 4. 卧推 Taxonomy", "## 5. 传统硬拉 / 相扑硬拉 Taxonomy"],
            ["## 第二章：卧推技术筛查", "## 第三章：传统硬拉技术筛查"],
        ],
        "deadlift": [
            ["## 5. 传统硬拉 / 相扑硬拉 Taxonomy", "## 6. App 使用建议"],
            ["## 第三章：传统硬拉技术筛查", "## 第五章：辅助训练与技术"],
        ],
    }
    start_end_pairs = markers.get(exercise)
    if not start_end_pairs:
        return text[:4000]
    for start_marker, end_marker in start_end_pairs:
        start = text.find(start_marker)
        if start < 0:
            continue
        end = text.find(end_marker, start + len(start_marker))
        excerpt = text[start:end] if end > start else text[start:]
        return excerpt.strip()[:5000]
    return text[:4000]


def _extract_boundary_section(text: str) -> str:
    start_marker = "## 8. 边界判定与去重规则"
    fallback_marker = "## 8. 备注"
    start = text.find(start_marker)
    if start < 0:
        return ""
    end = text.find(fallback_marker, start + len(start_marker))
    excerpt = text[start:end] if end > start else text[start:]
    return excerpt.strip()[:2200]


def _extract_indirect_inference_section(text: str) -> str:
    start_marker = "### 1.4 对“不能直接看见本体”的问题，如何判断"
    fallback_marker = "---"
    start = text.find(start_marker)
    if start < 0:
        return ""
    end = text.find(fallback_marker, start + len(start_marker))
    excerpt = text[start:end] if end > start else text[start:]
    return excerpt.strip()[:1800]
