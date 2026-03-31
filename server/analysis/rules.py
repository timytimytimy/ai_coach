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
        issues=issues[:6],
    )

    result = {
        "liftType": exercise,
        "confidence": max(float(i["confidence"]) for i in issues),
        "issues": [_enrich_issue(issue) for issue in issues[:6]],
        "coachFeedback": _build_coach_feedback(
            exercise=exercise,
            issues=[_enrich_issue(issue) for issue in issues[:6]],
            features=features,
        ),
        "cue": cue,
        "drills": drills,
        "loadAdjustment": load_adjustment,
        "cameraQualityWarning": _camera_quality_warning(video_quality),
    }
    coach = result.get("coachFeedback")
    if isinstance(coach, dict):
        result["coachFeedback"] = {
            **coach,
            "nextSet": _expand_next_set_with_drills(
                coach.get("nextSet"),
                drills=drills,
            ),
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

    pose_shift_rep = _pick_rep(reps, key="structureTorsoLeanDeltaDeg", prefer="max") or _pick_rep(reps, key="torsoLeanDeltaDeg", prefer="max")
    if (
        pose_shift_rep is not None
        and isinstance(
            pose_shift_rep.get("structureTorsoLeanDeltaDeg", pose_shift_rep.get("torsoLeanDeltaDeg")),
            (int, float),
        )
        and float(pose_shift_rep.get("structureTorsoLeanDeltaDeg", pose_shift_rep.get("torsoLeanDeltaDeg"))) >= 12.0
    ):
        torso_delta = float(pose_shift_rep.get("structureTorsoLeanDeltaDeg", pose_shift_rep.get("torsoLeanDeltaDeg")))
        issues.append(
            {
                "name": "torso_position_shift",
                "evidenceSource": "pose",
                "severity": "low" if torso_delta < 18.0 else "medium",
                "confidence": 0.66 if torso_delta < 18.0 else 0.73,
                "visualEvidence": ["起立过程中躯干角度变化偏大，胸背姿态不够稳定"],
                "kinematicEvidence": [f"单次 rep 躯干前倾变化约 {torso_delta:.1f}°"],
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
        and isinstance(
            forward_shift_rep.get("structureTorsoLeanDeltaDeg", forward_shift_rep.get("torsoLeanDeltaDeg")),
            (int, float),
        )
        and isinstance(ankle_coverage, (int, float))
        and float(ankle_coverage) >= 0.55
        and float(forward_shift_rep["barPathDriftCm"]) >= 7.5
        and float(forward_shift_rep.get("structureTorsoLeanDeltaDeg", forward_shift_rep.get("torsoLeanDeltaDeg"))) >= 10.0
    ):
        torso_delta = float(forward_shift_rep.get("structureTorsoLeanDeltaDeg", forward_shift_rep.get("torsoLeanDeltaDeg")))
        issues.append(
            {
                "name": "forward_weight_shift",
                "evidenceSource": "pose",
                "severity": "medium",
                "confidence": 0.68,
                "visualEvidence": ["起立时人和杠一起向前跑，重心控制不够稳"],
                "kinematicEvidence": [
                    f"单次 rep 横向漂移约 {float(forward_shift_rep['barPathDriftCm']):.1f} cm，躯干角度变化约 {torso_delta:.1f}°"
                ],
                "timeRangeMs": dict(forward_shift_rep["timeRangeMs"]),
            }
        )

    desync_rep = _pick_rep(reps, key="hipLeadMs", prefer="max")
    if (
        desync_rep is not None
        and isinstance(desync_rep.get("hipLeadMs"), (int, float))
        and isinstance(desync_rep.get("hipKneeSyncScore"), (int, float))
        and (
            float(desync_rep["hipLeadMs"]) >= 180.0
            or float(desync_rep["hipKneeSyncScore"]) <= 0.55
        )
    ):
        hip_lead_ms = float(desync_rep["hipLeadMs"])
        sync_score = float(desync_rep["hipKneeSyncScore"])
        severity = "medium" if hip_lead_ms >= 260.0 or sync_score <= 0.4 else "low"
        confidence = 0.74 if severity == "medium" else 0.66
        issues.append(
            {
                "name": "hip_shoot_in_squat",
                "evidenceSource": "pose",
                "severity": severity,
                "confidence": confidence,
                "visualEvidence": ["起立前半程髋部先走，膝部没有同步接上，动作联动偏散"],
                "kinematicEvidence": [
                    f"髋部进入主要展开比膝部早约 {int(hip_lead_ms)} ms，髋膝同步分数约 {sync_score:.2f}"
                ],
                "timeRangeMs": dict(desync_rep["timeRangeMs"]),
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

    elbow_rep = _pick_rep(reps, key="structureMinForearmFromVerticalDeg", prefer="max") or _pick_rep(reps, key="minElbowAngleDeg", prefer="max")
    if (
        elbow_rep is not None
        and isinstance(
            elbow_rep.get("structureMinForearmFromVerticalDeg", elbow_rep.get("minElbowAngleDeg")),
            (int, float),
        )
        and isinstance(elbow_rep.get("avgWristStackOffsetPx"), (int, float))
        and float(elbow_rep.get("structureMinForearmFromVerticalDeg", elbow_rep.get("minElbowAngleDeg"))) >= 8.0
        and float(elbow_rep["avgWristStackOffsetPx"]) >= 18.0
    ):
        forearm_offset = float(elbow_rep.get("structureMinForearmFromVerticalDeg", elbow_rep.get("minElbowAngleDeg")))
        issues.append(
            {
                "name": "bench_elbow_flare_mismatch",
                "evidenceSource": "pose",
                "severity": "low",
                "confidence": 0.63,
                "visualEvidence": ["离心到底和推起早段前臂承重线偏散，肘部展开时机不够稳定"],
                "kinematicEvidence": [
                    f"单次 rep 前臂偏离垂直约 {forearm_offset:.1f}°，平均手腕堆叠偏移约 {float(elbow_rep['avgWristStackOffsetPx']):.1f} px"
                ],
                "timeRangeMs": dict(elbow_rep["timeRangeMs"]),
            }
        )

    upper_back_rep = _pick_rep(reps, key="structureTorsoLeanDeltaDeg", prefer="max") or _pick_rep(reps, key="torsoLeanDeltaDeg", prefer="max")
    torso_coverage = features.get("torsoLineCoverage")
    if (
        upper_back_rep is not None
        and isinstance(
            upper_back_rep.get("structureTorsoLeanDeltaDeg", upper_back_rep.get("torsoLeanDeltaDeg")),
            (int, float),
        )
        and (
            not isinstance(torso_coverage, (int, float))
            or float(torso_coverage) >= 0.4
        )
        and float(
            upper_back_rep.get("structureTorsoLeanDeltaDeg", upper_back_rep.get("torsoLeanDeltaDeg"))
        ) >= 6.0
    ):
        torso_delta = float(
            upper_back_rep.get("structureTorsoLeanDeltaDeg", upper_back_rep.get("torsoLeanDeltaDeg"))
        )
        issues.append(
            {
                "name": "bench_upper_back_instability",
                "evidenceSource": "pose",
                "severity": "medium" if torso_delta >= 9.0 else "low",
                "confidence": 0.72 if torso_delta >= 9.0 else 0.64,
                "visualEvidence": ["下放到上推过程中胸背承托不够稳，杠下支撑略有松动"],
                "kinematicEvidence": [f"单次 rep 躯干结构角变化约 {torso_delta:.1f}°"],
                "timeRangeMs": dict(upper_back_rep["timeRangeMs"]),
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
    structure_torso_coverage = features.get("torsoLineCoverage")
    structure_torso_rep = _pick_rep(reps, key="structureTorsoLeanDeltaDeg", prefer="max")
    torso_delta_value = (
        float(structure_torso_rep["structureTorsoLeanDeltaDeg"])
        if structure_torso_rep is not None and isinstance(structure_torso_rep.get("structureTorsoLeanDeltaDeg"), (int, float))
        else float(torso_delta) if isinstance(torso_delta, (int, float)) else None
    )
    if (
        isinstance(torso_delta_value, (int, float))
        and float(torso_delta_value) >= 9.0
        and (
            (isinstance(max_torso, (int, float)) and float(max_torso) >= 12.0)
            or (isinstance(min_hip, (int, float)) and float(min_hip) <= 95.0)
            or (isinstance(structure_torso_coverage, (int, float)) and float(structure_torso_coverage) >= 0.5)
        )
    ):
        issues.append(
            {
                "name": "deadlift_tension_preset_failure",
                "evidenceSource": "pose",
                "severity": "medium" if float(torso_delta_value) >= 13.0 else "low",
                "confidence": 0.74 if float(torso_delta_value) >= 13.0 else 0.66,
                "visualEvidence": ["离地前到离地初段躯干姿态变化偏大，启动张力不够完整"],
                "kinematicEvidence": [
                    (
                        f"平均躯干角度变化约 {float(torso_delta_value):.1f}°，最小髋角约 {float(min_hip):.1f}°"
                        if isinstance(min_hip, (int, float))
                        else f"平均躯干角度变化约 {float(torso_delta_value):.1f}°，离地前后躯干姿态变化偏大"
                    )
                ],
                "timeRangeMs": _first_phase_range(phases, preferred=("floor_break", "pull", "lockout")),
            }
        )

    desync_rep = _pick_rep(reps, key="hipLeadMs", prefer="max")
    if (
        desync_rep is not None
        and isinstance(desync_rep.get("hipLeadMs"), (int, float))
        and isinstance(desync_rep.get("hipKneeSyncScore"), (int, float))
        and (
            float(desync_rep["hipLeadMs"]) >= 160.0
            or float(desync_rep["hipKneeSyncScore"]) <= 0.58
        )
    ):
        hip_lead_ms = float(desync_rep["hipLeadMs"])
        sync_score = float(desync_rep["hipKneeSyncScore"])
        issues.append(
            {
                "name": "deadlift_knee_hip_desync",
                "evidenceSource": "pose",
                "severity": "medium" if hip_lead_ms >= 240.0 or sync_score <= 0.42 else "low",
                "confidence": 0.74 if hip_lead_ms >= 240.0 or sync_score <= 0.42 else 0.66,
                "visualEvidence": ["离地初段髋和膝没有一起接上，起拉联动略散，容易变成只用髋去拉"],
                "kinematicEvidence": [f"髋部进入主要展开比膝部早约 {int(hip_lead_ms)} ms，髋膝同步分数约 {sync_score:.2f}"],
                "timeRangeMs": dict(desync_rep["timeRangeMs"]),
            }
        )

    lockout_rep = _pick_rep(reps, key="structureEndTorsoLeanDeg", prefer="max") or _pick_rep(reps, key="endTorsoLeanDeg", prefer="max")
    if (
        lockout_rep is not None
        and isinstance(
            lockout_rep.get("structureEndTorsoLeanDeg", lockout_rep.get("endTorsoLeanDeg")),
            (int, float),
        )
        and float(lockout_rep.get("structureEndTorsoLeanDeg", lockout_rep.get("endTorsoLeanDeg"))) >= 18.0
    ):
        end_torso = float(lockout_rep.get("structureEndTorsoLeanDeg", lockout_rep.get("endTorsoLeanDeg")))
        issues.append(
            {
                "name": "lockout_rounding",
                "evidenceSource": "pose",
                "severity": "low" if end_torso < 24.0 else "medium",
                "confidence": 0.64 if end_torso < 24.0 else 0.7,
                "visualEvidence": ["锁定前后躯干没有完全站稳，完成姿态略散"],
                "kinematicEvidence": [
                    f"单次 rep 末端躯干前倾约 {end_torso:.1f}°"
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
        "hip_shoot_in_squat": "深蹲起立先抬臀",
        "torso_position_shift": "起立时躯干角度变化偏大",
        "unstable_foot_pressure": "足底重心不稳",
        "forward_weight_shift": "深蹲重心前跑",
        "bench_upper_back_instability": "上背稳定不足",
        "bench_wrist_stack_break": "手腕承重线不稳",
        "bench_elbow_flare_mismatch": "肘部展开时机不匹配",
        "deadlift_tension_preset_failure": "启动前张力预设不足",
        "deadlift_knee_hip_desync": "髋膝联动不足",
        "lockout_rounding": "锁定姿态不稳",
        "rep_to_rep_velocity_drop": "后续重复明显掉速",
        "rep_inconsistency": "重复间稳定性不足",
        "insufficient_rule_evidence": "当前证据不足",
    }.get(name, name.replace("_", " "))


def _recommendation_for_primary_issue(
    *,
    exercise: str,
    issues: list[dict[str, Any]] | None,
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
    primary_issue = issues[0] if isinstance(issues, list) and issues and isinstance(issues[0], dict) else None
    secondary_issues = [issue for issue in (issues or [])[1:] if isinstance(issue, dict)]

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
        if name == "bench_upper_back_instability":
            return (
                "先把上背和胸廓承托稳住，再让杠沿同一条支撑线下放和推起。",
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
        if name == "deadlift_knee_hip_desync":
            return (
                "离地时让膝和髋一起接上，不要只先把髋往上顶。",
                ["paused deadlift", "tempo deadlift"],
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
            "触底后继续向上推地，别在中段泄力",
            ["pause squat", "tempo squat"],
            "hold_load_and_repeat_if_form_breaks",
        )
    if name == "torso_position_shift":
        return (
            "起立前半程先把胸口和背部顶住杠，再让髋膝一起展开",
            ["pause squat", "tempo squat"],
            "hold_load_and_repeat_if_form_breaks",
        )
    if name == "hip_shoot_in_squat":
        return (
            "触底后先稳住胸背，让髋和膝一起展开，不要先把屁股抬起来。",
            ["pause squat", "pin squat"],
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
        drills = _merge_drills(
            ["pause squat", "pin squat"],
            _squat_secondary_drills(secondary_issues),
        )
        return (
            "起立时保持持续加速，不要只在底部发力一下就泄掉",
            drills,
            "next_set_minus_5_percent",
        )
    if name in {"rep_to_rep_velocity_drop", "rep_inconsistency"}:
        drills = _merge_drills(
            ["tempo squat", "pin squat"],
            _squat_secondary_drills(secondary_issues),
        )
        return (
            "每次重复都用同样的准备和节奏，不要越做越急或越做越散",
            drills,
            "reduce_set_volume_if_quality_drops",
        )
    return default


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
            focus = "这组最需要先改的是触底到起立中段这段发力连续性。"
            why = "你不是单纯起不来，而是触底后到中段会明显减速，后半组这个问题更明显。"
            next_set = "下一组先把重点放在触底后继续把地板往下踩、把杠一路顶过中段，不要到底部发力一下就松掉。做的时候抓“胸背一直顶住杠、速度别在中段断掉”这个感觉。如果第 4 下以后又开始明显卡顿，这组就少做 1 到 2 次，或者先用暂停深蹲把这一下练顺。"
        elif primary_name == "rep_to_rep_velocity_drop":
            focus = "这组最明显的问题是后半组重复质量掉得比较快。"
            why = "前几次还能维持节奏，后面几次速度下降明显，说明疲劳一上来动作质量就开始下滑。"
            next_set = "下一组先把每次重复都做成同一个模板，别前面很稳、后面开始乱追速度。做的时候盯住“每一下下去前都重新锁住、起来时节奏一样”这个感觉。如果做到后半组已经明显磨速，就别硬做满，提前收组或少做 1 到 2 次。"
        elif primary_name in {"slow_concentric_speed", "grindy_ascent"}:
            focus = "这组起立整体偏慢，尤其后半组更吃力。"
            why = "问题不只是速度慢，而是起立发力没有持续顶上去，所以越到后面越容易拖长。"
            next_set = "下一组先把起立做成持续加速的一整段，不要到底部蹬一下、后面就靠磨。做的时候抓“杠一直往上走、不是突然停一下再补一段”这个感觉。如果第 4 下以后速度已经明显掉，就小幅降重或直接减少 1 到 2 次重复。"
        elif primary_name == "torso_position_shift":
            focus = "这组起立时躯干姿态有点散，胸背稳定性不够。"
            why = "触底后躯干角度变化偏大，说明你在用姿态变化帮自己把杠顶起来。"
            next_set = "下一组先把胸口和背撑住杠，再让髋膝一起向上展开，不要先让胸口往下掉。做的时候抓“上背把杠稳住、人和杠一起站起来”这个感觉。如果一加重量就又开始散，先用暂停深蹲或节奏深蹲把前半程稳住。"
        elif primary_name == "hip_shoot_in_squat":
            focus = "这组最先要改的是出底后的髋膝联动。"
            why = "起立前半程髋先走、膝没及时接上，动作会更像先抬臀再顶杠。"
            next_set = "下一组触底后先把胸背稳住，让髋和膝一起展开，不要急着先抬臀。做的时候抓“胸口别后跟、膝和髋一起把身体送起来”这个感觉。如果还是总想先抬臀，就先降一点重量，或者用箱式/暂停深蹲把起立顺序练对。"
        elif primary_name == "bar_path_drift":
            focus = "这组杠铃路径不够稳，起立时有往前跑的趋势。"
            why = "杠没有一直稳在同一条发力线上，路径一散，后面的发力效率就会下降。"
            next_set = "下一组先把人和杠一起稳在中足上方，再去追速度。做的时候抓“脚下压力稳在中足、杠贴着同一条线上下走”这个感觉。如果一到后半组就开始前跑，先降一点重量，或用 pin squat 把路径守住。"
        else:
            focus = "这组先优先处理最明显的技术问题。"
            why = "当前证据提示主要问题集中在起立质量和重复稳定性。"
            next_set = "下一组别同时改很多点，先只抓住最关键的一条提示。做的时候重点留意这一下做完以后动作有没有立刻顺一点；如果没有，就先减一点难度，把这条提示练会再往上加。"
    else:
        focus = "这组先优先处理当前最明显的技术问题。"
        why = "当前证据更支持先从主问题入手，而不是同时改很多点。"
        next_set = "下一组先只盯一条最关键的提示，不要一口气改太多。做的时候抓一个最明显的动作感觉；如果当组还是做不到，就先降一点难度，把正确模板做出来。"

    if exercise == "bench" and primary_name == "bench_wrist_stack_break":
        focus = "这组卧推最先要收的是前臂和手腕的承重线。"
        why = "手腕没有稳定叠在杠下，会让离心和上推都变得松散，力量传导也会打折。"
        next_set = "下一组先把手腕叠稳、前臂立住，再去追求更快的上推速度。做的时候抓“杠正好压在前臂正上方、手腕不先塌”这个感觉。如果一加重量就又散，先用暂停卧推把承重线练稳。"
    elif exercise == "bench" and primary_name == "bench_elbow_flare_mismatch":
        focus = "这组卧推要先把前臂承重线和肘部展开节奏收稳。"
        why = "如果离心到底和推起早段就把肘部放散，杠路和发力都会变得不稳定。"
        next_set = "下一组先让前臂保持更稳定的承重线，再决定什么时候把肘部展开。做的时候抓“下放和上推前臂都能顶住杠”这个感觉；如果一到离胸就乱，先用 paused/spoto press 把早段路线练顺。"
    elif exercise == "bench" and primary_name == "bench_upper_back_instability":
        focus = "这组卧推最先要补的是上背和胸廓的承托稳定。"
        why = "下放到上推过程中胸背支撑不够稳，杠下支撑线容易松掉，整次发力也会跟着散。"
        next_set = "下一组先把上背楔稳、胸廓立住，再让杠沿同一路径下放和推起。做的时候抓“整个平台一直顶住凳子、不是触胸后整个人散掉”这个感觉。如果一到离胸就掉平台，先用暂停卧推把支撑线练稳。"
    elif exercise == "deadlift" and primary_name == "deadlift_tension_preset_failure":
        focus = "这组硬拉最先要补的是离地前的整体张力。"
        why = "启动前到离地初段躯干姿态变化偏大，说明你还没把人和杠真正连成一个整体。"
        next_set = "下一组起杠前先把脚下、背阔和躯干一起拉紧，再让杠离地。做的时候抓“杠一离地人还是一整块，不是先把自己拉散”这个感觉。如果还总是抢起拉，就先降一点重量，先把 setup tension 做扎实。"
    elif exercise == "deadlift" and primary_name == "deadlift_knee_hip_desync":
        focus = "这组硬拉离地初段的髋膝联动还不够整齐。"
        why = "起拉时髋先走、膝没有同步接上，动作会更像先抬臀再把杠拖起来。"
        next_set = "下一组离地时先把腿和髋一起接上，不要只让髋先顶起来。做的时候抓“把地板推开，不是先用屁股把自己抬走”这个感觉。如果还是总先抬臀，就先用 paused deadlift 把离地顺序练对。"
    elif exercise == "deadlift" and primary_name == "lockout_rounding":
        focus = "这组硬拉锁定前后的躯干站稳质量还不够。"
        why = "杠已经接近完成时，躯干还没有完全站稳，会让最后的锁定看起来有点散。"
        next_set = "下一组锁定时先把髋伸直到位站稳，不要用圆肩或后仰去凑完成。做的时候抓“站直到位就结束，不再额外找后仰”这个感觉；如果锁定总是散，先用暂停硬拉把最后一段站稳。"

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


def _expand_next_set_with_drills(value: Any, *, drills: list[str] | None) -> str:
    text = value.strip() if isinstance(value, str) else ""
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


def _drill_labels_zh(drills: list[str] | None) -> list[str]:
    if not isinstance(drills, list):
        return []
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
        if not isinstance(drill, str):
            continue
        label = mapping.get(drill, drill)
        if label not in out:
            out.append(label)
        if len(out) >= 2:
            break
    return out
