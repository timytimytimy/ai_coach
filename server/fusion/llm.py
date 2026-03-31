from __future__ import annotations

import json
import logging
import os
import re
import time
import mimetypes
import base64
from typing import Any
from functools import lru_cache
from pathlib import Path

import httpx
from openai import APITimeoutError, OpenAI
from pydantic import ValidationError

from server.fusion.schema import FusionAnalysis
from server.video import extract_llm_keyframes

_LOG = logging.getLogger("ssc.fusion")


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
    rule_evidence: dict[str, Any] | None = None,
    fallback_analysis: dict[str, Any] | None = None,
    rule_analysis: dict[str, Any] | None = None,
    video_path: str | None = None,
    duration_ms: int | None = None,
    coach_soul: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if fallback_analysis is None and isinstance(rule_analysis, dict):
        fallback_analysis = rule_analysis
    if rule_evidence is None:
        if isinstance(rule_analysis, dict):
            rule_evidence = _rule_candidate_snapshot(rule_analysis)
        else:
            rule_evidence = {}
    if fallback_analysis is None:
        fallback_analysis = {}
    if not _llm_should_run():
        return (
            {**fallback_analysis, "source": "rules"},
            {"enabled": False, "used": False, "reason": "llm_disabled"},
        )

    try:
        payload, request_meta = _call_openai_chat(
            exercise=exercise,
            features=features,
            phases=phases,
            pose_result=pose_result,
            video_quality=video_quality,
            rule_evidence=rule_evidence,
            video_path=video_path,
            duration_ms=duration_ms,
            coach_soul=coach_soul,
        )
        screening = _normalize_screening_checklist(
            payload.get("screeningChecklist"),
            exercise=exercise,
        )
        analysis = _normalize_llm_analysis(
            exercise=exercise,
            payload=payload,
            fallback=fallback_analysis,
            screening=screening,
        )
        _LOG.info(
            "fusion_llm_result exercise=%s model=%s rawIssues=%s normalizedIssues=%s source=llm requestMetrics=%s",
            exercise,
            _llm_model(),
            _issue_names_for_log(payload.get("issues")),
            _issue_names_for_log(analysis.get("issues")),
            request_meta,
        )
        return (
            {**analysis, "source": "llm"},
            {
                "enabled": True,
                "used": True,
                "provider": "openai",
                "model": _llm_model(),
                "coachSoul": {
                    "id": _selected_coach_soul_id(coach_soul),
                    "included": bool(_coach_soul_excerpt(coach_soul)),
                },
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
        _LOG.warning(
            "fusion_llm_fallback exercise=%s model=%s reason=%s requestMetrics=%s fallbackIssues=%s",
            exercise,
            _llm_model(),
            str(exc),
            exc.request_meta,
            _issue_names_for_log(fallback_analysis.get("issues")),
        )
        return (
            {**fallback_analysis, "source": "rules"},
            {
                "enabled": True,
                "used": False,
                "provider": "openai",
                "model": _llm_model(),
                "coachSoul": {
                    "id": _selected_coach_soul_id(coach_soul),
                    "included": bool(_coach_soul_excerpt(coach_soul)),
                },
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
        _LOG.exception(
            "fusion_llm_exception exercise=%s model=%s fallbackIssues=%s",
            exercise,
            _llm_model(),
            _issue_names_for_log(fallback_analysis.get("issues")),
        )
        return (
            {**fallback_analysis, "source": "rules"},
            {
                "enabled": True,
                "used": False,
                "provider": "openai",
                "model": _llm_model(),
                "coachSoul": {
                    "id": _selected_coach_soul_id(coach_soul),
                    "included": bool(_coach_soul_excerpt(coach_soul)),
                },
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
        or "gemini-3-pro-preview-new"
    )


def llm_supports_video_input(model_name: str | None = None) -> bool:
    model = (model_name or _llm_model()).strip().lower()
    if model.startswith("gemini"):
        return True
    if model.startswith("doubao"):
        return True
    if model.startswith("gpt"):
        return False
    return False


def _call_openai_chat(
    *,
    exercise: str,
    features: dict[str, Any],
    phases: list[dict[str, Any]],
    pose_result: dict[str, Any] | None,
    video_quality: dict[str, Any] | None,
    rule_evidence: dict[str, Any],
    video_path: str | None,
    duration_ms: int | None,
    coach_soul: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    attempts = _llm_attempts(video_path=video_path)
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
                rule_evidence=rule_evidence,
                video_path=video_path,
                duration_ms=duration_ms,
                max_frames=attempt["max_frames"],
                max_edge=attempt["max_edge"],
                jpeg_quality=attempt["jpeg_quality"],
                coach_soul=coach_soul,
                media_mode=attempt["media_mode"],
            )
            response = client.chat.completions.create(
                model=_llm_model(),
                temperature=0.2,
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
                    "mediaMode": attempt["media_mode"],
                    "latencyMs": latency_ms,
                    "status": "succeeded",
                }
            )
            _LOG.info(
                "fusion_llm_request_succeeded exercise=%s model=%s mediaMode=%s latencyMs=%s promptTokens=%s completionTokens=%s totalTokens=%s rawContent=%s",
                exercise,
                _llm_model(),
                attempt["media_mode"],
                latency_ms,
                (usage or {}).get("promptTokens"),
                (usage or {}).get("completionTokens"),
                (usage or {}).get("totalTokens"),
                _truncate_for_log(content),
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
                    "mediaMode": attempt["media_mode"],
                    "latencyMs": latency_ms,
                    "status": "timeout",
                    "error": str(exc),
                }
            )
            if index == len(attempts) - 1:
                break
            continue
        except Exception:
            _LOG.exception(
                "fusion_llm_request_failed exercise=%s model=%s mediaMode=%s",
                exercise,
                _llm_model(),
                attempt["media_mode"],
            )
            raise
    if last_error is not None:
        raise _LlmRequestFailure(
            "Request timed out after retries "
            f"(frames={attempts[0]['max_frames']}->{attempts[-1]['max_frames']}, "
            f"timeout={attempts[0]['timeout_sec']}->{attempts[-1]['timeout_sec']}s, "
            f"attempts={len(attempts)}).",
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
    rule_evidence: dict[str, Any],
    has_video: bool,
    coach_soul: str | None = None,
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
            rule_evidence=rule_evidence,
            coach_soul=coach_soul,
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
    config = _load_prompt_config()
    items = config.get("system")
    if isinstance(items, list):
        text = "\n".join(f"- {str(item).strip()}" for item in items if str(item).strip())
        if text:
            return text
    return (
        "你是一位带出过多位世界冠军的力量举教练，长期从事深蹲、卧推、硬拉和相扑硬拉的教学、比赛指导与技术复盘。"
        "你的角色不是机器审表员，而是真正会看动作、会抓主次、会给人改动作的顶级教练。"
        "你现在要像高水平教练一样先看动作，再结合数据做校正，而不是先复述规则。"
        "你只能基于给定的视频关键帧、结构化证据、教练风格指南和技术手册生成结论，不能编造新的测量值。"
        "视频视觉判断是主观察源；杠铃轨迹、VBT、pose 和规则候选只用于验证、校正、补充，不是先验结论。"
        "如果提供了技术筛查手册，请优先按手册中的筛查点、理想状态、错误代偿、纠正逻辑来归纳问题和建议。"
        "如果手册中提供了边界判定与去重规则，必须优先遵守，避免把同一现象拆成重复问题。"
        "如果手册中说明某类问题属于‘不能直接看见本体、只能通过外在表现推断’，你必须遵守这种边界。"
        "你的基本观察方法必须符合优秀力量举教练常用的方法：先看准备与站位，再看离心/下放，再看底部或触胸，再看向心/起立，再看锁定；同时比较前后重复的节奏、稳定性和疲劳后的动作变化。"
        "你要优先观察外在表现：重心和力线、杠铃与身体的关系、胸背是否稳定、髋膝或上下肢是否协同、动作是否出现两段式发力、节奏是否被打断、左右是否对称、离心和向心是否连贯。"
        "你要像教练一样先抓‘最影响这组表现的主矛盾’，不要一上来平铺很多小问题。"
        "对肩胛控制、上背支撑、桥塌、brace、张力预设、腋下锁杠这类问题，不要假装直接看见了肌肉或关节本体。"
        "这类问题应该描述为基于连续动作表现、平台稳定性、路径变化、左右时序和相关证据做出的推断。"
        "如果证据不够强，优先输出为 possible 或继续观察，不要高置信硬下结论。"
        "你必须先对给定 taxonomy 中的每一个问题做逐项筛查，再输出最终 1-3 个主问题。"
        "逐项筛查时，先给出 visualAssessment，再给出 structuredAssessment，最后给出 finalAssessment。"
        "如果视频里明显看得出问题，但结构化证据较弱，可以给 possible；如果规则提到了问题但视频里看不出来，也可以降级或否决。"
        "你的结论必须遵守‘先说现象，再说更可能的技术含义，最后给出可执行的下一组提示’这个顺序。"
        "当你给动作建议时，优先使用教练口吻的可执行 cue，例如顶住上背、稳住胸背、脚下持续推地、髋膝一起展开、保持全程张力，而不是只给抽象结论。"
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
    rule_evidence: dict[str, Any],
    coach_soul: str | None = None,
) -> str:
    config = _load_prompt_config()
    task = str(
        config.get("task")
        or "基于给定的视频输入、技术手册、教练风格和结构化证据，生成最终技术分析 JSON。先做视觉筛查，再用结构化证据校正。保留稳定 schema，不要输出 markdown。"
    )
    constraints = config.get("constraints") if isinstance(config.get("constraints"), list) else []
    analysis_protocol = config.get("analysisProtocol") if isinstance(config.get("analysisProtocol"), list) else []
    issue_taxonomy = _issue_taxonomy(exercise)
    coach_soul_id = _selected_coach_soul_id(coach_soul)
    coach_soul_text = _coach_soul_excerpt(coach_soul)
    knowledge_text = _knowledge_excerpt(exercise)
    structured_evidence = _format_structured_evidence_text(
        features=_feature_snapshot(features),
        pose_quality=(pose_result or {}).get("quality"),
        video_quality=_video_quality_snapshot(video_quality),
        rule_candidates=_rule_candidate_snapshot(rule_evidence),
    )
    drill_candidates = _format_drill_candidates_text(_drill_candidate_pool(exercise))
    taxonomy_text = _format_taxonomy_text(issue_taxonomy)
    output_format = _output_format_text()

    sections = [
        _prompt_section("角色", "带出过多位世界冠军的力量举教练，负责先看片、抓主矛盾、再结合证据做校正。"),
        _prompt_section("性格", f"当前教练风格：{coach_soul_id}\n{coach_soul_text}" if coach_soul_text else f"当前教练风格：{coach_soul_id}"),
        _prompt_section(
            "技能",
            "\n".join(
                [
                    "1. 先按动作阶段观察视频，而不是先复述规则。",
                    "2. 优先抓外在动作表现：重心和力线、杠铃与身体关系、胸背稳定性、髋膝或上下肢协同、节奏是否中断、左右是否对称。",
                    "3. 对不能直接看见本体的问题，只能基于外在表现做推断。",
                    "4. 先完成逐项筛查，再输出 1-3 个最值得先改的问题。",
                ]
            ),
        ),
        _prompt_section(
            "参考资料",
            "\n\n".join(
                part
                for part in [
                    "稳定 taxonomy：\n" + taxonomy_text if taxonomy_text else "",
                    "技术手册：\n" + knowledge_text if knowledge_text else "",
                    "输出约束：\n" + _format_list_block(constraints) if constraints else "",
                    "分析流程：\n" + _format_list_block(analysis_protocol) if analysis_protocol else "",
                    "可选训练动作：\n" + drill_candidates if drill_candidates else "",
                ]
                if part
            ),
        ),
        _prompt_section(
            "任务",
            f"{task}\n请先看后面提供的视频或关键帧，再结合教练风格、技术手册和结构化证据完成逐项筛查与最终分析。技术手册和 taxonomy 是帮助你观察、解释和组织语言的参考资料，不是要你机械照抄的模板。应以视频里真实看到的动作表现为主，再用参考资料帮助归因、总结和给出解决方案。输出必须是 JSON 对象，不要输出 markdown，不要输出代码块。",
        ),
        _prompt_section("输出格式", output_format),
        _prompt_section("证据", structured_evidence),
    ]
    return "\n\n".join(section for section in sections if section.strip())


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
    rule_evidence: dict[str, Any],
    video_path: str | None,
    duration_ms: int | None,
    max_frames: int,
    max_edge: int,
    jpeg_quality: int,
    coach_soul: str | None = None,
    media_mode: str = "image",
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
                rule_evidence=rule_evidence,
                coach_soul=coach_soul,
            ),
        }
    ]
    if not video_path:
        return content

    if media_mode == "video":
        video_part = _video_content_item(video_path)
        if video_part is not None:
            content.append(
                {
                    "type": "text",
                    "text": "下面附上原始视频。请先完整观察动作过程，再结合后面的规则和证据校正。",
                }
            )
            content.append(video_part)
            return content

    keyframes = extract_llm_keyframes(
        video_path=video_path,
        duration_ms=duration_ms,
        phases=phases,
        rule_analysis=rule_evidence,
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
        frame_label = _keyframe_context_label(
            time_ms=int(time_ms) if isinstance(time_ms, int) else 0,
            phases=phases,
        )
        content.append(
            {
                "type": "text",
                "text": frame_label,
            }
        )
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": data_url},
            }
        )
    return content


