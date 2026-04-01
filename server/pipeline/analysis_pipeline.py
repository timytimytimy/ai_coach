from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
from typing import Any

from server.analysis import (
    build_analysis_result,
    build_findings_from_analysis,
    build_rule_evidence_snapshot,
    build_score_result,
    extract_features,
    segment_phases,
)
from server.barbell import BarbellTrajectoryDetector, default_model_path, find_local_video_path
from server.barbell.overlay import build_overlay_from_barbell
from server.barbell.vbt import compute_vbt_from_barbell
from server.utils.config import env_float, env_int
from server.utils.db import now_iso
from server.fusion import build_fused_analysis, build_fused_analysis_cache_key
from server.pose import infer_pose
from server.video import (
    analyze_video_quality,
    build_lift_classification_cache_key,
    classify_lift_from_video,
)

_LOG = logging.getLogger("ssc")

_barbell_lock = threading.Lock()
_barbell_detector: BarbellTrajectoryDetector | None = None

_BARBELL_CACHE_VERSION = "barbell-cache-v1"
_POSE_CACHE_VERSION = "pose-cache-v1"


def get_barbell_detector() -> BarbellTrajectoryDetector:
    global _barbell_detector
    with _barbell_lock:
        if _barbell_detector is not None:
            return _barbell_detector
        model_path = os.environ.get("SSC_YOLO_MODEL_PATH") or default_model_path()
        device = os.environ.get("SSC_YOLO_DEVICE") or ""
        if not device:
            from server.utils.accel import default_yolo_device
            device = default_yolo_device()
        imgsz = env_int("SSC_YOLO_IMGSZ", 640)
        conf = env_float("SSC_YOLO_CONF", 0.25)
        iou = env_float("SSC_YOLO_IOU", 0.5)
        _barbell_detector = BarbellTrajectoryDetector(
            model_path=model_path,
            device=device,
            imgsz=imgsz,
            conf=conf,
            iou=iou,
        )
        return _barbell_detector


def stable_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def barbell_cache_key(
    *,
    detector: BarbellTrajectoryDetector,
    sample_fps: float,
    batch_size: int,
    max_frames: int | None,
) -> str:
    payload = {
        "version": _BARBELL_CACHE_VERSION,
        "modelPath": detector.model_path,
        "device": detector.device,
        "imgsz": detector.imgsz,
        "conf": detector.conf,
        "iou": detector.iou,
        "sampleFps": sample_fps,
        "batchSize": batch_size,
        "maxFrames": max_frames,
    }
    return sha256_text(stable_json(payload))


def pose_cache_key(*, exercise: str, barbell_cache_key: str) -> str:
    payload = {
        "version": _POSE_CACHE_VERSION,
        "exercise": exercise,
        "barbellCacheKey": barbell_cache_key,
        "sampleFps": env_float("SSC_POSE_SAMPLE_FPS", 12.0),
        "minVisibility": env_float("SSC_POSE_MIN_VISIBILITY", 0.45),
        "minDetectionConf": env_float("SSC_POSE_MIN_DETECTION_CONF", 0.5),
        "minTrackingConf": env_float("SSC_POSE_MIN_TRACKING_CONF", 0.5),
        "modelComplexity": env_int("SSC_POSE_MODEL_COMPLEXITY", 1),
        "roiMaxGapMs": env_int("SSC_POSE_ROI_MAX_GAP_MS", 450),
    }
    return sha256_text(stable_json(payload))


def load_json_cache(
    conn: sqlite3.Connection,
    *,
    table: str,
    where: dict[str, Any],
    value_column: str,
) -> dict[str, Any] | None:
    where_clause = " AND ".join(f"{column}=?" for column in where)
    row = conn.execute(
        f"SELECT {value_column} FROM {table} WHERE {where_clause}",
        tuple(where.values()),
    ).fetchone()
    if row is None:
        return None
    return json.loads(row[value_column])


def store_json_cache(
    conn: sqlite3.Connection,
    *,
    table: str,
    payload: dict[str, Any],
    value_column: str,
    value: dict[str, Any],
) -> None:
    columns = list(payload.keys()) + [value_column, "created_at"]
    values = list(payload.values()) + [stable_json(value), now_iso()]
    placeholders = ",".join("?" for _ in columns)
    conn.execute(
        f"INSERT OR REPLACE INTO {table}({','.join(columns)}) VALUES ({placeholders})",
        values,
    )


