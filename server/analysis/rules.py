from __future__ import annotations

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

    return {
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

    issues.sort(
        key=lambda issue: (
            {"high": 2, "medium": 1, "low": 0}.get(str(issue.get("severity")), 0),
            float(issue.get("confidence", 0.0)),
        ),
        reverse=True,
    )
    return issues


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
    if exercise != "squat" or not isinstance(name, str):
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
