from __future__ import annotations

from typing import Any


_DIMENSION_WEIGHTS = {
    "speedRhythm": 0.30,
    "barPathControl": 0.30,
    "repConsistency": 0.20,
    "technicalExecution": 0.20,
}


def build_score_result(
    *,
    exercise: str,
    features: dict[str, Any] | None,
    analysis: dict[str, Any] | None,
    video_quality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    feature_map = features if isinstance(features, dict) else {}
    reps = feature_map.get("repSummaries")
    rep_summaries = [rep for rep in reps if isinstance(rep, dict)] if isinstance(reps, list) else []

    if not rep_summaries:
        return {
            "overall": None,
            "grade": None,
            "shareLabel": None,
            "confidence": _score_confidence(
                analysis_confidence=(analysis or {}).get("confidence") if isinstance(analysis, dict) else None,
                video_quality=video_quality,
            ),
            "dimensions": {},
            "bestRepIndex": None,
            "weakestRepIndex": None,
            "consistencyScore": None,
            "reps": [],
        }

    rep_velocities = [
        float(rep["avgVelocityMps"])
        for rep in rep_summaries
        if isinstance(rep.get("avgVelocityMps"), (int, float))
    ]
    rep_durations = [
        float(rep["durationMs"])
        for rep in rep_summaries
        if isinstance(rep.get("durationMs"), (int, float))
    ]

    best_velocity = max(rep_velocities) if rep_velocities else None
    median_velocity = _median(rep_velocities)
    median_duration = _median(rep_durations)
    issues = analysis.get("issues") if isinstance(analysis, dict) and isinstance(analysis.get("issues"), list) else []

    rep_results: list[dict[str, Any]] = []
    rep_weights: list[float] = []
    overall_dimension_acc = {key: 0.0 for key in _DIMENSION_WEIGHTS}

    for index, rep in enumerate(rep_summaries, start=1):
        rep_weight = 1.0 + ((index - 1) / max(1, len(rep_summaries) - 1)) * 0.25
        rep_weights.append(rep_weight)
        rep_result = _score_rep(
            rep=rep,
            exercise=exercise,
            best_velocity=best_velocity,
            median_velocity=median_velocity,
            median_duration=median_duration,
            issues=issues,
            video_quality=video_quality,
        )
        rep_results.append(rep_result)
        for dim, value in rep_result["dimensions"].items():
            if isinstance(value, (int, float)):
                overall_dimension_acc[dim] += float(value) * rep_weight

    total_weight = sum(rep_weights) or 1.0
    overall_dimensions = {
        dim: round(total / total_weight)
        for dim, total in overall_dimension_acc.items()
    }
    overall_score = _weighted_dimension_score(overall_dimensions)
    consistency_score = overall_dimensions.get("repConsistency")

    best_rep = max(rep_results, key=lambda rep: int(rep["score"]))
    weakest_rep = min(rep_results, key=lambda rep: int(rep["score"]))

    return {
        "overall": overall_score,
        "grade": _grade_for_score(overall_score),
        "shareLabel": f"本组技术评分 {overall_score}" if overall_score is not None else None,
        "confidence": _score_confidence(
            analysis_confidence=(analysis or {}).get("confidence") if isinstance(analysis, dict) else None,
            video_quality=video_quality,
        ),
        "dimensions": overall_dimensions,
        "bestRepIndex": best_rep.get("repIndex"),
        "weakestRepIndex": weakest_rep.get("repIndex"),
        "consistencyScore": consistency_score,
        "reps": rep_results,
    }


def _score_rep(
    *,
    rep: dict[str, Any],
    exercise: str,
    best_velocity: float | None,
    median_velocity: float | None,
    median_duration: float | None,
    issues: list[dict[str, Any]],
    video_quality: dict[str, Any] | None,
) -> dict[str, Any]:
    rep_index = int(rep.get("repIndex") or 0)
    rep_range = rep.get("timeRangeMs") if isinstance(rep.get("timeRangeMs"), dict) else {"start": 0, "end": 0}

    speed_score, speed_reasons, speed_highlights = _score_speed_rhythm(
        rep=rep,
        best_velocity=best_velocity,
    )
    path_score, path_reasons, path_highlights = _score_bar_path(rep=rep)
    consistency_score, consistency_reasons, consistency_highlights = _score_consistency(
        rep=rep,
        median_velocity=median_velocity,
        median_duration=median_duration,
    )
    technical_score, technical_reasons, technical_highlights = _score_technical_execution(
        rep=rep,
        issues=issues,
        video_quality=video_quality,
    )

    dimensions = {
        "speedRhythm": speed_score,
        "barPathControl": path_score,
        "repConsistency": consistency_score,
        "technicalExecution": technical_score,
    }
    score = _weighted_dimension_score(dimensions)

    reasons = sorted(
        speed_reasons + path_reasons + consistency_reasons + technical_reasons,
        key=lambda item: int(item["impact"]),
    )[:3]
    highlights = (
        speed_highlights
        + path_highlights
        + consistency_highlights
        + technical_highlights
    )[:3]
    deductions = [item["label"] for item in reasons]

    if not highlights:
        highlights = [_default_highlight(exercise=exercise, score=score)]

    return {
        "repIndex": rep_index,
        "score": score,
        "grade": _grade_for_score(score),
        "dimensions": dimensions,
        "timeRangeMs": rep_range,
        "highlights": highlights,
        "deductions": deductions,
        "reasons": reasons,
    }


def _score_speed_rhythm(
    *,
    rep: dict[str, Any],
    best_velocity: float | None,
) -> tuple[int, list[dict[str, Any]], list[str]]:
    score = 100.0
    reasons: list[dict[str, Any]] = []
    highlights: list[str] = []

    avg_velocity = _as_float(rep.get("avgVelocityMps"))
    duration_ms = _as_float(rep.get("durationMs"))
    sticking = rep.get("stickingRegion") if isinstance(rep.get("stickingRegion"), dict) else None

    if avg_velocity is not None and best_velocity and best_velocity > 0:
        drop_pct = max(0.0, (best_velocity - avg_velocity) / best_velocity * 100.0)
        if drop_pct > 4.0:
            penalty = min(24.0, (drop_pct - 4.0) * 1.2)
            score -= penalty
            reasons.append(_reason("speedRhythm", -round(penalty), f"相对本组最佳速度下降 {drop_pct:.1f}%"))
        elif drop_pct <= 1.5:
            highlights.append("起立节奏稳定")

    if duration_ms is not None and duration_ms > 1350:
        penalty = min(18.0, (duration_ms - 1350.0) / 30.0)
        score -= penalty
        reasons.append(_reason("speedRhythm", -round(penalty), f"起立时长偏长 ({int(duration_ms)} ms)"))

    if sticking and isinstance(sticking.get("durationMs"), (int, float)):
        sticking_ms = float(sticking["durationMs"])
        if sticking_ms >= 220:
            penalty = min(18.0, sticking_ms / 28.0)
            score -= penalty
            reasons.append(_reason("speedRhythm", -round(penalty), f"中段存在卡顿 ({int(sticking_ms)} ms)"))

    return _clamp_int(score), reasons, highlights


def _score_bar_path(*, rep: dict[str, Any]) -> tuple[int, list[dict[str, Any]], list[str]]:
    score = 100.0
    reasons: list[dict[str, Any]] = []
    highlights: list[str] = []

    drift_cm = _as_float(rep.get("barPathDriftCm"))
    if drift_cm is not None:
        if drift_cm > 3.0:
            penalty = min(30.0, (drift_cm - 3.0) * 4.0)
            score -= penalty
            reasons.append(_reason("barPathControl", -round(penalty), f"杠铃路径漂移 {drift_cm:.1f} cm"))
        elif drift_cm <= 2.0:
            highlights.append("杠铃路径较稳")

    return _clamp_int(score), reasons, highlights


def _score_consistency(
    *,
    rep: dict[str, Any],
    median_velocity: float | None,
    median_duration: float | None,
) -> tuple[int, list[dict[str, Any]], list[str]]:
    score = 100.0
    reasons: list[dict[str, Any]] = []
    highlights: list[str] = []

    avg_velocity = _as_float(rep.get("avgVelocityMps"))
    duration_ms = _as_float(rep.get("durationMs"))

    if avg_velocity is not None and median_velocity and median_velocity > 0:
        delta_pct = abs(avg_velocity - median_velocity) / median_velocity * 100.0
        if delta_pct > 5.0:
            penalty = min(18.0, (delta_pct - 5.0) * 1.3)
            score -= penalty
            reasons.append(_reason("repConsistency", -round(penalty), f"与组内中位速度偏差 {delta_pct:.1f}%"))
        else:
            highlights.append("重复间节奏一致")

    if duration_ms is not None and median_duration and median_duration > 0:
        duration_delta_pct = abs(duration_ms - median_duration) / median_duration * 100.0
        if duration_delta_pct > 10.0:
            penalty = min(16.0, (duration_delta_pct - 10.0) * 0.8)
            score -= penalty
            reasons.append(_reason("repConsistency", -round(penalty), f"与组内中位时长偏差 {duration_delta_pct:.1f}%"))

    return _clamp_int(score), reasons, highlights


def _score_technical_execution(
    *,
    rep: dict[str, Any],
    issues: list[dict[str, Any]],
    video_quality: dict[str, Any] | None,
) -> tuple[int, list[dict[str, Any]], list[str]]:
    score = 100.0
    reasons: list[dict[str, Any]] = []
    highlights: list[str] = []

    rep_range = rep.get("timeRangeMs") if isinstance(rep.get("timeRangeMs"), dict) else None
    start = int(rep_range.get("start", 0)) if rep_range else 0
    end = int(rep_range.get("end", 0)) if rep_range else 0

    for issue in issues:
        if not isinstance(issue, dict):
            continue
        evidence_source = issue.get("evidenceSource")
        issue_name = issue.get("name") if isinstance(issue.get("name"), str) else ""
        if evidence_source == "pose" and issue_name != "hip_shoot_in_squat":
            continue
        issue_range = issue.get("timeRangeMs")
        if not isinstance(issue_range, dict):
            continue
        issue_start = int(issue_range.get("start", 0))
        issue_end = int(issue_range.get("end", 0))
        if issue_end < start or issue_start > end:
            continue
        severity = str(issue.get("severity") or "low")
        penalty = {"high": 14.0, "medium": 9.0, "low": 5.0}.get(severity, 5.0)
        if issue_name == "hip_shoot_in_squat":
            penalty += 2.0
        title = issue.get("title") if isinstance(issue.get("title"), str) else "存在技术扣分项"
        score -= penalty
        reasons.append(_reason("technicalExecution", -round(penalty), title))

    confidence = _video_quality_confidence(video_quality)
    usable = _video_quality_usable(video_quality)
    if confidence is not None and confidence < 0.65:
        penalty = round((0.65 - confidence) * 20)
        if penalty > 0:
            score -= penalty
            reasons.append(_reason("technicalExecution", -penalty, "视频质量一般，技术评分置信度受限"))
    if usable:
        highlights.append("视频质量支持本次判断")

    score = _clamp(score, 0.0, 100.0)
    if not usable:
        score = min(score, 78.0)

    return _clamp_int(score), reasons, highlights[:1]


def _weighted_dimension_score(dimensions: dict[str, int]) -> int:
    total = 0.0
    for key, weight in _DIMENSION_WEIGHTS.items():
        value = dimensions.get(key)
        if isinstance(value, (int, float)):
            total += float(value) * weight
    return _clamp_int(total)


def _score_confidence(
    *,
    analysis_confidence: Any,
    video_quality: dict[str, Any] | None,
) -> float | None:
    vals: list[float] = []
    if isinstance(analysis_confidence, (int, float)):
        vals.append(float(analysis_confidence))
    quality_conf = _video_quality_confidence(video_quality)
    if quality_conf is not None:
        vals.append(quality_conf)
    if not vals:
        return None
    return round(sum(vals) / len(vals), 4)


def _video_quality_confidence(video_quality: dict[str, Any] | None) -> float | None:
    quality = video_quality.get("quality") if isinstance(video_quality, dict) else None
    confidence = quality.get("confidence") if isinstance(quality, dict) else None
    return float(confidence) if isinstance(confidence, (int, float)) else None


def _video_quality_usable(video_quality: dict[str, Any] | None) -> bool:
    quality = video_quality.get("quality") if isinstance(video_quality, dict) else None
    usable = quality.get("usable") if isinstance(quality, dict) else True
    return bool(usable)


def _grade_for_score(score: int | None) -> str | None:
    if score is None:
        return None
    if score >= 97:
        return "A+"
    if score >= 93:
        return "A"
    if score >= 90:
        return "A-"
    if score >= 87:
        return "B+"
    if score >= 83:
        return "B"
    if score >= 80:
        return "B-"
    if score >= 77:
        return "C+"
    if score >= 73:
        return "C"
    if score >= 70:
        return "C-"
    return "D"


def _default_highlight(*, exercise: str, score: int) -> str:
    if exercise == "squat":
        if score >= 85:
            return "本次重复整体完成度较好"
        if score >= 75:
            return "本次重复整体可控"
        return "本次重复仍有明显可优化空间"
    return "本次重复已完成基础技术判断"


def _reason(dimension: str, impact: int, label: str) -> dict[str, Any]:
    return {
        "dimension": dimension,
        "impact": impact,
        "label": label,
    }


def _as_float(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _clamp_int(value: float | int) -> int:
    return int(round(_clamp(float(value), 0.0, 100.0)))