def store_llm_cache(
    conn: sqlite3.Connection,
    *,
    video_sha256: str,
    exercise: str,
    cache_key: str,
    analysis: dict[str, Any],
    fusion: dict[str, Any],
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO llm_cache(
          video_sha256,exercise,cache_key,analysis_json,fusion_json,created_at
        ) VALUES (?,?,?,?,?,?)
        """,
        (
            video_sha256,
            exercise,
            cache_key,
            stable_json(analysis),
            stable_json(fusion),
            now_iso(),
        ),
    )


def usage_tokens(request_metrics: dict[str, Any] | None) -> tuple[int | None, int | None, int | None]:
    usage = request_metrics.get("usage") if isinstance(request_metrics, dict) else None
    if not isinstance(usage, dict):
        return None, None, None
    return (
        int(usage.get("promptTokens")) if isinstance(usage.get("promptTokens"), int) else None,
        int(usage.get("completionTokens")) if isinstance(usage.get("completionTokens"), int) else None,
        int(usage.get("totalTokens")) if isinstance(usage.get("totalTokens"), int) else None,
    )


def log_llm_usage(
    conn: sqlite3.Connection,
    *,
    video_sha256: str,
    set_id: str,
    exercise: str,
    model: str | None,
    cache_key: str,
    cache_hit: bool,
    status: str,
    error: str | None,
    request_metrics: dict[str, Any] | None,
) -> None:
    prompt_tokens, completion_tokens, total_tokens = usage_tokens(request_metrics)
    latency_ms = (
        int(request_metrics.get("latencyMs"))
        if isinstance(request_metrics, dict) and isinstance(request_metrics.get("latencyMs"), int)
        else None
    )
    if cache_hit:
        latency_ms = 0
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
    conn.execute(
        """
        INSERT INTO llm_usage_logs(
          video_sha256,set_id,exercise,model,cache_key,cache_hit,latency_ms,
          prompt_tokens,completion_tokens,total_tokens,status,error,created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            video_sha256,
            set_id,
            exercise,
            model,
            cache_key,
            1 if cache_hit else 0,
            latency_ms,
            prompt_tokens,
            completion_tokens,
            total_tokens,
            status,
            error,
            now_iso(),
        ),
    )


def llm_cache_enabled() -> bool:
    flag = (os.environ.get("SSC_LLM_ANALYSIS") or "").strip().lower()
    if flag in {"0", "false", "off", "no"}:
        return False
    return bool(os.environ.get("OPENAI_API_KEY"))


def model_cache_enabled() -> bool:
    flag = (os.environ.get("SSC_USE_MODEL_CACHE") or "1").strip().lower()
    return flag not in {"0", "false", "off", "no"}


def mark_job_failed(
    conn: sqlite3.Connection,
    *,
    job_id: str,
    failed_stage: str,
    failure_reason: str,
    pct: float,
) -> None:
    conn.execute(
        "UPDATE analysis_jobs SET status=?, failed_stage=?, failure_reason=?, finished_at=?, stage_json=? WHERE id=?",
        (
            "failed",
            failed_stage,
            failure_reason,
            now_iso(),
            json.dumps({"stage": failed_stage, "pct": pct}),
            job_id,
        ),
    )
    conn.commit()


