from __future__ import annotations

import math
from typing import Any

from server.video.quality import build_video_quality_summary


def extract_features(
    *,
    exercise: str,
    barbell_result: dict[str, Any] | None,
    overlay_result: dict[str, Any] | None,
    vbt_result: dict[str, Any] | None,
    phases: list[dict[str, Any]],
    pose_result: dict[str, Any] | None,
    video_quality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reps = vbt_result.get("reps") if isinstance(vbt_result, dict) else None
    samples = vbt_result.get("samples") if isinstance(vbt_result, dict) else None
    avg_v = None
    best_v = None
    if isinstance(reps, list) and reps:
        vals = [float(r["avgVelocityMps"]) for r in reps if isinstance(r, dict) and isinstance(r.get("avgVelocityMps"), (int, float))]
        if vals:
            avg_v = sum(vals) / len(vals)
            best_v = max(vals)

    overlay_frames = overlay_result.get("frames") if isinstance(overlay_result, dict) else None
    points = [f for f in overlay_frames if isinstance(f, dict) and isinstance(f.get("point"), dict)] if isinstance(overlay_frames, list) else []
    scale_cm_per_px = float(vbt_result["scaleCmPerPx"]) if isinstance(vbt_result, dict) and isinstance(vbt_result.get("scaleCmPerPx"), (int, float)) else None

    bar_path_drift_px = None
    if points:
        xs = [float(p["point"]["x"]) for p in points if isinstance(p["point"].get("x"), (int, float))]
        if xs:
            bar_path_drift_px = max(xs) - min(xs)

    rep_summaries = _build_rep_summaries(
        reps=reps if isinstance(reps, list) else [],
        samples=samples if isinstance(samples, list) else [],
        points=points,
        scale_cm_per_px=scale_cm_per_px,
        pose_result=pose_result,
    )
    velocity_loss_pct = None
    if isinstance(reps, list) and len(reps) >= 2:
        first = reps[0]
        last = reps[-1]
        if (
            isinstance(first, dict)
            and isinstance(last, dict)
            and isinstance(first.get("avgVelocityMps"), (int, float))
            and isinstance(last.get("avgVelocityMps"), (int, float))
            and float(first["avgVelocityMps"]) > 0
        ):
            velocity_loss_pct = max(
                0.0,
                (float(first["avgVelocityMps"]) - float(last["avgVelocityMps"]))
                / float(first["avgVelocityMps"])
                * 100.0,
            )

    rep_velocity_cv_pct = _coefficient_of_variation_pct(
        [
            float(rep["avgVelocityMps"])
            for rep in rep_summaries
            if isinstance(rep.get("avgVelocityMps"), (int, float))
        ]
    )
    avg_ascent_duration_ms = _mean(
        [
            float(rep["durationMs"])
            for rep in rep_summaries
            if isinstance(rep.get("durationMs"), (int, float))
        ]
    )
    grind_rep_count = sum(
        1
        for rep in rep_summaries
        if isinstance(rep.get("avgVelocityMps"), (int, float))
        and isinstance(rep.get("durationMs"), (int, float))
        and float(rep["avgVelocityMps"]) < 0.35
        and float(rep["durationMs"]) >= 1400
    )
    sticking_rep_count = sum(
        1 for rep in rep_summaries if isinstance(rep.get("stickingRegion"), dict)
    )
    pose_summary = _build_pose_summary(pose_result, rep_summaries=rep_summaries)
    structure_summary = _build_structure_summary(pose_result)
    video_quality_summary = build_video_quality_summary(video_quality)

    return {
        "exercise": exercise,
        "repCount": len(reps) if isinstance(reps, list) else 0,
        "avgRepVelocityMps": avg_v,
        "bestRepVelocityMps": best_v,
        "barPathDriftPx": bar_path_drift_px,
        "barPathDriftCm": (bar_path_drift_px * scale_cm_per_px) if (bar_path_drift_px is not None and scale_cm_per_px is not None) else None,
        "phaseCount": len(phases),
        "poseUsable": bool((pose_result or {}).get("quality", {}).get("usable")),
        "motionSource": (vbt_result or {}).get("motionSource"),
        "scaleSource": (vbt_result or {}).get("scaleSource"),
        "scaleCmPerPx": scale_cm_per_px,
        "velocityLossPct": velocity_loss_pct,
        "repVelocityCvPct": rep_velocity_cv_pct,
        "avgAscentDurationMs": avg_ascent_duration_ms,
        "grindRepCount": grind_rep_count,
        "stickingRepCount": sticking_rep_count,
        "repSummaries": rep_summaries,
        "poseFrameCount": pose_summary["poseFrameCount"],
        "posePrimarySide": pose_summary["posePrimarySide"],
        "poseJointQuality": pose_summary["poseJointQuality"],
        "maxTorsoLeanDeg": pose_summary["maxTorsoLeanDeg"],
        "avgTorsoLeanDeltaDeg": pose_summary["avgTorsoLeanDeltaDeg"],
        "minKneeAngleDeg": pose_summary["minKneeAngleDeg"],
        "minHipAngleDeg": pose_summary["minHipAngleDeg"],
        "minElbowAngleDeg": pose_summary["minElbowAngleDeg"],
        "avgWristStackOffsetPx": pose_summary["avgWristStackOffsetPx"],
        "trustedAnkleCoverage": pose_summary["trustedAnkleCoverage"],
        "trustedWristCoverage": pose_summary["trustedWristCoverage"],
        "poseStructures": structure_summary["structures"],
        "torsoLineCoverage": structure_summary["torsoLineCoverage"],
        "footMidpointCoverage": structure_summary["footMidpointCoverage"],
        "forearmLineCoverage": structure_summary["forearmLineCoverage"],
        **video_quality_summary,
    }


def _build_rep_summaries(
    *,
    reps: list[dict[str, Any]],
    samples: list[dict[str, Any]],
    points: list[dict[str, Any]],
    scale_cm_per_px: float | None,
    pose_result: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    pose_frames = _normalize_pose_frames(pose_result)
    structure_frames = _normalize_structure_frames(pose_result)
    primary_side = _pose_primary_side(pose_result)
    out: list[dict[str, Any]] = []
    for rep in reps:
        if not isinstance(rep, dict):
            continue
        tr = rep.get("timeRangeMs")
        if not isinstance(tr, dict):
            continue
        start = tr.get("start")
        end = tr.get("end")
        rep_index = rep.get("repIndex")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or not isinstance(rep_index, int):
            continue
        start_ms = int(start)
        end_ms = int(end)
        if end_ms <= start_ms:
            continue

        rep_samples = [
            s for s in samples
            if isinstance(s, dict)
            and s.get("repIndex") == rep_index
            and isinstance(s.get("timeMs"), (int, float))
            and start_ms <= int(s["timeMs"]) <= end_ms
            and isinstance(s.get("speedMps"), (int, float))
        ]
        speeds = [float(s["speedMps"]) for s in rep_samples]
        peak_speed = max(speeds) if speeds else None
        sticking = _detect_sticking_region(rep_samples, peak_speed)

        rep_points = [
            p for p in points
            if isinstance(p.get("timeMs"), (int, float))
            and start_ms <= int(p["timeMs"]) <= end_ms
            and isinstance((p.get("point") or {}).get("x"), (int, float))
        ]
        drift_px = None
        if rep_points:
            xs = [float(p["point"]["x"]) for p in rep_points]
            drift_px = max(xs) - min(xs)
        pose_metrics = _summarize_pose_for_range(
            pose_frames=pose_frames,
            primary_side=primary_side,
            start_ms=start_ms,
            end_ms=end_ms,
        )
        structure_metrics = _summarize_structures_for_range(
            structure_frames=structure_frames,
            start_ms=start_ms,
            end_ms=end_ms,
        )

        out.append(
            {
                "repIndex": rep_index,
                "timeRangeMs": {"start": start_ms, "end": end_ms},
                "avgVelocityMps": float(rep["avgVelocityMps"]) if isinstance(rep.get("avgVelocityMps"), (int, float)) else None,
                "peakVelocityMps": peak_speed,
                "durationMs": end_ms - start_ms,
                "peakToAvgRatio": (
                    peak_speed / float(rep["avgVelocityMps"])
                    if peak_speed is not None
                    and isinstance(rep.get("avgVelocityMps"), (int, float))
                    and float(rep["avgVelocityMps"]) > 0
                    else None
                ),
                "barPathDriftPx": drift_px,
                "barPathDriftCm": (drift_px * scale_cm_per_px) if (drift_px is not None and scale_cm_per_px is not None) else None,
                "stickingRegion": sticking,
                **pose_metrics,
                **structure_metrics,
            }
        )
    return out


def _build_pose_summary(
    pose_result: dict[str, Any] | None,
    *,
    rep_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    pose_frames = _normalize_pose_frames(pose_result)
    quality = pose_result.get("quality") if isinstance(pose_result, dict) else None
    torso_peaks = [
        float(rep["maxTorsoLeanDeg"])
        for rep in rep_summaries
        if isinstance(rep.get("maxTorsoLeanDeg"), (int, float))
    ]
    torso_deltas = [
        float(rep["torsoLeanDeltaDeg"])
        for rep in rep_summaries
        if isinstance(rep.get("torsoLeanDeltaDeg"), (int, float))
    ]
    knee_angles = [
        float(rep["minKneeAngleDeg"])
        for rep in rep_summaries
        if isinstance(rep.get("minKneeAngleDeg"), (int, float))
    ]
    return {
        "poseFrameCount": len(pose_frames),
        "posePrimarySide": _pose_primary_side(pose_result),
        "poseJointQuality": (
            quality.get("jointQuality")
            if isinstance((pose_result or {}).get("quality"), dict)
            and isinstance((pose_result or {}).get("quality", {}).get("jointQuality"), dict)
            else {}
        ),
        "maxTorsoLeanDeg": max(torso_peaks) if torso_peaks else None,
        "avgTorsoLeanDeltaDeg": _mean(torso_deltas),
        "minKneeAngleDeg": min(knee_angles) if knee_angles else None,
        "minHipAngleDeg": min(
            [
                float(rep["minHipAngleDeg"])
                for rep in rep_summaries
                if isinstance(rep.get("minHipAngleDeg"), (int, float))
            ]
        )
        if any(isinstance(rep.get("minHipAngleDeg"), (int, float)) for rep in rep_summaries)
        else None,
        "minElbowAngleDeg": min(
            [
                float(rep["minElbowAngleDeg"])
                for rep in rep_summaries
                if isinstance(rep.get("minElbowAngleDeg"), (int, float))
            ]
        )
        if any(isinstance(rep.get("minElbowAngleDeg"), (int, float)) for rep in rep_summaries)
        else None,
        "avgWristStackOffsetPx": _mean(
            [
                float(rep["avgWristStackOffsetPx"])
                for rep in rep_summaries
                if isinstance(rep.get("avgWristStackOffsetPx"), (int, float))
            ]
        ),
        "trustedAnkleCoverage": _best_trusted_coverage(pose_result, ("leftAnkle", "rightAnkle")),
        "trustedWristCoverage": _best_trusted_coverage(pose_result, ("leftWrist", "rightWrist")),
    }


def _normalize_pose_frames(pose_result: dict[str, Any] | None) -> list[dict[str, Any]]:
    frames = pose_result.get("keypoints") if isinstance(pose_result, dict) else None
    if not isinstance(frames, list):
        return []
    return [
        frame
        for frame in frames
        if isinstance(frame, dict)
        and isinstance(frame.get("timeMs"), (int, float))
        and isinstance(frame.get("keypoints"), dict)
        and frame.get("keypoints")
    ]


def _normalize_structure_frames(pose_result: dict[str, Any] | None) -> list[dict[str, Any]]:
    structures = pose_result.get("structures") if isinstance(pose_result, dict) else None
    frames = structures.get("frames") if isinstance(structures, dict) else None
    if not isinstance(frames, list):
        return []
    return [
        frame
        for frame in frames
        if isinstance(frame, dict)
        and isinstance(frame.get("timeMs"), (int, float))
    ]


def _build_structure_summary(pose_result: dict[str, Any] | None) -> dict[str, Any]:
    structures = pose_result.get("structures") if isinstance(pose_result, dict) else None
    if not isinstance(structures, dict):
        return {
            "structures": {"frames": [], "quality": {}},
            "torsoLineCoverage": 0.0,
            "footMidpointCoverage": 0.0,
            "forearmLineCoverage": 0.0,
        }
    quality = structures.get("quality")
    if not isinstance(quality, dict):
        quality = {}
    return {
        "structures": structures,
        "torsoLineCoverage": float(quality.get("torsoLineCoverage", 0.0) or 0.0),
        "footMidpointCoverage": float(quality.get("footMidpointCoverage", 0.0) or 0.0),
        "forearmLineCoverage": float(quality.get("forearmLineCoverage", 0.0) or 0.0),
    }


def _summarize_structures_for_range(
    *,
    structure_frames: list[dict[str, Any]],
    start_ms: int,
    end_ms: int,
) -> dict[str, Any]:
    rep_frames = [
        frame for frame in structure_frames if start_ms <= int(frame["timeMs"]) <= end_ms
    ]
    torso_angles: list[float] = []
    forearm_angles: list[float] = []
    foot_points = 0
    for frame in rep_frames:
        torso_line = frame.get("torsoLine")
        forearm_line = frame.get("forearmLine")
        foot_midpoint = frame.get("footMidpoint")
        if isinstance(torso_line, dict) and isinstance(torso_line.get("angleDeg"), (int, float)):
            torso_angles.append(_line_angle_from_vertical(float(torso_line["angleDeg"])))
        if isinstance(forearm_line, dict) and isinstance(forearm_line.get("angleDeg"), (int, float)):
            forearm_angles.append(_line_angle_from_vertical(float(forearm_line["angleDeg"])))
        if isinstance(foot_midpoint, dict):
            foot_points += 1
    return {
        "structureFrameCount": len(rep_frames),
        "structureTorsoLeanDeltaDeg": (max(torso_angles) - min(torso_angles)) if len(torso_angles) >= 2 else None,
        "structureEndTorsoLeanDeg": torso_angles[-1] if torso_angles else None,
        "structureMinForearmFromVerticalDeg": min(forearm_angles) if forearm_angles else None,
        "structureFootMidpointCoverage": (float(foot_points) / float(len(rep_frames))) if rep_frames else None,
    }


def _line_angle_from_vertical(angle_deg: float) -> float:
    normalized = ((angle_deg + 180.0) % 360.0) - 180.0
    return abs(abs(normalized) - 90.0)


def _pose_primary_side(pose_result: dict[str, Any] | None) -> str:
    side = pose_result.get("primarySide") if isinstance(pose_result, dict) else None
    return side if side in {"left", "right"} else "left"


def _summarize_pose_for_range(
    *,
    pose_frames: list[dict[str, Any]],
    primary_side: str,
    start_ms: int,
    end_ms: int,
) -> dict[str, Any]:
    rep_frames = [
        frame for frame in pose_frames if start_ms <= int(frame["timeMs"]) <= end_ms
    ]
    torso_values: list[float] = []
    knee_values: list[float] = []
    hip_values: list[float] = []
    angle_samples: list[dict[str, float]] = []
    elbow_values: list[float] = []
    wrist_stack_offsets: list[float] = []
    for frame in rep_frames:
        points = frame["keypoints"]
        torso = _torso_lean_deg(points, primary_side)
        knee = _joint_angle_deg(points, f"{primary_side}Hip", f"{primary_side}Knee", f"{primary_side}Ankle")
        hip = _joint_angle_deg(points, f"{primary_side}Shoulder", f"{primary_side}Hip", f"{primary_side}Knee")
        elbow = _joint_angle_deg(points, f"{primary_side}Shoulder", f"{primary_side}Elbow", f"{primary_side}Wrist")
        wrist_stack = _wrist_stack_offset_px(points, side=primary_side)
        if torso is not None:
            torso_values.append(torso)
        if knee is not None:
            knee_values.append(knee)
        if hip is not None:
            hip_values.append(hip)
        if (
            isinstance(frame.get("timeMs"), (int, float))
            and knee is not None
            and hip is not None
        ):
            angle_samples.append(
                {
                    "timeMs": float(frame["timeMs"]),
                    "kneeDeg": knee,
                    "hipDeg": hip,
                }
            )
        if elbow is not None:
            elbow_values.append(elbow)
        if wrist_stack is not None:
            wrist_stack_offsets.append(wrist_stack)
    hip_knee_sync = _hip_knee_sync_metrics(angle_samples)
    return {
        "poseFrameCount": len(rep_frames),
        "startTorsoLeanDeg": torso_values[0] if torso_values else None,
        "endTorsoLeanDeg": torso_values[-1] if torso_values else None,
        "maxTorsoLeanDeg": max(torso_values) if torso_values else None,
        "minTorsoLeanDeg": min(torso_values) if torso_values else None,
        "torsoLeanDeltaDeg": (max(torso_values) - min(torso_values)) if len(torso_values) >= 2 else None,
        "minKneeAngleDeg": min(knee_values) if knee_values else None,
        "minHipAngleDeg": min(hip_values) if hip_values else None,
        "hipKneeSyncScore": hip_knee_sync["syncScore"],
        "hipLeadMs": hip_knee_sync["hipLeadMs"],
        "minElbowAngleDeg": min(elbow_values) if elbow_values else None,
        "avgWristStackOffsetPx": _mean(wrist_stack_offsets),
    }


def _torso_lean_deg(points: dict[str, Any], side: str) -> float | None:
    shoulder = _trusted_point(points, f"{side}Shoulder")
    hip = _trusted_point(points, f"{side}Hip")
    if not isinstance(shoulder, dict) or not isinstance(hip, dict):
        return None
    dx = float(shoulder["x"]) - float(hip["x"])
    dy = float(hip["y"]) - float(shoulder["y"])
    if dy <= 1e-6:
        return None
    return abs(math.degrees(math.atan2(abs(dx), abs(dy))))


def _joint_angle_deg(points: dict[str, Any], a_name: str, b_name: str, c_name: str) -> float | None:
    a = _trusted_point(points, a_name)
    b = _trusted_point(points, b_name)
    c = _trusted_point(points, c_name)
    if not isinstance(a, dict) or not isinstance(b, dict) or not isinstance(c, dict):
        return None
    ba_x = float(a["x"]) - float(b["x"])
    ba_y = float(a["y"]) - float(b["y"])
    bc_x = float(c["x"]) - float(b["x"])
    bc_y = float(c["y"]) - float(b["y"])
    ba_norm = math.hypot(ba_x, ba_y)
    bc_norm = math.hypot(bc_x, bc_y)
    if ba_norm <= 1e-6 or bc_norm <= 1e-6:
        return None
    cosine = max(-1.0, min(1.0, (ba_x * bc_x + ba_y * bc_y) / (ba_norm * bc_norm)))
    return math.degrees(math.acos(cosine))


def _hip_knee_sync_metrics(samples: list[dict[str, float]]) -> dict[str, float | None]:
    if len(samples) < 3:
        return {"syncScore": None, "hipLeadMs": None}

    hip_values = [float(sample["hipDeg"]) for sample in samples]
    knee_values = [float(sample["kneeDeg"]) for sample in samples]
    sync_score = _pearson_correlation(hip_values, knee_values)

    hip_lead_ms = _first_progress_crossing_ms(samples=samples, key="hipDeg")
    knee_lead_ms = _first_progress_crossing_ms(samples=samples, key="kneeDeg")
    return {
        "syncScore": sync_score,
        "hipLeadMs": (
            int(knee_lead_ms - hip_lead_ms)
            if hip_lead_ms is not None and knee_lead_ms is not None
            else None
        ),
    }


def _first_progress_crossing_ms(
    *,
    samples: list[dict[str, float]],
    key: str,
    ratio: float = 0.25,
) -> float | None:
    values = [float(sample[key]) for sample in samples]
    start = values[0]
    end = values[-1]
    delta = end - start
    if abs(delta) < 1e-6:
        return None
    target = start + delta * ratio
    if delta > 0:
        for sample in samples:
            if float(sample[key]) >= target:
                return float(sample["timeMs"])
    else:
        for sample in samples:
            if float(sample[key]) <= target:
                return float(sample["timeMs"])
    return None


def _pearson_correlation(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    mean_x = _mean(xs)
    mean_y = _mean(ys)
    if mean_x is None or mean_y is None:
        return None
    centered_x = [x - mean_x for x in xs]
    centered_y = [y - mean_y for y in ys]
    numerator = sum(x * y for x, y in zip(centered_x, centered_y))
    denom_x = math.sqrt(sum(x * x for x in centered_x))
    denom_y = math.sqrt(sum(y * y for y in centered_y))
    if denom_x <= 1e-6 or denom_y <= 1e-6:
        return None
    return max(-1.0, min(1.0, numerator / (denom_x * denom_y)))


def _wrist_stack_offset_px(points: dict[str, Any], *, side: str) -> float | None:
    elbow = _trusted_point(points, f"{side}Elbow")
    wrist = _trusted_point(points, f"{side}Wrist")
    if not isinstance(elbow, dict) or not isinstance(wrist, dict):
        return None
    return abs(float(wrist["x"]) - float(elbow["x"]))


def _trusted_point(points: dict[str, Any], name: str) -> dict[str, Any] | None:
    point = points.get(name)
    if not isinstance(point, dict):
        return None
    if point.get("trusted") is False:
        return None
    return point


def _best_trusted_coverage(
    pose_result: dict[str, Any] | None,
    joints: tuple[str, ...],
) -> float | None:
    quality = pose_result.get("quality") if isinstance(pose_result, dict) else None
    joint_quality = quality.get("jointQuality") if isinstance(quality, dict) else None
    if not isinstance(joint_quality, dict):
        return None
    vals: list[float] = []
    for joint in joints:
        node = joint_quality.get(joint)
        if not isinstance(node, dict):
            continue
        trusted = node.get("trustedCoverage")
        if isinstance(trusted, (int, float)):
            vals.append(float(trusted))
    return max(vals) if vals else None


def _detect_sticking_region(rep_samples: list[dict[str, Any]], peak_speed: float | None) -> dict[str, Any] | None:
    if peak_speed is None or peak_speed <= 0 or len(rep_samples) < 3:
        return None
    threshold = peak_speed * 0.6
    longest: tuple[int, int] | None = None
    cur_start = None
    for sample in rep_samples:
        t = sample.get("timeMs")
        speed = sample.get("speedMps")
        if not isinstance(t, (int, float)) or not isinstance(speed, (int, float)):
            continue
        t_ms = int(t)
        if 0.0 < float(speed) <= threshold:
            if cur_start is None:
                cur_start = t_ms
        else:
            if cur_start is not None:
                seg = (cur_start, t_ms)
                if longest is None or (seg[1] - seg[0]) > (longest[1] - longest[0]):
                    longest = seg
                cur_start = None
    if cur_start is not None:
        end_ms = int(rep_samples[-1]["timeMs"])
        seg = (cur_start, end_ms)
        if longest is None or (seg[1] - seg[0]) > (longest[1] - longest[0]):
            longest = seg
    if longest is None or (longest[1] - longest[0]) < 120:
        return None
    return {
        "startMs": longest[0],
        "endMs": longest[1],
        "durationMs": longest[1] - longest[0],
        "thresholdMps": threshold,
    }


def _mean(xs: list[float]) -> float | None:
    if not xs:
        return None
    return sum(xs) / len(xs)


def _coefficient_of_variation_pct(xs: list[float]) -> float | None:
    if len(xs) < 2:
        return None
    mean = _mean(xs)
    if mean is None or mean <= 0:
        return None
    variance = sum((x - mean) ** 2 for x in xs) / len(xs)
    return (variance ** 0.5) / mean * 100.0