def _keyframe_context_label(*, time_ms: int, phases: list[dict[str, Any]]) -> str:
    rep_index: int | None = None
    phase_name: str | None = None
    phase_start: int | None = None
    for phase in phases:
        if not isinstance(phase, dict):
            continue
        start = phase.get("startMs")
        end = phase.get("endMs")
        if not isinstance(start, int) or not isinstance(end, int):
            continue
        if start <= time_ms <= end:
            rep_index = phase.get("repIndex") if isinstance(phase.get("repIndex"), int) else None
            phase_name = _phase_display_name(phase.get("name"))
            phase_start = start
            break
        if start <= time_ms and (phase_start is None or start > phase_start):
            rep_index = phase.get("repIndex") if isinstance(phase.get("repIndex"), int) else rep_index
            phase_name = _phase_display_name(phase.get("name"))
            phase_start = start

    parts = ["关键帧"]
    if rep_index is not None:
        parts.append(f"Rep {rep_index}")
    if phase_name:
        parts.append(f"{phase_name}阶段")
    parts.append(f"{time_ms} ms")
    return " · ".join(parts)


def _phase_display_name(name: Any) -> str:
    phase = str(name or "").strip().lower()
    return {
        "descent": "离心",
        "bottom": "底部",
        "ascent": "起立",
        "lockout": "锁定",
        "chest_touch": "触胸",
        "press": "推起",
        "slack_pull": "预拉",
        "floor_break": "离地",
        "knee_pass": "过膝",
    }.get(phase, phase or "未知")


def _llm_attempts(*, video_path: str | None) -> list[dict[str, Any]]:
    base_timeout = _env_float("SSC_LLM_TIMEOUT_SEC", 180.0)
    retry_timeout = _env_float("SSC_LLM_RETRY_TIMEOUT_SEC", 180.0)
    if video_path and _llm_supports_video_input():
        return [
            {
                "media_mode": "video",
                "timeout_sec": base_timeout,
                "max_frames": 0,
                "max_edge": 0,
                "jpeg_quality": 0,
            },
            {
                "media_mode": "video",
                "timeout_sec": retry_timeout,
                "max_frames": 0,
                "max_edge": 0,
                "jpeg_quality": 0,
            },
            {
                "media_mode": "video",
                "timeout_sec": retry_timeout,
                "max_frames": 0,
                "max_edge": 0,
                "jpeg_quality": 0,
            },
        ]
    return [
        {
            "media_mode": "image",
            "timeout_sec": base_timeout,
            "max_frames": _env_int("SSC_LLM_MAX_FRAMES", 18),
            "max_edge": _env_int("SSC_LLM_KEYFRAME_MAX_EDGE", 576),
            "jpeg_quality": _env_int("SSC_LLM_KEYFRAME_JPEG_QUALITY", 72),
        },
        {
            "media_mode": "image",
            "timeout_sec": retry_timeout,
            "max_frames": _env_int("SSC_LLM_RETRY_MAX_FRAMES", 8),
            "max_edge": _env_int("SSC_LLM_RETRY_KEYFRAME_MAX_EDGE", 448),
            "jpeg_quality": _env_int("SSC_LLM_RETRY_KEYFRAME_JPEG_QUALITY", 60),
        },
        {
            "media_mode": "image",
            "timeout_sec": retry_timeout,
            "max_frames": _env_int("SSC_LLM_RETRY_MAX_FRAMES", 8),
            "max_edge": _env_int("SSC_LLM_RETRY_KEYFRAME_MAX_EDGE", 448),
            "jpeg_quality": _env_int("SSC_LLM_RETRY_KEYFRAME_JPEG_QUALITY", 60),
        },
    ]