def process_analysis_job(conn: sqlite3.Connection, row: sqlite3.Row) -> None:
    job_config = {}
    try:
        job_config = json.loads(row["calibration_json"] or "{}")
        if not isinstance(job_config, dict):
            job_config = {}
    except Exception:
        job_config = {}

    selected_coach_soul = (
        str(job_config.get("coachSoul")).strip()
        if job_config.get("coachSoul") is not None
        else None
    )
    if selected_coach_soul == "":
        selected_coach_soul = None

    video = conn.execute(
        "SELECT duration_ms,sha256 FROM videos WHERE id=?", (row["video_id"],)
    ).fetchone()
    duration_ms = int(video["duration_ms"] or 30000) if video else 30000
    video_sha256 = str(video["sha256"]) if video and video["sha256"] else ""

    _LOG.info(
        "job_start jobId=%s setId=%s videoId=%s sha256=%s durationMs=%s coachSoul=%s",
        row["id"],
        row["set_id"],
        row["video_id"],
        video_sha256,
        duration_ms,
        selected_coach_soul or "default",
    )

    stage = {"stage": "preprocessing", "pct": 0.1}
    conn.execute(
        "UPDATE analysis_jobs SET stage_json=? WHERE id=?",
        (json.dumps(stage), row["id"]),
    )
    conn.commit()

    barbell_result: dict[str, Any] | None = None
    barbell_error: str | None = None
    overlay_result: dict[str, Any] | None = None
    vbt_result: dict[str, Any] | None = None
    pose_result: dict[str, Any] | None = None
    video_quality_result: dict[str, Any] | None = None
    phases_result: list[dict[str, Any]] = []
    features_result: dict[str, Any] | None = None
    rule_analysis_result: dict[str, Any] | None = None
    analysis_result: dict[str, Any] | None = None
    fusion_result: dict[str, Any] | None = None
    video_classification_result: dict[str, Any] | None = None
    failed_stage: str | None = None
    failure_reason: str | None = None
    barbell_cache_key_value: str | None = None
    requested_exercise = str(row["exercise"])
    exercise = requested_exercise
    video_path = find_local_video_path(video_sha256)
    if video_path is None:
        barbell_error = "video file not found; set SSC_VIDEO_DIR and name file as <sha256>.mp4"
        failed_stage = "video_lookup"
        failure_reason = barbell_error
        _LOG.warning("video_not_found jobId=%s sha256=%s", row["id"], video_sha256)
    else:
        _LOG.info("video_found jobId=%s sha256=%s path=%s", row["id"], video_sha256, video_path)
        try:
            video_quality_result = analyze_video_quality(video_path=video_path)
        except Exception:
            video_quality_result = {
                "quality": {
                    "usable": False,
                    "confidence": 0.0,
                    "primaryWarning": "视频质量检查失败，分析结果可能不稳定。",
                },
                "metrics": {},
                "warnings": [{
                    "code": "quality_check_failed",
                    "label": "质量检查失败",
                    "message": "视频质量检查失败，分析结果可能不稳定。",
                }],
            }
            _LOG.exception("video_quality_failed jobId=%s", row["id"])

        try:
            stage = {"stage": "classifying_lift", "pct": 0.18}
            conn.execute("UPDATE analysis_jobs SET stage_json=? WHERE id=?", (json.dumps(stage), row["id"]))
            conn.commit()
            classify_cache_key = build_lift_classification_cache_key(duration_ms=duration_ms)
            cached_classification = (
                load_json_cache(
                    conn,
                    table="lift_classification_cache",
                    where={"video_sha256": video_sha256, "cache_key": classify_cache_key},
                    value_column="result_json",
                )
                if model_cache_enabled()
                else None
            )
            if cached_classification is not None:
                video_classification_result = cached_classification
                _LOG.info("lift_classification_cache_hit jobId=%s sha256=%s cacheKey=%s", row["id"], video_sha256, classify_cache_key)
            else:
                video_classification_result = classify_lift_from_video(video_path=video_path, duration_ms=duration_ms)
                if model_cache_enabled():
                    store_json_cache(
                        conn,
                        table="lift_classification_cache",
                        payload={"video_sha256": video_sha256, "cache_key": classify_cache_key},
                        value_column="result_json",
                        value=video_classification_result,
                    )
                    conn.commit()
                    _LOG.info("lift_classification_cache_store jobId=%s sha256=%s cacheKey=%s", row["id"], video_sha256, classify_cache_key)
            classified = (video_classification_result or {}).get("analysisExercise") if isinstance(video_classification_result, dict) else None
            if isinstance(classified, str) and classified:
                exercise = classified
            _LOG.info(
                "lift_classification jobId=%s requested=%s liftType=%s analysisExercise=%s confidence=%s",
                row["id"], requested_exercise,
                (video_classification_result or {}).get("liftType") if isinstance(video_classification_result, dict) else None,
                exercise,
                (video_classification_result or {}).get("confidence") if isinstance(video_classification_result, dict) else None,
            )
        except Exception:
            video_classification_result = {
                "enabled": False,
                "used": False,
                "liftType": requested_exercise,
                "analysisExercise": requested_exercise,
                "confidence": 0.0,
                "reason": "classification_failed",
            }
            exercise = requested_exercise
            _LOG.exception("lift_classification_failed jobId=%s", row["id"])

        stage = {"stage": "barbell_detecting", "pct": 0.6}
        conn.execute("UPDATE analysis_jobs SET stage_json=? WHERE id=?", (json.dumps(stage), row["id"]))
        conn.commit()
        try:
            detector = get_barbell_detector()
            sample_fps = env_float("SSC_BAR_DETECT_FPS", 15.0)
            batch_size = env_int("SSC_BAR_DETECT_BATCH", 8)
            max_frames = os.environ.get("SSC_BAR_MAX_FRAMES")
            max_frames_val = int(max_frames) if max_frames and max_frames.isdigit() else None
            barbell_cache_key_value = barbell_cache_key(
                detector=detector,
                sample_fps=sample_fps,
                batch_size=batch_size,
                max_frames=max_frames_val,
            )

            cached_barbell = (
                load_json_cache(
                    conn,
                    table="barbell_cache",
                    where={"video_sha256": video_sha256, "cache_key": barbell_cache_key_value},
                    value_column="result_json",
                )
                if model_cache_enabled()
                else None
            )
            if cached_barbell is not None:
                barbell_result = cached_barbell
                _LOG.info("bar_detect_cache_hit jobId=%s sha256=%s cacheKey=%s", row["id"], video_sha256, barbell_cache_key_value)
                dt = 0.0
            else:
                t0 = time.monotonic()
                _LOG.info(
                    "bar_detect_start jobId=%s sampleFps=%.2f batchSize=%s maxFrames=%s model=%s device=%s imgsz=%s conf=%.3f iou=%.3f",
                    row["id"], sample_fps, batch_size, max_frames_val,
                    detector.model_path, detector.device, detector.imgsz, detector.conf, detector.iou,
                )
                barbell_result = detector.detect_video(video_path, sample_fps=sample_fps, max_frames=max_frames_val, batch_size=batch_size)
                dt = time.monotonic() - t0
                if model_cache_enabled():
                    store_json_cache(
                        conn,
                        table="barbell_cache",
                        payload={"video_sha256": video_sha256, "cache_key": barbell_cache_key_value},
                        value_column="result_json",
                        value=barbell_result,
                    )
                    conn.commit()
                    _LOG.info("bar_detect_cache_store jobId=%s sha256=%s cacheKey=%s elapsedSec=%.3f", row["id"], video_sha256, barbell_cache_key_value, dt)

            frames = barbell_result.get("frames") if isinstance(barbell_result, dict) else None
            n_frames = len(frames) if isinstance(frames, list) else 0
            _LOG.info(
                "bar_detect_done jobId=%s elapsedSec=%.3f frames=%s frame=%sx%s sourceFps=%s sampleFps=%s",
                row["id"], dt, n_frames,
                barbell_result.get("frameWidth"), barbell_result.get("frameHeight"),
                barbell_result.get("sourceFps"), barbell_result.get("sampleFps"),
            )

            t1 = time.monotonic()
            vbt_result = compute_vbt_from_barbell(barbell_result, bar_end_diameter_cm=5.0)
            dt_v = time.monotonic() - t1
            if isinstance(vbt_result, dict) and vbt_result.get("error"):
                _LOG.warning("vbt_error jobId=%s error=%s", row["id"], vbt_result.get("error"))
            elif isinstance(vbt_result, dict):
                reps = vbt_result.get("reps")
                n_reps = len(reps) if isinstance(reps, list) else 0
                scale = vbt_result.get("scaleCmPerPx")
                scale_from = vbt_result.get("scaleFrom")
                start_ext = vbt_result.get("startExtremum") if isinstance(vbt_result, dict) else None
                avgs: list[str] = []
                if isinstance(reps, list):
                    for rep in reps[:5]:
                        if isinstance(rep, dict) and isinstance(rep.get("avgVelocityMps"), (int, float)):
                            avgs.append(f"{float(rep['avgVelocityMps']):.3f}")
                _LOG.info(
                    "vbt_done jobId=%s elapsedSec=%.3f reps=%s startExtremum=%s scaleCmPerPx=%s scaleFrom=%s avgMps=%s",
                    row["id"], dt_v, n_reps, start_ext, scale, scale_from, ",".join(avgs),
                )
        except Exception as e:
            barbell_error = str(e)
            failed_stage = "bar_detect"
            failure_reason = barbell_error
            _LOG.exception("bar_detect_failed jobId=%s", row["id"])

    if isinstance(barbell_result, dict):
        try:
            overlay_result = build_overlay_from_barbell(barbell_result)
        except Exception as e:
            overlay_result = {"anchor": "plate", "frames": [], "error": str(e)}
            _LOG.exception("overlay_build_failed jobId=%s", row["id"])

        if isinstance(overlay_result, dict) and overlay_result.get("error"):
            _LOG.warning("overlay_error jobId=%s error=%s", row["id"], overlay_result.get("error"))

    stage = {"stage": "pose_detecting", "pct": 0.72}
    conn.execute("UPDATE analysis_jobs SET stage_json=? WHERE id=?", (json.dumps(stage), row["id"]))
    conn.commit()

    if video_path is not None:
        try:
            pose_cache_key_value = pose_cache_key(exercise=exercise, barbell_cache_key=barbell_cache_key_value or "barbell-miss")
            cached_pose = (
                load_json_cache(
                    conn,
                    table="pose_cache",
                    where={"video_sha256": video_sha256, "exercise": exercise, "cache_key": pose_cache_key_value},
                    value_column="result_json",
                )
                if model_cache_enabled()
                else None
            )
            if cached_pose is not None:
                pose_result = cached_pose
                _LOG.info("pose_cache_hit jobId=%s sha256=%s exercise=%s cacheKey=%s", row["id"], video_sha256, exercise, pose_cache_key_value)
            else:
                pose_result = infer_pose(video_path=video_path, exercise=exercise, duration_ms=duration_ms, barbell_result=barbell_result)
                if model_cache_enabled():
                    store_json_cache(
                        conn,
                        table="pose_cache",
                        payload={"video_sha256": video_sha256, "exercise": exercise, "cache_key": pose_cache_key_value},
                        value_column="result_json",
                        value=pose_result,
                    )
                    conn.commit()
                    _LOG.info("pose_cache_store jobId=%s sha256=%s exercise=%s cacheKey=%s", row["id"], video_sha256, exercise, pose_cache_key_value)
        except Exception as e:
            pose_result = {
                "quality": {"usable": False, "confidence": 0.0, "reason": str(e)},
                "keypoints": [],
                "overlay": {"frames": []},
                "exercise": exercise,
                "durationMs": duration_ms,
            }
            _LOG.exception("pose_infer_failed jobId=%s", row["id"])

    if failed_stage is None and isinstance(vbt_result, dict) and vbt_result.get("error"):
        failed_stage = "vbt"
        failure_reason = str(vbt_result.get("error"))

    if failed_stage is not None and failure_reason is not None:
        mark_job_failed(
            conn,
            job_id=row["id"],
            failed_stage=failed_stage,
            failure_reason=failure_reason,
            pct=(0.75 if failed_stage == "vbt" else 0.6),
        )
        conn.close()
        return

    stage = {"stage": "extracting_features", "pct": 0.8}
    conn.execute("UPDATE analysis_jobs SET stage_json=? WHERE id=?", (json.dumps(stage), row["id"]))
    conn.commit()

    phases_result = segment_phases(exercise=exercise, overlay_result=overlay_result, vbt_result=vbt_result)
    features_result = extract_features(
        exercise=exercise,
        barbell_result=barbell_result,
        overlay_result=overlay_result,
        vbt_result=vbt_result,
        phases=phases_result,
        pose_result=pose_result,
        video_quality=video_quality_result,
    )

    stage = {"stage": "generating_analysis", "pct": 0.88}
    conn.execute("UPDATE analysis_jobs SET stage_json=? WHERE id=?", (json.dumps(stage), row["id"]))
    conn.commit()

    rule_analysis_result = build_analysis_result(
        exercise=exercise,
        features=features_result,
        phases=phases_result,
        video_quality=video_quality_result,
    )
    rule_evidence_result = build_rule_evidence_snapshot(rule_analysis_result)
    llm_cache_key_value: str | None = None
    if llm_cache_enabled() and model_cache_enabled():
        llm_cache_key_value = build_fused_analysis_cache_key(
            exercise=exercise,
            features=features_result,
            phases=phases_result,
            pose_result=pose_result,
            video_quality=video_quality_result,
            rule_evidence=rule_evidence_result,
            has_video=bool(video_path),
            coach_soul=selected_coach_soul,
        )
    cached_llm = (
        load_json_cache(
            conn,
            table="llm_cache",
            where={"video_sha256": video_sha256, "exercise": exercise, "cache_key": llm_cache_key_value},
            value_column="analysis_json",
        )
        if llm_cache_key_value
        else None
    )
    if cached_llm is not None and llm_cache_key_value is not None:
        analysis_result = cached_llm
        fusion_result = load_json_cache(
            conn,
            table="llm_cache",
            where={"video_sha256": video_sha256, "exercise": exercise, "cache_key": llm_cache_key_value},
            value_column="fusion_json",
        ) or {"enabled": True, "used": False, "reason": "cache_read_failed"}
        if isinstance(fusion_result, dict):
            fusion_result = {**fusion_result, "cacheHit": True}
        log_llm_usage(
            conn,
            video_sha256=video_sha256,
            set_id=row["set_id"],
            exercise=exercise,
            model=(fusion_result or {}).get("model") if isinstance(fusion_result, dict) else None,
            cache_key=llm_cache_key_value,
            cache_hit=True,
            status="cached",
            error=None,
            request_metrics=None,
        )
        conn.commit()
        _LOG.info("llm_cache_hit jobId=%s sha256=%s exercise=%s cacheKey=%s", row["id"], video_sha256, exercise, llm_cache_key_value)
    else:
        analysis_result, fusion_result = build_fused_analysis(
            exercise=exercise,
            features=features_result,
            phases=phases_result,
            pose_result=pose_result,
            video_quality=video_quality_result,
            rule_evidence=rule_evidence_result,
            fallback_analysis=rule_analysis_result,
            video_path=video_path,
            duration_ms=duration_ms,
            coach_soul=selected_coach_soul,
        )
        fusion_meta = fusion_result if isinstance(fusion_result, dict) else {}
        request_metrics = fusion_meta.get("requestMetrics") if isinstance(fusion_meta, dict) else None
        if fusion_meta.get("enabled"):
            log_llm_usage(
                conn,
                video_sha256=video_sha256,
                set_id=row["set_id"],
                exercise=exercise,
                model=fusion_meta.get("model") if isinstance(fusion_meta, dict) else None,
                cache_key=llm_cache_key_value or "llm-disabled",
                cache_hit=False,
                status="succeeded" if fusion_meta.get("used") else "failed",
                error=fusion_meta.get("error") if isinstance(fusion_meta, dict) else None,
                request_metrics=request_metrics if isinstance(request_metrics, dict) else None,
            )
        if llm_cache_key_value and isinstance(fusion_meta, dict) and fusion_meta.get("used"):
            store_llm_cache(
                conn,
                video_sha256=video_sha256,
                exercise=exercise,
                cache_key=llm_cache_key_value,
                analysis=analysis_result,
                fusion=fusion_result,
            )
            _LOG.info("llm_cache_store jobId=%s sha256=%s exercise=%s cacheKey=%s", row["id"], video_sha256, exercise, llm_cache_key_value)
        conn.commit()

    top3_raw, all_findings_raw = build_findings_from_analysis(analysis=analysis_result, features=features_result)
    score_result = build_score_result(
        exercise=exercise,
        features=features_result,
        analysis=analysis_result,
        video_quality=video_quality_result,
    )
    meta = {
        "durationMs": duration_ms,
        "note": "Phase 1 analysis: findings are rules-based and pose uses a real single-person inference path with graceful fallback when unavailable.",
        "barbell": {"result": barbell_result, "error": barbell_error},
        "overlay": overlay_result,
        "vbt": vbt_result,
        "pose": pose_result,
        "videoQuality": video_quality_result,
        "phases": phases_result,
        "features": features_result,
        "score": score_result,
        "analysisRule": rule_evidence_result,
        "analysisFusion": fusion_result,
        "analysis": analysis_result,
        "videoClassification": video_classification_result,
        "requestedExercise": requested_exercise,
        "analysisExercise": exercise,
    }

    conn.execute(
        "INSERT OR REPLACE INTO reports(set_id,status,top3_json,all_json,meta_json,created_at) VALUES (?,?,?,?,?,?)",
        (
            row["set_id"],
            "succeeded",
            json.dumps(top3_raw),
            json.dumps(all_findings_raw),
            json.dumps(meta),
            now_iso(),
        ),
    )

    conn.execute(
        "UPDATE analysis_jobs SET status=?, finished_at=?, stage_json=? WHERE id=?",
        ("succeeded", now_iso(), json.dumps({"stage": "done", "pct": 1.0}), row["id"]),
    )
    conn.commit()
    conn.close()
