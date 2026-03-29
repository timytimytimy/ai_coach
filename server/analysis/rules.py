from __future__ import annotations

import re
from typing import Any


def build_analysis_result(
    *,
    exercise: str,
    features: dict[str, Any],
    phases: list[dict[str, Any]],
    video_quality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []

    if exercise == "squat":
        issues.extend(_build_squat_issues(features))
    elif exercise == "bench":
        issues.extend(_build_bench_issues(features, phases=phases))
    elif exercise == "deadlift":
        issues.extend(_build_deadlift_issues(features, phases=phases))
    else:
        avg_v = features.get("avgRepVelocityMps")
        if isinstance(avg_v, (int, float)) and avg_v < 0.35:
            issues.append(
                {
                    "name": "slow_concentric_speed",
                    "evidenceSource": "vbt",
                    "severity": "medium",
                    "confidence": 0.72,
                    "visualEvidence": ["向心阶段整体节奏偏慢"],
                    "kinematicEvidence": [f"平均向心速度 {float(avg_v):.3f} m/s"],
                    "timeRangeMs": _first_phase_range(phases, preferred=("ascent", "press", "floor_break")),
                }
            )

    if not issues:
        issues.append(
            {
                "name": "insufficient_rule_evidence",
                "evidenceSource": "rule",
                "severity": "low",
                "confidence": 0.35,
                "visualEvidence": ["当前规则层暂未发现高置信技术问题"],
                "kinematicEvidence": ["Phase 1 仍是规则版分析骨架"],
                "timeRangeMs": _first_phase_range(phases, preferred=("ascent", "press", "lockout")),
            }
        )

    cue, drills, load_adjustment = _recommendation_for_primary_issue(
        exercise=exercise,
        primary_issue=issues[0] if issues else None,
    )

    result = {
        "liftType": exercise,
        "confidence": max(float(i["confidence"]) for i in issues),
        "issues": [_enrich_issue(issue) for issue in issues[:3]],
        "coachFeedback": _build_coach_feedback(
            exercise=exercise,
            issues=[_enrich_issue(issue) for issue in issues[:3]],
            features=features,
        ),
        "cue": cue,
        "drills": drills,
        "loadAdjustment": load_adjustment,
        "cameraQualityWarning": _camera_quality_warning(video_quality),
    }
    return _humanize_analysis_texts(result)


def build_findings_from_analysis(
    *,
    analysis: dict[str, Any] | None,
    features: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(analysis, dict):
        return [], []

    issues = analysis.get("issues")
    if not isinstance(issues, list):
        return [], []

    rep_count = 0
    if isinstance(features, dict) and isinstance(features.get("repCount"), int):
        rep_count = int(features["repCount"])

    out: list[dict[str, Any]] = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        name = issue.get("name")
        severity = issue.get("severity")
        confidence = issue.get("confidence")
        tr = issue.get("timeRangeMs")
        if (
            not isinstance(name, str)
            or not isinstance(severity, str)
            or not isinstance(confidence, (int, float))
            or not isinstance(tr, dict)
            or not isinstance(tr.get("start"), int)
            or not isinstance(tr.get("end"), int)
        ):
            continue

        metrics: dict[str, float] = {}
        kinematic = issue.get("kinematicEvidence")
        if isinstance(kinematic, list) and kinematic:
            metrics["confidencePct"] = round(float(confidence) * 100.0, 1)

        rep_index = _guess_rep_index(tr, rep_count=rep_count)
        label_display = issue.get("title")
        if not isinstance(label_display, str) or not label_display:
            label_display = _issue_title(name)
        out.append(
            {
                "label": name,
                "labelDisplay": label_display,
                "severity": severity,
                "confidence": float(confidence),
                "timeRangeMs": {
                    "start": int(tr["start"]),
                    "end": int(tr["end"]),
                },
                "repIndex": rep_index,
                "metrics": metrics,
            }
        )
    return out[:3], out


def _build_squat_issues(features: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    reps = features.get("repSummaries")
    if not isinstance(reps, list):
        reps = []

    slowest = _pick_rep(reps, key="avgVelocityMps", prefer="min")
    if slowest is not None and isinstance(slowest.get("avgVelocityMps"), (int, float)) and float(slowest["avgVelocityMps"]) < 0.38:
        issues.append(
            {
                "name": "slow_concentric_speed",
                "evidenceSource": "vbt",
                "severity": "medium",
                "confidence": 0.76,
                "visualEvidence": ["起立阶段整体速度偏慢，向心节奏不够干脆"],
                "kinematicEvidence": [f"最慢一组平均向心速度 {float(slowest['avgVelocityMps']):.3f} m/s"],
                "timeRangeMs": dict(slowest["timeRangeMs"]),
            }
        )

    if (
        slowest is not None
        and isinstance(slowest.get("avgVelocityMps"), (int, float))
        and isinstance(slowest.get("durationMs"), (int, float))
        and float(slowest["avgVelocityMps"]) < 0.34
        and float(slowest["durationMs"]) >= 1400
    ):
        issues.append(
            {
                "name": "grindy_ascent",
                "evidenceSource": "vbt",
                "severity": "medium",
                "confidence": 0.74,
                "visualEvidence": ["起立时间拉长，整次 rep 明显发力吃力"],
                "kinematicEvidence": [
                    f"该 rep 持续 {int(float(slowest['durationMs']))} ms，平均速度 {float(slowest['avgVelocityMps']):.3f} m/s"
                ],
                "timeRangeMs": dict(slowest["timeRangeMs"]),
            }
        )

    worst_drift = _pick_rep(reps, key="barPathDriftCm", prefer="max")
    if worst_drift is not None and isinstance(worst_drift.get("barPathDriftCm"), (int, float)) and float(worst_drift["barPathDriftCm"]) > 6.0:
        issues.append(
            {
                "name": "bar_path_drift",
                "evidenceSource": "barbell",
                "severity": "medium",
                "confidence": 0.72,
                "visualEvidence": ["起立过程中杠铃没有稳定贴近同一垂直路径"],
                "kinematicEvidence": [f"单次 rep 横向漂移约 {float(worst_drift['barPathDriftCm']):.1f} cm"],
                "timeRangeMs": dict(worst_drift["timeRangeMs"]),
            }
        )

    worst_sticking = None
    for rep in reps:
        if not isinstance(rep, dict):
            continue
        sr = rep.get("stickingRegion")
        if not isinstance(sr, dict):
            continue
        if worst_sticking is None or int(sr.get("durationMs", 0)) > int(worst_sticking["stickingRegion"].get("durationMs", 0)):
            worst_sticking = rep
    if worst_sticking is not None:
        sr = worst_sticking["stickingRegion"]
        if int(sr.get("durationMs", 0)) >= 220:
            issues.append(
                {
                    "name": "mid_ascent_sticking_point",
                    "evidenceSource": "vbt",
                    "severity": "medium",
                    "confidence": 0.7,
                    "visualEvidence": ["起立中段出现明显减速区间"],
                    "kinematicEvidence": [f"低速区持续约 {int(sr['durationMs'])} ms"],
                    "timeRangeMs": {"start": int(sr["startMs"]), "end": int(sr["endMs"])},
                }
            )

    pose_shift_rep = _pick_rep(reps, key="torsoLeanDeltaDeg", prefer="max")
    if (
        pose_shift_rep is not None
        and isinstance(pose_shift_rep.get("torsoLeanDeltaDeg"), (int, float))
        and float(pose_shift_rep["torsoLeanDeltaDeg"]) >= 12.0
    ):
        issues.append(
            {
                "name": "torso_position_shift",
                "evidenceSource": "pose",
                "severity": "low" if float(pose_shift_rep["torsoLeanDeltaDeg"]) < 18.0 else "medium",
                "confidence": 0.66 if float(pose_shift_rep["torsoLeanDeltaDeg"]) < 18.0 else 0.73,
                "visualEvidence": ["起立过程中躯干角度变化偏大，胸背姿态不够稳定"],
                "kinematicEvidence": [f"单次 rep 躯干前倾变化约 {float(pose_shift_rep['torsoLeanDeltaDeg']):.1f}°"],
                "timeRangeMs": dict(pose_shift_rep["timeRangeMs"]),
            }
        )

    ankle_coverage = features.get("trustedAnkleCoverage")
    unstable_base_rep = _pick_rep(reps, key="barPathDriftCm", prefer="max")
    if (
        isinstance(ankle_coverage, (int, float))
        and float(ankle_coverage) >= 0.6
        and unstable_base_rep is not None
        and isinstance(unstable_base_rep.get("barPathDriftCm"), (int, float))
        and float(unstable_base_rep["barPathDriftCm"]) >= 5.5
    ):
        issues.append(
            {
                "name": "unstable_foot_pressure",
                "evidenceSource": "pose",
                "severity": "low",
                "confidence": 0.58,
                "visualEvidence": ["下肢支撑稳定性一般，起立时足底压力控制可能不够稳"],
                "kinematicEvidence": [
                    f"可信足踝覆盖率 {float(ankle_coverage) * 100.0:.0f}%，同时单次 rep 横向漂移约 {float(unstable_base_rep['barPathDriftCm']):.1f} cm"
                ],
                "timeRangeMs": dict(unstable_base_rep["timeRangeMs"]),
            }
        )

    forward_shift_rep = _pick_rep(reps, key="barPathDriftCm", prefer="max")
    if (
        forward_shift_rep is not None
        and isinstance(forward_shift_rep.get("barPathDriftCm"), (int, float))
        and isinstance(forward_shift_rep.get("torsoLeanDeltaDeg"), (int, float))
        and isinstance(ankle_coverage, (int, float))
        and float(ankle_coverage) >= 0.55
        and float(forward_shift_rep["barPathDriftCm"]) >= 7.5
        and float(forward_shift_rep["torsoLeanDeltaDeg"]) >= 10.0
    ):
        issues.append(
            {
                "name": "forward_weight_shift",
                "evidenceSource": "pose",
                "severity": "medium",
                "confidence": 0.68,
                "visualEvidence": ["起立时人和杠一起向前跑，重心控制不够稳"],
                "kinematicEvidence": [
                    f"单次 rep 横向漂移约 {float(forward_shift_rep['barPathDriftCm']):.1f} cm，躯干角度变化约 {float(forward_shift_rep['torsoLeanDeltaDeg']):.1f}°"
                ],
                "timeRangeMs": dict(forward_shift_rep["timeRangeMs"]),
            }
        )

    vl = features.get("velocityLossPct")
    if isinstance(vl, (int, float)) and float(vl) >= 15.0:
        issues.append(
            {
                "name": "rep_to_rep_velocity_drop",
                "evidenceSource": "vbt",
                "severity": "medium" if float(vl) >= 20.0 else "low",
                "confidence": 0.7 if float(vl) >= 20.0 else 0.64,
                "visualEvidence": ["后续 reps 的起立节奏明显慢于前面"],
                "kinematicEvidence": [f"首末 rep 速度损失约 {float(vl):.1f}%"],
                "timeRangeMs": _range_of_last_rep(reps),
            }
        )

    cv = features.get("repVelocityCvPct")
    if isinstance(cv, (int, float)) and float(cv) >= 12.0:
        issues.append(
            {
                "name": "rep_inconsistency",
                "evidenceSource": "vbt",
                "severity": "low",
                "confidence": 0.62,
                "visualEvidence": ["各次起立节奏波动较大，重复间稳定性一般"],
                "kinematicEvidence": [f"rep 平均速度变异系数约 {float(cv):.1f}%"],
                "timeRangeMs": _range_of_last_rep(reps),
            }
        )

    return _sort_issues(issues)


def _build_bench_issues(
    features: dict[str, Any],
    *,
    phases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    reps = features.get("repSummaries")
    if not isinstance(reps, list):
        reps = []
    wrist_offset = features.get("avgWristStackOffsetPx")
    wrist_coverage = features.get("trustedWristCoverage")
    if (
        isinstance(wrist_offset, (int, float))
        and float(wrist_offset) >= 14.0
        and (
            not isinstance(wrist_coverage, (int, float))
            or float(wrist_coverage) >= 0.45
        )
    ):
        issues.append(
            {
                "name": "bench_wrist_stack_break",
                "evidenceSource": "pose",
                "severity": "medium" if float(wrist_offset) >= 20.0 else "low",
                "confidence": 0.73 if float(wrist_offset) >= 20.0 else 0.66,
                "visualEvidence": ["离心和推起时前臂承重线没有稳定叠在杠下，手腕位置略散"],
                "kinematicEvidence": [
                    (
                        f"可信手腕覆盖率 {float(wrist_coverage) * 100.0:.0f}%，平均手腕堆叠偏移约 {float(wrist_offset):.1f} px"
                        if isinstance(wrist_coverage, (int, float))
                        else f"平均手腕堆叠偏移约 {float(wrist_offset):.1f} px"
                    )
                ],
                "timeRangeMs": _first_phase_range(phases, preferred=("press", "touch", "lockout")),
            }
        )

    elbow_rep = _pick_rep(reps, key="minElbowAngleDeg", prefer="max")
    if (
        elbow_rep is not None
        and isinstance(elbow_rep.get("minElbowAngleDeg"), (int, float))
        and isinstance(elbow_rep.get("avgWristStackOffsetPx"), (int, float))
        and float(elbow_rep["minElbowAngleDeg"]) >= 145.0
        and float(elbow_rep["avgWristStackOffsetPx"]) >= 18.0
    ):
        issues.append(
            {
                "name": "bench_elbow_flare_mismatch",
                "evidenceSource": "pose",
                "severity": "low",
                "confidence": 0.63,
                "visualEvidence": ["离心到底和推起早段前臂承重线偏散，肘部展开时机不够稳定"],
                "kinematicEvidence": [
                    f"单次 rep 最小肘角约 {float(elbow_rep['minElbowAngleDeg']):.1f}°，平均手腕堆叠偏移约 {float(elbow_rep['avgWristStackOffsetPx']):.1f} px"
                ],
                "timeRangeMs": dict(elbow_rep["timeRangeMs"]),
            }
        )

    avg_v = features.get("avgRepVelocityMps")
    if isinstance(avg_v, (int, float)) and float(avg_v) < 0.28:
        issues.append(
            {
                "name": "slow_concentric_speed",
                "evidenceSource": "vbt",
                "severity": "medium",
                "confidence": 0.72,
                "visualEvidence": ["上推阶段整体节奏偏慢"],
                "kinematicEvidence": [f"平均上推速度 {float(avg_v):.3f} m/s"],
                "timeRangeMs": _first_phase_range(phases, preferred=("press", "lockout")),
            }
        )
    return _sort_issues(issues)


def _build_deadlift_issues(
    features: dict[str, Any],
    *,
    phases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    reps = features.get("repSummaries")
    if not isinstance(reps, list):
        reps = []
    torso_delta = features.get("avgTorsoLeanDeltaDeg")
    min_hip = features.get("minHipAngleDeg")
    max_torso = features.get("maxTorsoLeanDeg")
    if (
        isinstance(torso_delta, (int, float))
        and float(torso_delta) >= 9.0
        and (
            (isinstance(max_torso, (int, float)) and float(max_torso) >= 12.0)
            or (isinstance(min_hip, (int, float)) and float(min_hip) <= 95.0)
        )
    ):
        issues.append(
            {
                "name": "deadlift_tension_preset_failure",
                "evidenceSource": "pose",
                "severity": "medium" if float(torso_delta) >= 13.0 else "low",
                "confidence": 0.74 if float(torso_delta) >= 13.0 else 0.66,
                "visualEvidence": ["离地前到离地初段躯干姿态变化偏大，启动张力不够完整"],
                "kinematicEvidence": [
                    (
                        f"平均躯干角度变化约 {float(torso_delta):.1f}°，最小髋角约 {float(min_hip):.1f}°"
                        if isinstance(min_hip, (int, float))
                        else f"平均躯干角度变化约 {float(torso_delta):.1f}°，离地前后躯干姿态变化偏大"
                    )
                ],
                "timeRangeMs": _first_phase_range(phases, preferred=("floor_break", "pull", "lockout")),
            }
        )

    lockout_rep = _pick_rep(reps, key="endTorsoLeanDeg", prefer="max")
    if (
        lockout_rep is not None
        and isinstance(lockout_rep.get("endTorsoLeanDeg"), (int, float))
        and float(lockout_rep["endTorsoLeanDeg"]) >= 18.0
    ):
        issues.append(
            {
                "name": "lockout_rounding",
                "evidenceSource": "pose",
                "severity": "low" if float(lockout_rep["endTorsoLeanDeg"]) < 24.0 else "medium",
                "confidence": 0.64 if float(lockout_rep["endTorsoLeanDeg"]) < 24.0 else 0.7,
                "visualEvidence": ["锁定前后躯干没有完全站稳，完成姿态略散"],
                "kinematicEvidence": [
                    f"单次 rep 末端躯干前倾约 {float(lockout_rep['endTorsoLeanDeg']):.1f}°"
                ],
                "timeRangeMs": dict(lockout_rep["timeRangeMs"]),
            }
        )

    avg_v = features.get("avgRepVelocityMps")
    if isinstance(avg_v, (int, float)) and float(avg_v) < 0.3:
        issues.append(
            {
                "name": "slow_concentric_speed",
                "evidenceSource": "vbt",
                "severity": "medium",
                "confidence": 0.72,
                "visualEvidence": ["拉起阶段整体节奏偏慢"],
                "kinematicEvidence": [f"平均拉起速度 {float(avg_v):.3f} m/s"],
                "timeRangeMs": _first_phase_range(phases, preferred=("floor_break", "pull", "lockout")),
            }
        )
    return _sort_issues(issues)


def _pick_rep(reps: list[dict[str, Any]], *, key: str, prefer: str) -> dict[str, Any] | None:
    valid = [r for r in reps if isinstance(r, dict) and isinstance(r.get(key), (int, float))]
    if not valid:
        return None
    if prefer == "min":
        return min(valid, key=lambda r: float(r[key]))
    return max(valid, key=lambda r: float(r[key]))


def _camera_quality_warning(video_quality: dict[str, Any] | None) -> str | None:
    if not isinstance(video_quality, dict):
        return None
    quality = video_quality.get("quality")
    if isinstance(quality, dict):
        warning = quality.get("primaryWarning")
        if isinstance(warning, str) and warning:
            return warning
    warnings = video_quality.get("warnings")
    if isinstance(warnings, list):
        for item in warnings:
            if isinstance(item, dict) and isinstance(item.get("message"), str) and item["message"]:
                return item["message"]
    return None


def _range_of_last_rep(reps: list[dict[str, Any]]) -> dict[str, int]:
    for rep in reversed(reps):
        if isinstance(rep, dict) and isinstance(rep.get("timeRangeMs"), dict):
            tr = rep["timeRangeMs"]
            start = tr.get("start")
            end = tr.get("end")
            if isinstance(start, int) and isinstance(end, int):
                return {"start": start, "end": end}
    return {"start": 0, "end": 0}


def _guess_rep_index(time_range_ms: dict[str, int], *, rep_count: int) -> int | None:
    if rep_count <= 0:
        return None
    end_ms = int(time_range_ms["end"])
    if end_ms <= 0:
        return None
    guess = max(1, min(rep_count, 1 + end_ms // 3000))
    return guess


def _first_phase_range(phases: list[dict[str, Any]], *, preferred: tuple[str, ...]) -> dict[str, int]:
    for name in preferred:
        for p in phases:
            if isinstance(p, dict) and p.get("name") == name:
                start = p.get("startMs")
                end = p.get("endMs")
                if isinstance(start, int) and isinstance(end, int):
                    return {"start": start, "end": end}
    return {"start": 0, "end": 0}


def _enrich_issue(issue: dict[str, Any]) -> dict[str, Any]:
    name = issue.get("name")
    if not isinstance(name, str):
        return issue
    return {
        **issue,
        "title": _issue_title(name),
        "evidenceSource": issue.get("evidenceSource") if isinstance(issue.get("evidenceSource"), str) else "rule",
    }


def _issue_title(name: str) -> str:
    return {
        "slow_concentric_speed": "起立速度偏慢",
        "grindy_ascent": "起立过程过于吃力",
        "bar_path_drift": "杠铃路径漂移",
        "mid_ascent_sticking_point": "起立中段卡顿",
        "torso_position_shift": "起立时躯干角度变化偏大",
        "unstable_foot_pressure": "足底重心不稳",
        "forward_weight_shift": "深蹲重心前跑",
        "bench_wrist_stack_break": "手腕承重线不稳",
        "bench_elbow_flare_mismatch": "肘部展开时机不匹配",
        "deadlift_tension_preset_failure": "启动前张力预设不足",
        "lockout_rounding": "锁定姿态不稳",
        "rep_to_rep_velocity_drop": "后续重复明显掉速",
        "rep_inconsistency": "重复间稳定性不足",
        "insufficient_rule_evidence": "当前证据不足",
    }.get(name, name.replace("_", " "))


def _recommendation_for_primary_issue(
    *,
    exercise: str,
    primary_issue: dict[str, Any] | None,
) -> tuple[str, list[str], str]:
    default = (
        {
            "squat": "起立时先把背顶住杠，再带髋一起上升",
            "bench": "下放保持前臂稳定堆叠，触胸后直接向上推",
            "deadlift": "起杠前先拉紧身体和杠，再把地板推开",
        }.get(exercise, "优先保持路径稳定和节奏一致"),
        {
            "squat": ["pause squat"],
            "bench": ["paused bench"],
            "deadlift": ["tempo deadlift"],
        }.get(exercise, ["tempo variation"]),
        "keep_load",
    )
    if not isinstance(primary_issue, dict):
        return default

    name = primary_issue.get("name")
    if not isinstance(name, str):
        return default

    if exercise == "bench":
        if name == "bench_wrist_stack_break":
            return (
                "让手腕、前臂和杠铃承重线叠稳，别让手腕先塌掉",
                ["paused bench", "spoto press"],
                "hold_load",
            )
        if name == "bench_elbow_flare_mismatch":
            return (
                "离心和推起都先让前臂承重线立住，不要过早外展把力线放散",
                ["paused bench", "spoto press"],
                "hold_load",
            )
        if name == "slow_concentric_speed":
            return (
                "触胸后把全身张力一口气接住，再沿原路径稳定上推",
                ["paused bench"],
                "hold_load_and_repeat_if_form_breaks",
            )
        return default

    if exercise == "deadlift":
        if name == "deadlift_tension_preset_failure":
            return (
                "拉之前先把自己和杠连成一个整体，再让杠离地",
                ["paused deadlift", "setup tension drill"],
                "hold_load_and_repeat_if_form_breaks",
            )
        if name == "lockout_rounding":
            return (
                "锁定时先把髋伸直到位站稳，不要靠圆肩或散掉的躯干去凑完成",
                ["paused deadlift", "banded deadlift"],
                "hold_load_and_repeat_if_form_breaks",
            )
        if name == "slow_concentric_speed":
            return (
                "起杠前先把腿和躯干一起拉紧，再把地板推开",
                ["tempo deadlift"],
                "hold_load_and_repeat_if_form_breaks",
            )
        return default

    if exercise != "squat":
        return default

    if name == "bar_path_drift":
        return (
            "全程把杠稳在中足上方，起立时不要让杠向前跑",
            ["tempo squat", "pin squat"],
            "hold_load_and_repeat_if_form_breaks",
        )
    if name == "mid_ascent_sticking_point":
        return (
            "出底后继续向上推地，别在中段泄力",
            ["pause squat", "tempo squat"],
            "hold_load_and_repeat_if_form_breaks",
        )
    if name == "torso_position_shift":
        return (
            "起立前半程先把胸口和背部顶住杠，再让髋膝一起展开",
            ["pause squat", "tempo squat"],
            "hold_load_and_repeat_if_form_breaks",
        )
    if name == "unstable_foot_pressure":
        return (
            "全程把重心稳在全脚掌，别让足底压力前后乱飘",
            ["tempo squat"],
            "hold_load_and_repeat_if_form_breaks",
        )
    if name == "forward_weight_shift":
        return (
            "让人和杠一起稳在中足上方，别把压力一路送到前脚掌",
            ["tempo squat", "box squat"],
            "hold_load_and_repeat_if_form_breaks",
        )
    if name in {"slow_concentric_speed", "grindy_ascent"}:
        return (
            "起立时保持持续加速，不要只在底部发力一下就泄掉",
            ["pause squat", "squat doubles"],
            "next_set_minus_5_percent",
        )
    if name in {"rep_to_rep_velocity_drop", "rep_inconsistency"}:
        return (
            "每次重复都用同样的准备和节奏，不要越做越急或越做越散",
            ["tempo squat"],
            "reduce_set_volume_if_quality_drops",
        )
    return default


def _build_coach_feedback(
    *,
    exercise: str,
    issues: list[dict[str, Any]],
    features: dict[str, Any],
) -> dict[str, Any]:
    primary = issues[0] if issues else None
    secondary = issues[1:] if len(issues) > 1 else []
    primary_name = str(primary.get("name")) if isinstance(primary, dict) else ""
    rep_count = int(features.get("repCount") or 0) if isinstance(features.get("repCount"), (int, float)) else 0
    velocity_loss = (
        float(features.get("velocityLossPct"))
        if isinstance(features.get("velocityLossPct"), (int, float))
        else None
    )

    if exercise == "squat":
        if primary_name == "mid_ascent_sticking_point":
            focus = "这组最需要先改的是出底到起立中段这段发力连续性。"
            why = "你不是单纯起不来，而是出底后到中段会明显减速，后半组这个问题更明显。"
            next_set = "下一组把注意力放在出底后继续顶住、继续加速，不要到底部发力一下就松掉。"
        elif primary_name == "rep_to_rep_velocity_drop":
            focus = "这组最明显的问题是后半组重复质量掉得比较快。"
            why = "前几次还能维持节奏，后面几次速度下降明显，说明疲劳一上来动作质量就开始下滑。"
            next_set = "下一组先把每次重复的准备和起立节奏做一致，不要越做越急，也不要越做越散。"
        elif primary_name in {"slow_concentric_speed", "grindy_ascent"}:
            focus = "这组起立整体偏慢，尤其后半组更吃力。"
            why = "问题不只是速度慢，而是起立发力没有持续顶上去，所以越到后面越容易拖长。"
            next_set = "下一组把重点放在持续加速上，让力量从底部一直延续到站直。"
        elif primary_name == "torso_position_shift":
            focus = "这组起立时躯干姿态有点散，胸背稳定性不够。"
            why = "出底后躯干角度变化偏大，说明你在用姿态变化帮自己把杠顶起来。"
            next_set = "下一组先把胸口和背撑住，再让髋膝一起向上展开。"
        elif primary_name == "bar_path_drift":
            focus = "这组杠铃路径不够稳，起立时有往前跑的趋势。"
            why = "杠没有一直稳在同一条发力线上，路径一散，后面的发力效率就会下降。"
            next_set = "下一组盯住中足上方这条线，起立时别让杠向前漂。"
        else:
            focus = "这组先优先处理最明显的技术问题。"
            why = "当前证据提示主要问题集中在起立质量和重复稳定性。"
            next_set = "下一组先把最关键的一条提示做到位，再看动作有没有马上变顺。"
    else:
        focus = "这组先优先处理当前最明显的技术问题。"
        why = "当前证据更支持先从主问题入手，而不是同时改很多点。"
        next_set = "下一组先只盯一条提示，动作会更容易稳定下来。"

    if exercise == "bench" and primary_name == "bench_wrist_stack_break":
        focus = "这组卧推最先要收的是前臂和手腕的承重线。"
        why = "手腕没有稳定叠在杠下，会让离心和上推都变得松散，力量传导也会打折。"
        next_set = "下一组先把手腕叠稳、前臂立住，再去追求更快的上推速度。"
    elif exercise == "bench" and primary_name == "bench_elbow_flare_mismatch":
        focus = "这组卧推要先把前臂承重线和肘部展开节奏收稳。"
        why = "如果离心到底和推起早段就把肘部放散，杠路和发力都会变得不稳定。"
        next_set = "下一组先让前臂保持更稳定的承重线，再决定什么时候把肘部展开。"
    elif exercise == "deadlift" and primary_name == "deadlift_tension_preset_failure":
        focus = "这组硬拉最先要补的是离地前的整体张力。"
        why = "启动前到离地初段躯干姿态变化偏大，说明你还没把人和杠真正连成一个整体。"
        next_set = "下一组起杠前先把脚下、背阔和躯干一起拉紧，再让杠离地。"
    elif exercise == "deadlift" and primary_name == "lockout_rounding":
        focus = "这组硬拉锁定前后的躯干站稳质量还不够。"
        why = "杠已经接近完成时，躯干还没有完全站稳，会让最后的锁定看起来有点散。"
        next_set = "下一组锁定时先把髋伸直到位站稳，不要用圆肩或后仰去凑完成。"

    keep_watching: list[str] = []
    for issue in secondary[:3]:
        if not isinstance(issue, dict):
            continue
        title = issue.get("title")
        if isinstance(title, str) and title:
            keep_watching.append(f"{title}还需要继续观察")

    if exercise == "squat" and velocity_loss is not None and velocity_loss >= 15.0:
        text = "后半组掉速趋势还需要继续观察"
        if text not in keep_watching:
            keep_watching.append(text)

    if rep_count > 0 and len(keep_watching) > 3:
        keep_watching = keep_watching[:3]

    return {
        "focus": focus,
        "why": why,
        "nextSet": next_set,
        "keepWatching": keep_watching,
    }


def _sort_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues.sort(
        key=lambda issue: (
            {"high": 2, "medium": 1, "low": 0}.get(str(issue.get("severity")), 0),
            float(issue.get("confidence", 0.0)),
        ),
        reverse=True,
    )
    return issues


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