def _llm_supports_video_input() -> bool:
    model = _llm_model().lower()
    return model.startswith("ep-") or "seed" in model or "gemini" in model


def _video_content_item(video_path: str) -> dict[str, Any] | None:
    path = Path(video_path)
    if not path.exists():
        return None
    try:
        mime_type, _ = mimetypes.guess_type(str(path))
        mime_type = mime_type or "video/mp4"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return {
            "type": "video_url",
            "video_url": {
                "url": f"data:{mime_type};base64,{encoded}",
            },
        }
    except Exception:
        return None




def _feature_snapshot(features: dict[str, Any]) -> dict[str, Any]:
    rep_summaries = features.get("repSummaries")
    compact_reps: list[dict[str, Any]] = []
    if isinstance(rep_summaries, list):
        sorted_reps = [rep for rep in rep_summaries if isinstance(rep, dict)]
        sorted_reps.sort(
            key=lambda rep: (
                _safe_float(rep.get("avgVelocityMps")) or 999.0,
                -(_safe_int(rep.get("durationMs")) or 0),
            )
        )
        selected: list[dict[str, Any]] = []
        seen: set[int] = set()
        for rep in sorted_reps[:1]:
            rep_index = _safe_int(rep.get("repIndex"))
            if rep_index is not None:
                seen.add(rep_index)
            selected.append(rep)
        if sorted_reps:
            fastest = max(sorted_reps, key=lambda rep: _safe_float(rep.get("avgVelocityMps")) or -1.0)
            rep_index = _safe_int(fastest.get("repIndex"))
            if rep_index is None or rep_index not in seen:
                if rep_index is not None:
                    seen.add(rep_index)
                selected.append(fastest)
        for rep in sorted_reps:
            sticking = rep.get("stickingRegion")
            rep_index = _safe_int(rep.get("repIndex"))
            has_sticking = isinstance(sticking, dict) and any(
                sticking.get(key) is not None for key in ("durationMs", "startMs", "endMs")
            )
            if has_sticking and (rep_index is None or rep_index not in seen):
                if rep_index is not None:
                    seen.add(rep_index)
                selected.append(rep)
                break
        for rep in selected[:3]:
            if not isinstance(rep, dict):
                continue
            compact_reps.append(
                {
                    "repIndex": rep.get("repIndex"),
                    "timeRangeMs": rep.get("timeRangeMs"),
                    "avgVelocityMps": rep.get("avgVelocityMps"),
                    "durationMs": rep.get("durationMs"),
                    "barPathDriftCm": rep.get("barPathDriftCm"),
                    "torsoLeanDeltaDeg": rep.get("torsoLeanDeltaDeg"),
                    "minKneeAngleDeg": rep.get("minKneeAngleDeg"),
                    "minHipAngleDeg": rep.get("minHipAngleDeg"),
                    "minElbowAngleDeg": rep.get("minElbowAngleDeg"),
                    "avgWristStackOffsetPx": rep.get("avgWristStackOffsetPx"),
                    "stickingDurationMs": ((rep.get("stickingRegion") or {}).get("durationMs") if isinstance(rep.get("stickingRegion"), dict) else None),
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
        "keyRepSummaries": compact_reps,
    }


def _prompt_section(title: str, body: str) -> str:
    cleaned = body.strip()
    return f"# {title}：\n{cleaned}" if cleaned else f"# {title}："


def _truncate_for_log(value: Any, limit: int = 1600) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "...<truncated>"


def _issue_names_for_log(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        title = _clean_text(item.get("title"))
        name = _clean_text(item.get("name"))
        names.append(title or name or "unknown_issue")
    return names


def _format_list_block(items: list[Any]) -> str:
    lines = [f"- {str(item).strip()}" for item in items if str(item).strip()]
    return "\n".join(lines)


def _format_taxonomy_text(codes: list[Any]) -> str:
    lines: list[str] = []
    for item in codes:
        if isinstance(item, dict):
            code_text = _clean_text(item.get("code")) or str(item.get("code"))
            title = _clean_text(item.get("title")) or _issue_title(code_text)
        else:
            code_text = _clean_text(item) or str(item)
            title = _issue_title(code_text)
        if title and title != code_text:
            lines.append(f"- {code_text}: {title}")
        else:
            lines.append(f"- {code_text}")
    return "\n".join(lines)


def _format_drill_candidates_text(candidates: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for item in candidates:
        code = _clean_text(item.get("code")) or ""
        title = _clean_text(item.get("title")) or code
        when_use = _clean_text(item.get("whenUse")) or ""
        text = f"- {code}: {title}"
        if when_use:
            text += f"。适用：{when_use}"
        lines.append(text)
    return "\n".join(lines)


def _format_structured_evidence_text(
    *,
    features: dict[str, Any],
    pose_quality: Any,
    video_quality: dict[str, Any] | None,
    rule_candidates: dict[str, Any],
) -> str:
    numeric_lines: list[str] = []
    for label, key in [
        ("动作", "exercise"),
        ("重复次数", "repCount"),
        ("平均速度(m/s)", "avgRepVelocityMps"),
        ("最好速度(m/s)", "bestRepVelocityMps"),
        ("路径漂移(cm)", "barPathDriftCm"),
        ("速度损失(%)", "velocityLossPct"),
        ("重复速度波动(%)", "repVelocityCvPct"),
        ("平均起立时长(ms)", "avgAscentDurationMs"),
        ("最大躯干角(deg)", "maxTorsoLeanDeg"),
        ("平均躯干变化(deg)", "avgTorsoLeanDeltaDeg"),
        ("最小膝角(deg)", "minKneeAngleDeg"),
        ("最小髋角(deg)", "minHipAngleDeg"),
        ("最小肘角(deg)", "minElbowAngleDeg"),
    ]:
        value = features.get(key)
        if value is not None:
            numeric_lines.append(f"- {label}: {value}")

    key_rep_lines: list[str] = []
    key_reps = features.get("keyRepSummaries")
    if isinstance(key_reps, list):
        for rep in key_reps:
            if not isinstance(rep, dict):
                continue
            rep_index = rep.get("repIndex")
            parts = [f"Rep {rep_index}" if rep_index is not None else "Rep"]
            for label, key in [
                ("时间窗", "timeRangeMs"),
                ("平均速度", "avgVelocityMps"),
                ("时长(ms)", "durationMs"),
                ("路径漂移(cm)", "barPathDriftCm"),
                ("躯干变化(deg)", "torsoLeanDeltaDeg"),
                ("最小膝角(deg)", "minKneeAngleDeg"),
                ("sticking(ms)", "stickingDurationMs"),
            ]:
                value = rep.get(key)
                if value is not None:
                    parts.append(f"{label}={value}")
            key_rep_lines.append("- " + "；".join(parts))

    pose_lines: list[str] = []
    if isinstance(pose_quality, dict):
        for label, key in [
            ("pose可用", "usable"),
            ("主视侧", "primarySide"),
            ("置信度", "confidence"),
        ]:
            value = pose_quality.get(key)
            if value is not None:
                pose_lines.append(f"- {label}: {value}")
    elif pose_quality is not None:
        pose_lines.append(f"- pose质量: {pose_quality}")

    video_lines: list[str] = []
    if isinstance(video_quality, dict):
        warnings = video_quality.get("warnings")
        quality = video_quality.get("quality")
        if quality is not None:
            video_lines.append(f"- 视频质量摘要: {quality}")
        if isinstance(warnings, list) and warnings:
            video_lines.append("- 视频警告: " + "；".join(str(item) for item in warnings[:4]))

    rule_lines: list[str] = []
    measurement_lines: list[str] = []
    candidates = rule_candidates.get("candidates") if isinstance(rule_candidates, dict) else None
    if isinstance(candidates, list):
        for item in candidates[:4]:
            if not isinstance(item, dict):
                continue
            title = _clean_text(item.get("title")) or _clean_text(item.get("code")) or "候选问题"
            confidence = item.get("confidence")
            time_range = item.get("timeRangeMs")
            text = f"- {title}"
            if confidence is not None:
                text += f"，confidence={confidence}"
            if time_range is not None:
                text += f"，timeRangeMs={time_range}"
            rule_lines.append(text)
    measurements = rule_candidates.get("measurements") if isinstance(rule_candidates, dict) else None
    if isinstance(measurements, list):
        measurement_lines = [f"- {item}" for item in measurements[:4] if isinstance(item, str) and item]

    parts = []
    if numeric_lines:
        parts.append("数字证据：\n" + "\n".join(numeric_lines))
    if key_rep_lines:
        parts.append("关键 rep 摘要：\n" + "\n".join(key_rep_lines))
    if pose_lines:
        parts.append("姿态证据：\n" + "\n".join(pose_lines))
    if video_lines:
        parts.append("视频质量：\n" + "\n".join(video_lines))
    if rule_lines:
        parts.append("候选关注点（仅供参考，不是结论）：\n" + "\n".join(rule_lines))
    if measurement_lines:
        parts.append("测量层关键证据：\n" + "\n".join(measurement_lines))
    return "\n\n".join(parts)


def _output_format_text() -> str:
    return "\n".join(
        [
            "{",
            '  "liftType": "string",',
            '  "confidence": "0-1 float",',
            '  "screeningChecklist": [',
            "    {",
            '      "name": "stable taxonomy code",',
            '      "title": "中文标题",',
            '      "visualAssessment": "present|possible|absent|not_supported",',
            '      "structuredAssessment": "present|possible|absent|not_supported",',
            '      "finalAssessment": "present|possible|absent|not_supported",',
            '      "confidence": "0-1 float",',
            '      "reason": "一句中文解释"',
            "    }",
            "  ],",
            '  "issues": [',
            "    {",
            '      "name": "stable taxonomy code",',
            '      "title": "中文标题",',
            '      "severity": "low|medium|high",',
            '      "confidence": "0-1 float",',
            '      "evidenceSource": "fusion",',
            '      "summary": "结合 taxonomy 总结的中文问题概述",',
            '      "whatYouSee": "视频里最像什么现象",',
            '      "whyItHappens": "更像什么技术原因或动作机制",',
            '      "whatToDo": "针对这个问题的直接改法",',
            '      "evidence": ["最关键证据1", "最关键证据2"],',
            '      "visualEvidence": ["中文证据1", "中文证据2"],',
            '      "kinematicEvidence": ["中文证据1", "中文证据2"],',
            '      "timeRangeMs": {"start": 0, "end": 0}',
            "    }",
            "  ],",
            '  "coachFeedback": {',
            '    "focus": "本次重点",',
            '    "why": "为什么这么判断",',
            '    "nextSet": "下组建议",',
            '    "keepWatching": ["继续观察1", "继续观察2"]',
            "  },",
            '  "cue": "一句中文 cue",',
            '  "drills": ["候选训练动作1", "候选训练动作2"],',
            '  "loadAdjustment": "string|null",',
            '  "cameraQualityWarning": "string|null"',
            "}",
            "要求：issues 最多 6 个；drills 最多 2 个；重点把本组问题尽量列清楚，并给出严重度和置信度；每个问题优先写 summary、whatYouSee、whyItHappens、whatToDo 和 1-2 条精简 evidence；可以参考 taxonomy 里的 summary、whatYouSee、whatToDo、cue、drills，但要结合视频里的真实表现重新组织语言，不要机械照抄；不要输出任何 schema 之外的解释文本。",
        ]
    )


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
    if isinstance(rule_analysis.get("candidates"), list):
        return {
            "note": _clean_text(rule_analysis.get("note"))
            or "这些只是系统召回出来的候选关注点，不是最终结论。请先看片，再决定是否采纳、降级或否决。",
            "candidates": rule_analysis.get("candidates"),
            "measurements": rule_analysis.get("measurements")
            if isinstance(rule_analysis.get("measurements"), list)
            else [],
            "cameraQualityWarning": _clean_text(rule_analysis.get("cameraQualityWarning")),
        }

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
        "measurements": [],
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
    exercise: str,
    payload: dict[str, Any],
    fallback: dict[str, Any],
    screening: list[dict[str, Any]],
) -> dict[str, Any]:
    issues = _merge_duplicate_issues(_normalize_issues(payload.get("issues"), None))
    normalized_cue, normalized_drills, normalized_load_adjustment = (
        _normalize_recommendations(
            exercise=exercise,
            issues=issues,
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
            drills=normalized_drills,
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
        fallback_issues = fallback.get("issues") if isinstance(fallback, dict) else []
        if not issues and isinstance(fallback_issues, list):
            merged["issues"] = []
        try:
            validated = FusionAnalysis.model_validate(merged)
            return _humanize_analysis_texts(validated.model_dump())
        except ValidationError:
            return {
                **fallback,
                "issues": [],
                "coachFeedback": merged.get("coachFeedback", fallback.get("coachFeedback")),
                "cue": merged.get("cue", fallback.get("cue")),
                "drills": merged.get("drills", fallback.get("drills")),
                "loadAdjustment": merged.get("loadAdjustment", fallback.get("loadAdjustment")),
            }


def _normalize_issues(candidate: Any, fallback: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    source = candidate if isinstance(candidate, list) else fallback
    if not isinstance(source, list):
        return fallback if isinstance(fallback, list) else []
    for issue in source[:6]:
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
                "summary": _clean_text(issue.get("summary")) or "",
                "whatYouSee": _clean_text(issue.get("whatYouSee")) or "",
                "whyItHappens": _clean_text(issue.get("whyItHappens")) or "",
                "whatToDo": _clean_text(issue.get("whatToDo")) or "",
                "evidence": _normalize_issue_evidence(
                    issue.get("evidence"),
                    visual=issue.get("visualEvidence"),
                    kinematic=issue.get("kinematicEvidence"),
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
    return merged[:6]


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
    drills: list[str],
) -> dict[str, Any]:
    fallback_dict = fallback if isinstance(fallback, dict) else {}
    default = _default_coach_feedback(issues=issues, screening=screening)
    if not isinstance(candidate, dict):
        return {
            "focus": _clean_text(fallback_dict.get("focus")) or default["focus"],
            "why": _clean_text(fallback_dict.get("why")) or default["why"],
            "nextSet": _expand_next_set_with_drills(
                _clean_text(fallback_dict.get("nextSet")) or default["nextSet"],
                drills=drills,
            ),
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
        "nextSet": _expand_next_set_with_drills(
            _clean_text(candidate.get("nextSet"))
            or _clean_text(fallback_dict.get("nextSet"))
            or default["nextSet"],
            drills=drills,
        ),
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
        "mid_ascent_sticking_point": "这组最需要先改的是触底到起立中段这段发力连续性。",
        "slow_concentric_speed": "这组起立整体偏慢，尤其后半组更吃力。",
        "grindy_ascent": "这组起立过程偏拖，后半段发力不够干脆。",
        "torso_position_shift": "这组起立时躯干姿态有点散，胸背稳定性不够。",
        "bar_path_drift": "这组杠铃路径不够稳，起立时有往前跑的趋势。",
    }
    why_map = {
        "rep_to_rep_velocity_drop": "前几次还能维持节奏，后面几次速度和完成质量一起往下掉，疲劳会把问题放大。",
        "mid_ascent_sticking_point": "你不是单纯底部起不来，而是触底后到中段会明显减速，所以看起来像卡一下再继续上。",
        "slow_concentric_speed": "问题不只是速度慢，而是起立发力没有持续顶上去，越到后面越容易拖长。",
        "grindy_ascent": "单次起立时间被拉长，说明这组的发力连续性和完成效率都在往下掉。",
        "torso_position_shift": "触底后躯干角度变化偏大，说明你在用姿态变化帮自己把杠顶起来。",
        "bar_path_drift": "杠没有一直稳在同一条发力线上，路径一散，后面的发力效率就会下降。",
    }
    next_set_map = {
        "rep_to_rep_velocity_drop": "下一组先把每次重复都做成同一个模板，别前面很稳、后面开始越做越散。做的时候抓“每一下下去前都重新锁住、起来时节奏一样”这个感觉；如果做到后半组已经明显磨速，就提前收组或少做 1 到 2 次。",
        "mid_ascent_sticking_point": "下一组先把重点放在触底后继续把地板往下踩、把杠一路顶过中段。做的时候抓“胸背一直顶住杠、速度别在中段断掉”这个感觉；如果第 4 下以后又开始卡顿，就先用暂停深蹲把这一下练顺。",
        "slow_concentric_speed": "下一组先把起立做成持续加速的一整段，不要到底部蹬一下、后面就靠磨。做的时候抓“杠一直往上走、不是突然停一下再补一段”这个感觉；如果第 4 下以后速度已经明显掉，就小幅降重或减少 1 到 2 次。",
        "grindy_ascent": "下一组先把起立做得更连贯，宁可稳一点，也不要中段突然泄力。做的时候抓“出力是一整段，不是卡一下再补一下”这个感觉；如果后半组总磨速，就先减一点组容量。",
        "torso_position_shift": "下一组先把胸口和背撑住杠，再让髋膝一起向上展开。做的时候抓“上背把杠稳住、人和杠一起站起来”这个感觉；如果一加重量就又开始散，先用暂停深蹲或节奏深蹲把前半程稳住。",
        "bar_path_drift": "下一组先把人和杠一起稳在中足上方，再去追速度。做的时候抓“脚下压力稳在中足、杠贴着同一条线上下走”这个感觉；如果一到后半组就开始前跑，就先降一点重量或用 pin squat 守住路径。",
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
                    "summary": _humanize_text(issue.get("summary")),
                    "whatYouSee": _humanize_text(issue.get("whatYouSee")),
                    "whyItHappens": _humanize_text(issue.get("whyItHappens")),
                    "whatToDo": _humanize_text(issue.get("whatToDo")),
                    "evidence": _humanize_string_list(issue.get("evidence")),
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


def _expand_next_set_with_drills(value: Any, *, drills: list[str]) -> str:
    text = _clean_text(value) or ""
    drill_names = _drill_labels_zh(drills)
    if not text:
        return text
    if not drill_names:
        return text
    if any(word in text for word in ("先用", "先练", "辅助练习", "练习")):
        return text
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"[。！？；，, ]+$", "", text)
    if len(drill_names) == 1:
        return f"{text}。如果这一下还是总做不出来，就先用{drill_names[0]}把动作顺序练稳。"
    return f"{text}。如果这一下还是总做不出来，就先用{drill_names[0]}和{drill_names[1]}把动作顺序练稳。"


def _drill_labels_zh(drills: list[str]) -> list[str]:
    mapping = {
        "pause squat": "暂停深蹲",
        "tempo squat": "节奏深蹲",
        "pin squat": "架上蹲",
        "squat doubles": "双次组深蹲",
        "box squat": "箱式深蹲",
        "front squat": "前蹲",
        "paused bench": "暂停卧推",
        "spoto press": "Spoto Press",
        "tempo deadlift": "节奏硬拉",
        "paused deadlift": "暂停硬拉",
        "setup tension drill": "预拉张力练习",
        "banded deadlift": "弹力带硬拉",
        "quad-dominant accessory": "股四主导辅助",
        "straight-arm lat activation": "直臂背阔激活",
        "overload lockout work": "锁定强化练习",
        "high bar squat": "高杠深蹲",
        "bulgarian split squat": "保加利亚分腿蹲",
        "sumo wedge drill": "相扑楔入练习",
        "paused sumo deadlift": "暂停相扑硬拉",
        "tempo variation": "节奏变化练习",
    }
    out: list[str] = []
    for drill in drills:
        label = mapping.get(drill, drill)
        if label not in out:
            out.append(label)
        if len(out) >= 2:
            break
    return out


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


def _normalize_issue_evidence(value: Any, *, visual: Any, kinematic: Any) -> list[str]:
    direct = _normalize_string_list(value)
    if direct:
        return direct[:3]
    merged = _merge_string_lists(kinematic, visual, limit=3)
    return merged[:3]


def _normalize_drills(candidate: Any, fallback: Any) -> list[str]:
    drills = _normalize_string_list(candidate)
    if drills:
        return drills[:2]
    if isinstance(fallback, list):
        return [str(item) for item in fallback if isinstance(item, str)][:2]
    return []


def _normalize_recommendations(
    *,
    exercise: str,
    issues: list[dict[str, Any]] | None,
    cue: Any,
    drills: Any,
    load_adjustment: Any,
    fallback: dict[str, Any],
) -> tuple[str, list[str], str]:
    primary_issue = (
        issues[0]
        if isinstance(issues, list) and issues and isinstance(issues[0], dict)
        else None
    )
    secondary_issues = [
        issue for issue in (issues or [])[1:] if isinstance(issue, dict)
    ]
    issue_name = (
        str(primary_issue.get("name"))
        if isinstance(primary_issue, dict) and isinstance(primary_issue.get("name"), str)
        else None
    )
    rec = _taxonomy_recommendation(issue_name)
    rec = _merge_recommendation_with_secondary_issues(
        recommendation=rec,
        primary_issue_name=issue_name,
        secondary_issues=secondary_issues,
    )

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
        exercise=exercise,
        value=drills,
        default=fallback_drills,
        recommendation=rec,
    )
    normalized_load = _normalize_load_adjustment(
        load_adjustment,
        default=fallback_load,
        recommendation=rec,
    )
    return normalized_cue, normalized_drills, normalized_load


def _merge_recommendation_with_secondary_issues(
    *,
    recommendation: dict[str, Any],
    primary_issue_name: str | None,
    secondary_issues: list[dict[str, Any]],
) -> dict[str, Any]:
    if primary_issue_name not in {
        "slow_concentric_speed",
        "grindy_ascent",
        "rep_to_rep_velocity_drop",
        "rep_inconsistency",
    }:
        return recommendation
    merged_drills = _merge_drills(
        list(recommendation.get("drills") or []),
        _squat_secondary_drills(secondary_issues),
    )
    return {
        **recommendation,
        "drills": merged_drills or list(recommendation.get("drills") or []),
    }


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
    *,
    exercise: str,
    value: Any,
    default: list[str],
    recommendation: dict[str, Any],
) -> list[str]:
    allowed = set(_allowed_drill_codes(exercise))
    drills = _normalize_drills(value, default)
    canonical: list[str] = []
    for drill in drills:
        mapped = _canonical_drill_name(drill)
        if mapped and mapped in allowed and mapped not in canonical:
            canonical.append(mapped)
    if canonical:
        return canonical[:2]
    recommended = [
        drill for drill in list(recommendation["drills"]) if drill in allowed
    ]
    if recommended:
        return recommended[:2]
    fallback_allowed = [drill for drill in default if drill in allowed]
    return fallback_allowed[:2]


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
    if "架上蹲" in raw or "销位深蹲" in raw:
        return "pin squat"
    if "双次组深蹲" in raw or "双次深蹲" in raw:
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


def _safe_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
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
    if not isinstance(name, str):
        return str(name)
    return {
        "slow_concentric_speed": "起立速度偏慢",
        "grindy_ascent": "起立过程过于吃力",
        "bar_path_drift": "杠铃路径漂移",
        "mid_ascent_sticking_point": "起立中段卡顿",
        "torso_position_shift": "起立时躯干角度变化偏大",
        "upper_back_support_loss": "上背支撑不足",
        "trunk_brace_loss_in_squat": "躯干刚性不足",
        "bottom_tension_loss": "底部张力丢失",
        "squat_knee_track_collapse": "膝轨迹控制不足",
        "squat_descent_rhythm_loss": "离心节奏不连贯",
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
        "bench_leg_drive_disconnect": "桥和下肢张力没有真正连通",
        "bench_bounce_dependence": "触胸后反弹依赖过强",
        "bench_uncontrolled_descent": "卧推离心不受控",
        "bench_lockout_quality": "卧推锁定质量差",
        "bench_press_path_recovery_loss": "推起路径回不来",
        "bench_weak_side_lockout_delay": "弱侧锁定更慢",
        "hip_shoot_at_start": "启动抬臀",
        "deadlift_tension_preset_failure": "启动前张力预设不足",
        "deadlift_knee_hip_desync": "髋膝联动不足",
        "bar_drift": "杠铃前飘",
        "lat_lock_missing": "腋下锁杠不足",
        "deadlift_trunk_brace_loss": "硬拉躯干刚性不足",
        "deadlift_knee_pass_transition_loss": "过膝衔接差",
        "deadlift_weight_shift_instability": "硬拉重心前后切换过大",
        "deadlift_bar_separation_at_start": "离地前就把杠往前拉",
        "deadlift_lockout_by_low_back": "锁定时先顶腰，不是先伸髋",
        "deadlift_shrug_arm_takeover": "锁定耸肩，手臂代偿",
        "deadlift_mid_pull_brace_loss": "中段躯干刚性丢失",
        "lower_back_rounding": "下背弯曲",
        "lockout_rounding": "锁定姿态不稳",
        "overextended_lockout": "锁定过度后仰",
        "sumo_hip_height_mismatch": "相扑硬拉臀位过高",
        "sumo_wedge_missing": "相扑硬拉预发力不足",
        "sumo_wedge_timing_loss": "楔入时序不对",
        "sumo_abduction_disconnect": "外展打开不足，导致相扑像宽站传统拉",
        "sumo_arm_line_instability": "手臂不垂直，受力线不干净",
        "sumo_lockout_back_lean_compensation": "锁定时用后仰替代站直",
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
            "drills": ["pause squat", "pin squat"],
            "loadAdjustment": "next_set_minus_5_percent",
        },
        "grindy_ascent": {
            "cue": "起立时保持持续加速，不要只在底部发力一下就泄掉",
            "drills": ["pause squat", "pin squat"],
            "loadAdjustment": "next_set_minus_5_percent",
        },
        "mid_ascent_sticking_point": {
            "cue": "触底后继续向上推地，别在中段泄力",
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
        "bottom_tension_loss": {
            "cue": "触底时先把张力守住，再把底部到起立这一拍顺着接起来，别靠反弹乱找力",
            "drills": ["pause squat", "tempo squat"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
        "squat_knee_track_collapse": {
            "cue": "让脚先踩稳，再让膝持续跟着脚尖方向推开，不要触底后突然往里塌",
            "drills": ["tempo squat", "box squat"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
        "squat_descent_rhythm_loss": {
            "cue": "下放做成同一条路线和同一节奏，别一路犹豫、改重心、再继续下去",
            "drills": ["tempo squat", "pause squat"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
        "rep_to_rep_velocity_drop": {
            "cue": "每次重复都用同样的准备和节奏，不要越做越急或越做越散",
            "drills": ["tempo squat", "pin squat"],
            "loadAdjustment": "reduce_set_volume_if_quality_drops",
        },
        "rep_inconsistency": {
            "cue": "每次重复都用同样的准备和节奏，不要越做越急或越做越散",
            "drills": ["tempo squat", "pin squat"],
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
            "cue": "触底时先把胸口和背撑住，让髋膝一起向上展开",
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
        "bench_leg_drive_disconnect": {
            "cue": "先把脚下张力、桥和上背接成一个平台，再开始每一次离心和推起",
            "drills": ["paused bench", "spoto press"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
        "bench_bounce_dependence": {
            "cue": "先把触胸做得可控、暂停也能稳稳推起，再去追求更快的连续发力",
            "drills": ["paused bench", "spoto press"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
        "bench_uncontrolled_descent": {
            "cue": "先把下放节奏控住，让杠稳定落到同一个触胸点，再去追求更快的推起",
            "drills": ["paused bench", "spoto press"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
        "bench_lockout_quality": {
            "cue": "锁定时先把两侧肩带和杠铃一起站稳，不要靠最后一下乱补路线去凑完成",
            "drills": ["paused bench", "spoto press"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
        "bench_press_path_recovery_loss": {
            "cue": "先把触胸后的第一段推回优势轨道，不要一离胸就让杠迷路、再临时找路线",
            "drills": ["spoto press", "paused bench"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
        "bench_weak_side_lockout_delay": {
            "cue": "让两侧平台先做对称，再让弱侧按同一条路线和节奏跟上，不要总等一边补锁定",
            "drills": ["paused bench", "unilateral accessory"],
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
        "deadlift_knee_pass_transition_loss": {
            "cue": "过膝前后让杠继续贴身上来，把地面发力顺着接到后段，不要到膝附近重新找力",
            "drills": ["tempo deadlift", "paused deadlift"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
        "deadlift_weight_shift_instability": {
            "cue": "从预拉开始就把压力稳在足中，别让离地到过膝一路前后乱切换",
            "drills": ["tempo deadlift", "paused deadlift"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
        "deadlift_bar_separation_at_start": {
            "cue": "离地前先把杠收回身体、接住张力，再让腿和躯干一起把杠带离地面",
            "drills": ["setup tension drill", "paused deadlift"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
        "deadlift_lockout_by_low_back": {
            "cue": "锁定时先把髋伸直到位站直，不要用顶腰或后仰去补最后一下",
            "drills": ["banded deadlift", "overload lockout work"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
        "deadlift_shrug_arm_takeover": {
            "cue": "锁定时先把髋站直到位，肩和手臂只负责稳住，不要靠耸肩或手臂抢活去补完成",
            "drills": ["overload lockout work", "banded deadlift"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
        "deadlift_mid_pull_brace_loss": {
            "cue": "离地到过膝都把躯干守成一整块，别到中段才开始漏气、塌掉再重新找力",
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
        "sumo_wedge_timing_loss": {
            "cue": "先把身体和杠接上，再把脚、膝、髋、腋下按顺序楔成一个整体，不要人先下去杠还没接住",
            "drills": ["sumo wedge drill", "paused sumo deadlift"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
        "sumo_abduction_disconnect": {
            "cue": "先把脚下压力和膝外开接成一体，再把髋和躯干一起楔住，不要做成宽站传统拉",
            "drills": ["sumo wedge drill", "bulgarian split squat"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
        "sumo_arm_line_instability": {
            "cue": "让手臂尽量垂直、杠贴着身体受力，别一开始就把力量线拉歪",
            "drills": ["paused sumo deadlift", "sumo wedge drill"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
        "sumo_lockout_back_lean_compensation": {
            "cue": "相扑锁定时只需要髋伸直到位站直，不要靠继续后仰和顶腰去凑完成",
            "drills": ["paused sumo deadlift", "sumo wedge drill"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
        },
    }
    if issue_name and issue_name in table:
        return table[issue_name]
    return defaults


def _drill_candidate_pool(exercise: str) -> list[dict[str, str]]:
    pools: dict[str, list[tuple[str, str, str]]] = {
        "squat": [
            ("pause squat", "暂停深蹲", "适合触底后张力丢失、底部衔接差、中段卡顿"),
            ("tempo squat", "节奏深蹲", "适合离心节奏乱、路径不稳、重心管理差"),
            ("pin squat", "架上蹲", "适合中段卡顿、路径漂移、起立顺序乱"),
            ("box squat", "箱式深蹲", "适合重心前跑、髋主导控制差、站位不稳"),
            ("front squat", "前蹲", "适合躯干刚性不足、胸背支撑差"),
            ("high bar squat", "高杠深蹲", "适合相扑硬拉辅助，也可用于改善蹲起竖直度"),
        ],
        "bench": [
            ("paused bench", "暂停卧推", "适合触胸不稳、离胸节奏差、整体控制不足"),
            ("spoto press", "Spoto Press", "适合触胸点不稳、肩带平台散、路径不干净"),
        ],
        "deadlift": [
            ("tempo deadlift", "节奏硬拉", "适合启动节奏乱、离地顺序差、过膝衔接差"),
            ("paused deadlift", "暂停硬拉", "适合离地后就散、过膝卡顿、路径不稳"),
            ("setup tension drill", "预拉张力练习", "适合启动前张力预设不足、身体没接住杠"),
            ("banded deadlift", "弹力带硬拉", "适合锁定发力差、路径前飘"),
            ("straight-arm lat activation", "直臂背阔激活", "适合腋下锁杠不足、杠离身"),
            ("quad-dominant accessory", "股四主导辅助", "适合离地时髋膝联动差、膝伸展参与不足"),
            ("overload lockout work", "锁定强化练习", "适合锁定发力不足、末段站不稳"),
            ("sumo wedge drill", "相扑楔入练习", "只在明显相扑硬拉模式时使用，适合楔入和预发力不足"),
            ("paused sumo deadlift", "暂停相扑硬拉", "只在明显相扑硬拉模式时使用，适合离地和过膝衔接差"),
        ],
        "sumo_deadlift": [
            ("sumo wedge drill", "相扑楔入练习", "适合楔入时序不对、预发力不足"),
            ("paused sumo deadlift", "暂停相扑硬拉", "适合离地和过膝衔接差"),
            ("setup tension drill", "预拉张力练习", "适合身体没接住杠、启动前张力不足"),
            ("high bar squat", "高杠深蹲", "适合改善相扑起拉的下肢参与和竖直驱动"),
            ("bulgarian split squat", "保加利亚分腿蹲", "适合外展打开不足、单侧支撑控制差"),
        ],
    }
    selected = pools.get(exercise) or pools["deadlift"]
    return [
        {"code": code, "title": title, "whenUse": when_use}
        for code, title, when_use in selected
    ]


def _allowed_drill_codes(exercise: str) -> list[str]:
    return [item["code"] for item in _drill_candidate_pool(exercise)]


def _squat_secondary_drills(issues: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for issue in issues:
        name = issue.get("name")
        if not isinstance(name, str):
            continue
        if name in {"bar_path_drift", "forward_weight_shift"}:
            out = _merge_drills(out, ["pin squat", "box squat"])
        elif name in {"mid_ascent_sticking_point", "hip_shoot_in_squat"}:
            out = _merge_drills(out, ["pause squat", "pin squat"])
        elif name in {"torso_position_shift", "upper_back_support_loss", "trunk_brace_loss_in_squat"}:
            out = _merge_drills(out, ["pause squat", "tempo squat"])
        elif name in {"rep_to_rep_velocity_drop", "rep_inconsistency"}:
            out = _merge_drills(out, ["tempo squat", "pin squat"])
        elif name in {"slow_concentric_speed", "grindy_ascent"}:
            out = _merge_drills(out, ["pause squat", "pin squat"])
        if len(out) >= 2:
            return out[:2]
    return out[:2]


def _merge_drills(*drill_lists: list[str]) -> list[str]:
    out: list[str] = []
    for drill_list in drill_lists:
        for drill in drill_list:
            if drill not in out:
                out.append(drill)
            if len(out) >= 2:
                return out[:2]
    return out[:2]


def _issue_taxonomy(exercise: str) -> list[dict[str, str]]:
    common = [
        {"code": "slow_concentric_speed", "title": "起立速度偏慢"},
        {"code": "mid_ascent_sticking_point", "title": "起立中段卡顿"},
            {"code": "bar_path_drift", "title": "杠铃路径漂移"},
            {"code": "torso_position_shift", "title": "起立时躯干角度变化偏大"},
            {"code": "upper_back_support_loss", "title": "上背支撑不足"},
            {"code": "trunk_brace_loss_in_squat", "title": "躯干刚性不足"},
            {"code": "bottom_tension_loss", "title": "底部张力丢失"},
            {"code": "squat_knee_track_collapse", "title": "膝轨迹控制不足"},
            {"code": "squat_descent_rhythm_loss", "title": "离心节奏不连贯"},
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
            {"code": "bench_leg_drive_disconnect", "title": "桥和下肢张力没有真正连通"},
            {"code": "bench_bounce_dependence", "title": "触胸后反弹依赖过强"},
            {"code": "bench_uncontrolled_descent", "title": "卧推离心不受控"},
            {"code": "bench_lockout_quality", "title": "卧推锁定质量差"},
            {"code": "bench_press_path_recovery_loss", "title": "推起路径回不来"},
            {"code": "bench_weak_side_lockout_delay", "title": "弱侧锁定更慢"},
        ]
    if exercise == "deadlift":
        return [
            {"code": "hip_shoot_at_start", "title": "启动抬臀"},
            {"code": "deadlift_tension_preset_failure", "title": "启动前张力预设不足"},
            {"code": "deadlift_knee_hip_desync", "title": "髋膝联动不足"},
            {"code": "bar_drift", "title": "杠铃前飘"},
            {"code": "lat_lock_missing", "title": "腋下锁杠不足"},
            {"code": "deadlift_trunk_brace_loss", "title": "硬拉躯干刚性不足"},
            {"code": "deadlift_knee_pass_transition_loss", "title": "过膝衔接差"},
            {"code": "deadlift_weight_shift_instability", "title": "硬拉重心前后切换过大"},
            {"code": "deadlift_bar_separation_at_start", "title": "离地前就把杠往前拉"},
            {"code": "deadlift_lockout_by_low_back", "title": "锁定时先顶腰，不是先伸髋"},
            {"code": "deadlift_shrug_arm_takeover", "title": "锁定耸肩，手臂代偿"},
            {"code": "deadlift_mid_pull_brace_loss", "title": "中段躯干刚性丢失"},
            {"code": "lower_back_rounding", "title": "下背弯曲"},
            {"code": "lockout_rounding", "title": "锁定姿态不稳"},
            {"code": "overextended_lockout", "title": "锁定过度后仰"},
            {"code": "sumo_hip_height_mismatch", "title": "相扑硬拉臀位过高"},
            {"code": "sumo_wedge_missing", "title": "相扑硬拉预发力不足"},
            {"code": "sumo_wedge_timing_loss", "title": "楔入时序不对"},
            {"code": "sumo_abduction_disconnect", "title": "外展打开不足，导致相扑像宽站传统拉"},
            {"code": "sumo_arm_line_instability", "title": "手臂不垂直，受力线不干净"},
            {"code": "sumo_lockout_back_lean_compensation", "title": "锁定时用后仰替代站直"},
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
        "bottom_tension_loss",
        "squat_knee_track_collapse",
        "squat_descent_rhythm_loss",
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
        "bench_leg_drive_disconnect",
        "bench_bounce_dependence",
        "bench_uncontrolled_descent",
        "bench_lockout_quality",
        "bench_press_path_recovery_loss",
        "bench_weak_side_lockout_delay",
        "hip_shoot_at_start",
        "deadlift_tension_preset_failure",
        "deadlift_knee_hip_desync",
        "bar_drift",
        "lat_lock_missing",
        "deadlift_trunk_brace_loss",
        "deadlift_knee_pass_transition_loss",
        "deadlift_weight_shift_instability",
        "deadlift_bar_separation_at_start",
        "deadlift_lockout_by_low_back",
        "deadlift_shrug_arm_takeover",
        "deadlift_mid_pull_brace_loss",
        "lower_back_rounding",
        "lockout_rounding",
        "overextended_lockout",
        "sumo_hip_height_mismatch",
        "sumo_wedge_missing",
        "sumo_wedge_timing_loss",
        "sumo_abduction_disconnect",
        "sumo_arm_line_instability",
        "sumo_lockout_back_lean_compensation",
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
        (("底部张力", "触底衔接差", "底部接不上", "到底太松"), "bottom_tension_loss"),
        (("膝轨迹控制不足", "膝内扣趋势", "膝往里收", "膝盖没跟脚尖"), "squat_knee_track_collapse"),
        (("离心犹豫", "节奏不连贯", "一路在找位置", "下放犹豫"), "squat_descent_rhythm_loss"),
        (("掉速", "速度损失"), "rep_to_rep_velocity_drop"),
        (("稳定性", "不一致", "波动"), "rep_inconsistency"),
        (("骨盆眨眼", "骨盆翻转", "butt wink"), "pelvic_wink"),
        (("足底重心", "重心不稳"), "unstable_foot_pressure"),
        (("站距", "站姿"), "stance_setup_mismatch"),
        (("卧推离心不受控", "卧推动作里下放不受控", "卧推下放不受控", "bench descent", "bench_uncontrolled_descent"), "bench_uncontrolled_descent"),
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
        (("桥和下肢张力", "腿驱和桥没接", "平台还是松的", "脚下和胸廓像两套系统"), "bench_leg_drive_disconnect"),
        (("触胸反弹", "吃反弹", "一暂停就不会推"), "bench_bounce_dependence"),
        (("离心不受控", "下放不受控", "下放太快", "卧推离心节奏乱"), "bench_uncontrolled_descent"),
        (("锁定质量差", "锁定不稳", "末端锁不稳"), "bench_lockout_quality"),
        (("推起路径回不来", "路径回不来", "离胸后找不到轨道"), "bench_press_path_recovery_loss"),
        (("弱侧锁定更慢", "一边锁得更慢", "弱侧总在等"), "bench_weak_side_lockout_delay"),
        (("抬臀",), "hip_shoot_at_start"),
        (("张力预设", "预设张力", "启动前张力", "接住杠铃"), "deadlift_tension_preset_failure"),
        (("髋膝联动", "只用髋", "膝没接上"), "deadlift_knee_hip_desync"),
        (("前飘", "飘杠"), "bar_drift"),
        (("腋下锁杠", "锁杠不足", "背阔没锁"), "lat_lock_missing"),
        (("硬拉躯干刚性", "硬拉核心松", "离地后散掉", "杠一离地身体就散"), "deadlift_trunk_brace_loss"),
        (("过膝衔接", "过膝发不上去", "膝附近卡住"), "deadlift_knee_pass_transition_loss"),
        (("重心前后切换", "重心来回跑", "硬拉重心不稳"), "deadlift_weight_shift_instability"),
        (("离地前就把杠往前拉", "起拉前杠先离身", "拉杠离身"), "deadlift_bar_separation_at_start"),
        (("锁定时先顶腰", "不是先伸髋", "顶腰锁定"), "deadlift_lockout_by_low_back"),
        (("锁定耸肩", "手臂代偿", "手臂抢活", "耸肩锁定"), "deadlift_shrug_arm_takeover"),
        (("中段躯干刚性丢失", "中段漏气", "到中段开始散", "过膝前躯干塌了"), "deadlift_mid_pull_brace_loss"),
        (("下背弯", "腰部弯"), "lower_back_rounding"),
        (("锁定", "圆肩"), "lockout_rounding"),
        (("后仰锁定", "锁定过头", "过度后仰"), "overextended_lockout"),
        (("相扑", "臀位过高", "臀抬太高"), "sumo_hip_height_mismatch"),
        (("相扑", "楔入", "预发力不足", "楔在一起"), "sumo_wedge_missing"),
        (("楔入时序", "不是真的楔进去", "先蹲下去再找张力"), "sumo_wedge_timing_loss"),
        (("外展打开不足", "相扑像宽站传统拉", "外展没打开"), "sumo_abduction_disconnect"),
        (("手臂不垂直", "受力线不干净", "手臂拉歪了"), "sumo_arm_line_instability"),
        (("锁定时用后仰替代站直", "相扑后段往后甩", "相扑锁定靠后仰"), "sumo_lockout_back_lean_compensation"),
        (("证据不足",), "insufficient_rule_evidence"),
    ]
    for keys, code in mappings:
        if any(k in text for k in keys):
            return code
    return name


@lru_cache(maxsize=1)
def _load_prompt_config() -> dict[str, Any]:
    path = _project_root() / "model" / "prompts" / "fusion_prompt_config.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def _selected_coach_soul_id(style_id: str | None = None) -> str:
    raw = (style_id or os.environ.get("SSC_COACH_SOUL") or "balanced").strip().lower()
    allowed = {"balanced", "direct", "analytical", "competition", "plainspoken"}
    return raw if raw in allowed else "balanced"


@lru_cache(maxsize=1)
def _load_knowledge_base_text() -> str:
    candidates = [
        str(_project_root() / "model" / "力量举技术筛查手册_v2_app版.md"),
        str(_project_root() / "model" / "力量举技术筛查手册.md"),
    ]
    for path in candidates:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
    return ""


@lru_cache(maxsize=5)
def _coach_soul_excerpt(style_id: str | None = None) -> str:
    selected = _selected_coach_soul_id(style_id)
    path = _project_root() / "model" / "prompts" / "coach_souls" / f"{selected}_soul.md"
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()[:2600]
    except Exception:
        return ""


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _knowledge_excerpt(exercise: str) -> str:
    text = _load_knowledge_base_text()
    if not text:
        return ""
    sections = _split_markdown_h2_sections(text)
    wanted_headings = []
    if exercise == "squat":
        wanted_headings.append("## 3. 深蹲 Taxonomy")
    elif exercise == "bench":
        wanted_headings.append("## 4. 卧推 Taxonomy")
    elif exercise in {"deadlift", "sumo_deadlift"}:
        wanted_headings.append("## 5. 传统硬拉 / 相扑硬拉 Taxonomy")
    wanted_headings.append("## 8. 边界判定与去重规则")

    picked: list[str] = []
    for heading in wanted_headings:
        section = sections.get(heading)
        if section:
            picked.append(section.strip())
    return "\n\n".join(picked).strip()


def _split_markdown_h2_sections(text: str) -> dict[str, str]:
    lines = text.splitlines()
    sections: dict[str, str] = {}
    current_heading: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        nonlocal current_heading, buffer
        if current_heading is not None:
            sections[current_heading] = "\n".join(buffer).strip()
        buffer = []

    for line in lines:
        if line.startswith("## "):
            flush()
            current_heading = line.strip()
            buffer = [line]
        elif current_heading is not None:
            buffer.append(line)
    flush()
    return sections


@lru_cache(maxsize=1)
def _taxonomy_knowledge_map() -> dict[str, dict[str, Any]]:
    text = _load_knowledge_base_text()
    if not text:
        return {}
    pattern = re.compile(
        r"^###\s+[^\n]*`(?P<code>[^`]+)`\s*\n(?P<body>.*?)(?=^###\s+|^##\s+|\Z)",
        re.M | re.S,
    )
    out: dict[str, dict[str, Any]] = {}
    for match in pattern.finditer(text):
        code = _clean_issue_name(match.group("code"))
        body = match.group("body")
        if not code or not body:
            continue
        out[code] = {
            "title": _extract_taxonomy_scalar(body, "title"),
            "summary": _extract_taxonomy_scalar(body, "summary"),
            "whatYouSee": _extract_taxonomy_scalar(body, "whatYouSee"),
            "whatToDo": _extract_taxonomy_scalar(body, "whatToDo"),
            "cue": _extract_taxonomy_scalar(body, "cue"),
            "drills": _extract_taxonomy_list(body, "drills"),
        }
    return out


def _taxonomy_knowledge_for_code(code: str) -> dict[str, Any]:
    return dict(_taxonomy_knowledge_map().get(code, {}))


def _extract_taxonomy_scalar(body: str, field: str) -> str | None:
    match = re.search(rf"^- `{re.escape(field)}`:\s*(.+)$", body, re.M)
    if not match:
        return None
    return _clean_text(match.group(1))


def _extract_taxonomy_list(body: str, field: str) -> list[str]:
    match = re.search(
        rf"^- `{re.escape(field)}`:\s*\n(?P<items>(?:\s+- .+\n?)*)",
        body,
        re.M,
    )
    if not match:
        return []
    out: list[str] = []
    for raw in (match.group("items") or "").splitlines():
        line = raw.strip()
        if not line.startswith("- "):
            continue
        value = _clean_text(line[2:])
        if value:
            out.append(value)
    return out


def _extract_knowledge_drills(knowledge: dict[str, Any]) -> list[str]:
    raw = knowledge.get("drills")
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        text = _clean_text(item)
        if text:
            out.append(text)
            if len(out) >= 2:
                break
    return out


def _extract_taxonomy_section(text: str, exercise: str) -> str:
    exercise_heading = {
        "squat": "## 3. 深蹲 Taxonomy",
        "bench": "## 4. 卧推 Taxonomy",
        "deadlift": "## 5. 传统硬拉 / 相扑硬拉 Taxonomy",
        "sumo_deadlift": "## 5. 传统硬拉 / 相扑硬拉 Taxonomy",
    }.get(exercise)
    chunks: list[str] = []
    if exercise_heading and exercise_heading in text:
        chunks.append(exercise_heading)
    for item in _issue_taxonomy(exercise):
        code = _clean_text(item.get("code")) if isinstance(item, dict) else _clean_text(item)
        if not code:
            continue
        section = _extract_taxonomy_entry(text, code)
        if section:
            chunks.append(section)
    return "\n\n".join(chunks)[:5200]


def _extract_taxonomy_entry(text: str, code: str) -> str:
    marker = f"`{code}`"
    marker_index = text.find(marker)
    if marker_index < 0:
        return ""
    start = text.rfind("## ", 0, marker_index)
    if start < 0:
        return ""
    end = text.find("\n## ", marker_index)
    excerpt = text[start:end] if end > start else text[start:]
    return excerpt.strip()


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


def _extract_writing_principles_section(text: str) -> str:
    start_marker = "### 1.5 推荐写法：先说现象，再说推断，最后给动作建议"
    fallback_marker = "---"
    start = text.find(start_marker)
    if start < 0:
        return ""
    end = text.find(fallback_marker, start + len(start_marker))
    excerpt = text[start:end] if end > start else text[start:]
    return excerpt.strip()[:1200]
