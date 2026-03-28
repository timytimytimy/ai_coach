from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from server.barbell import BarbellTrajectoryDetector, default_model_path, find_local_video_path
from server.barbell.overlay import build_overlay_from_barbell
from server.barbell.vbt import compute_vbt_from_barbell
from server.analysis import (
    build_analysis_result,
    build_findings_from_analysis,
    extract_features,
    segment_phases,
)
from server.pose import infer_pose
from server.fusion import build_fused_analysis, build_fused_analysis_cache_key
from server.video import analyze_video_quality

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

DB_PATH = os.environ.get("SSC_DB_PATH", os.path.join(os.path.dirname(__file__), "app.db"))
VIDEO_DIR = os.environ.get("SSC_VIDEO_DIR", os.path.join(os.path.dirname(__file__), "videos"))

_LOG = logging.getLogger("ssc")


def _setup_logging() -> None:
    level_name = (os.environ.get("SSC_LOG_LEVEL") or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
    else:
        root.setLevel(level)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_video_dir() -> str:
    p = os.path.abspath(VIDEO_DIR)
    os.makedirs(p, exist_ok=True)
    return p


def init_db() -> None:
    ensure_video_dir()
    conn = db()
    conn.executescript(
        """
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS videos(
          id TEXT PRIMARY KEY,
          sha256 TEXT NOT NULL UNIQUE,
          fps INTEGER,
          width INTEGER,
          height INTEGER,
          duration_ms INTEGER,
          created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS workouts(
          id TEXT PRIMARY KEY,
          day TEXT NOT NULL,
          created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sets(
          id TEXT PRIMARY KEY,
          workout_id TEXT NOT NULL,
          exercise TEXT NOT NULL,
          weight_kg REAL,
          reps_done INTEGER,
          rpe REAL,
          video_id TEXT,
          created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS analysis_jobs(
          id TEXT PRIMARY KEY,
          set_id TEXT NOT NULL,
          video_id TEXT NOT NULL,
          pipeline_version TEXT NOT NULL,
          calibration_json TEXT,
          status TEXT NOT NULL,
          failed_stage TEXT,
          failure_reason TEXT,
          created_at TEXT NOT NULL,
          started_at TEXT,
          finished_at TEXT,
          stage_json TEXT
        );

        CREATE TABLE IF NOT EXISTS reports(
          set_id TEXT PRIMARY KEY,
          status TEXT NOT NULL,
          top3_json TEXT NOT NULL,
          all_json TEXT NOT NULL,
          meta_json TEXT NOT NULL,
          created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS barbell_cache(
          video_sha256 TEXT NOT NULL,
          cache_key TEXT NOT NULL,
          result_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          PRIMARY KEY(video_sha256, cache_key)
        );

        CREATE TABLE IF NOT EXISTS pose_cache(
          video_sha256 TEXT NOT NULL,
          exercise TEXT NOT NULL,
          cache_key TEXT NOT NULL,
          result_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          PRIMARY KEY(video_sha256, exercise, cache_key)
        );

        CREATE TABLE IF NOT EXISTS llm_cache(
          video_sha256 TEXT NOT NULL,
          exercise TEXT NOT NULL,
          cache_key TEXT NOT NULL,
          analysis_json TEXT NOT NULL,
          fusion_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          PRIMARY KEY(video_sha256, exercise, cache_key)
        );

        CREATE TABLE IF NOT EXISTS llm_usage_logs(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          video_sha256 TEXT NOT NULL,
          set_id TEXT,
          exercise TEXT NOT NULL,
          model TEXT,
          cache_key TEXT NOT NULL,
          cache_hit INTEGER NOT NULL DEFAULT 0,
          latency_ms INTEGER,
          prompt_tokens INTEGER,
          completion_tokens INTEGER,
          total_tokens INTEGER,
          status TEXT NOT NULL,
          error TEXT,
          created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_llm_usage_video_created
          ON llm_usage_logs(video_sha256, created_at DESC);
        """
    )
    conn.commit()
    conn.close()


class VideoFinalizeRequest(BaseModel):
    fps: int | None = Field(default=None, ge=1, le=240)
    width: int | None = Field(default=None, ge=1, le=10000)
    height: int | None = Field(default=None, ge=1, le=10000)
    durationMs: int | None = Field(default=None, alias="durationMs", ge=0, le=3_600_000)
    sha256: str = Field(min_length=8, max_length=128)


class WorkoutCreateRequest(BaseModel):
    day: str


class SetCreateRequest(BaseModel):
    exercise: Literal["squat", "bench", "deadlift"]
    weightKg: float | None = Field(default=None, alias="weightKg")
    repsDone: int | None = Field(default=None, alias="repsDone")
    rpe: float | None = None
    videoId: str | None = Field(default=None, alias="videoId")


class Calibration(BaseModel):
    plateDiameterMm: int | None = Field(default=None, alias="plateDiameterMm")


class AnalysisJobCreateRequest(BaseModel):
    videoSha256: str = Field(alias="videoSha256")
    calibration: Calibration | None = None
    pipelineVersion: str = Field(default="pipe-v1", alias="pipelineVersion")


FindingSeverity = Literal["low", "medium", "high"]


class FindingEvent(BaseModel):
    label: str
    severity: FindingSeverity
    confidence: float = Field(ge=0, le=1)
    timeRangeMs: dict[str, int] = Field(alias="timeRangeMs")
    repIndex: int | None = Field(default=None, alias="repIndex")
    metrics: dict[str, float] = Field(default_factory=dict)


@dataclass
class JobWork:
    job_id: str


_job_queue: list[JobWork] = []
_job_lock = threading.Lock()

_barbell_lock = threading.Lock()
_barbell_detector: BarbellTrajectoryDetector | None = None

_BARBELL_CACHE_VERSION = "barbell-cache-v1"
_POSE_CACHE_VERSION = "pose-cache-v1"


def _env_float(name: str, default: float) -> float:
    v = os.environ.get(name)
    if v is None:
        return default
    try:
        return float(v)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    v = os.environ.get(name)
    if v is None:
        return default
    try:
        return int(float(v))
    except ValueError:
        return default


def get_barbell_detector() -> BarbellTrajectoryDetector:
    global _barbell_detector
    with _barbell_lock:
        if _barbell_detector is not None:
            return _barbell_detector
        model_path = os.environ.get("SSC_YOLO_MODEL_PATH") or default_model_path()
        device = os.environ.get("SSC_YOLO_DEVICE", "mps")
        imgsz = _env_int("SSC_YOLO_IMGSZ", 640)
        conf = _env_float("SSC_YOLO_CONF", 0.25)
        iou = _env_float("SSC_YOLO_IOU", 0.5)
        _barbell_detector = BarbellTrajectoryDetector(
            model_path=model_path,
            device=device,
            imgsz=imgsz,
            conf=conf,
            iou=iou,
        )
        return _barbell_detector


def _stable_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _barbell_cache_key(
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
    return _sha256_text(_stable_json(payload))


def _pose_cache_key(*, exercise: str, barbell_cache_key: str) -> str:
    payload = {
        "version": _POSE_CACHE_VERSION,
        "exercise": exercise,
        "barbellCacheKey": barbell_cache_key,
        "sampleFps": _env_float("SSC_POSE_SAMPLE_FPS", 12.0),
        "minVisibility": _env_float("SSC_POSE_MIN_VISIBILITY", 0.45),
        "minDetectionConf": _env_float("SSC_POSE_MIN_DETECTION_CONF", 0.5),
        "minTrackingConf": _env_float("SSC_POSE_MIN_TRACKING_CONF", 0.5),
        "modelComplexity": _env_int("SSC_POSE_MODEL_COMPLEXITY", 1),
        "roiMaxGapMs": _env_int("SSC_POSE_ROI_MAX_GAP_MS", 450),
    }
    return _sha256_text(_stable_json(payload))


def _load_json_cache(
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


def _store_json_cache(
    conn: sqlite3.Connection,
    *,
    table: str,
    payload: dict[str, Any],
    value_column: str,
    value: dict[str, Any],
) -> None:
    columns = list(payload.keys()) + [value_column, "created_at"]
    values = list(payload.values()) + [_stable_json(value), now_iso()]
    placeholders = ",".join("?" for _ in columns)
    conn.execute(
        f"INSERT OR REPLACE INTO {table}({','.join(columns)}) VALUES ({placeholders})",
        values,
    )


def _store_llm_cache(
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
            _stable_json(analysis),
            _stable_json(fusion),
            now_iso(),
        ),
    )


def _usage_tokens(request_metrics: dict[str, Any] | None) -> tuple[int | None, int | None, int | None]:
    usage = request_metrics.get("usage") if isinstance(request_metrics, dict) else None
    if not isinstance(usage, dict):
        return None, None, None
    return (
        int(usage.get("promptTokens")) if isinstance(usage.get("promptTokens"), int) else None,
        int(usage.get("completionTokens")) if isinstance(usage.get("completionTokens"), int) else None,
        int(usage.get("totalTokens")) if isinstance(usage.get("totalTokens"), int) else None,
    )


def _log_llm_usage(
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
    prompt_tokens, completion_tokens, total_tokens = _usage_tokens(request_metrics)
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


def _llm_cache_enabled() -> bool:
    flag = (os.environ.get("SSC_LLM_ANALYSIS") or "").strip().lower()
    if flag in {"0", "false", "off", "no"}:
        return False
    return bool(os.environ.get("OPENAI_API_KEY"))


def enqueue_job(job_id: str) -> None:
    with _job_lock:
        _job_queue.append(JobWork(job_id=job_id))


def pop_job() -> JobWork | None:
    with _job_lock:
        if not _job_queue:
            return None
        return _job_queue.pop(0)


def ms_to_mmss(ms: int) -> str:
    s = max(0, ms // 1000)
    return f"{s // 60:02d}:{s % 60:02d}"


def _mark_job_failed(
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


def job_worker_loop(stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        work = pop_job()
        if work is None:
            time.sleep(0.2)
            continue

        conn = db()
        row = conn.execute(
            "SELECT j.id,j.set_id,j.video_id,j.status,s.exercise FROM analysis_jobs j JOIN sets s ON s.id=j.set_id WHERE j.id = ?",
            (work.job_id,),
        ).fetchone()
        if row is None or row["status"] != "queued":
            conn.close()
            continue

        cur = conn.execute(
            "UPDATE analysis_jobs SET status=?, started_at=? WHERE id=? AND status=?",
            ("running", now_iso(), work.job_id, "queued"),
        )
        conn.commit()
        if cur.rowcount != 1:
            conn.close()
            continue

        video = conn.execute(
            "SELECT duration_ms,sha256 FROM videos WHERE id=?", (row["video_id"],)
        ).fetchone()
        duration_ms = int(video["duration_ms"] or 30000) if video else 30000
        video_sha256 = str(video["sha256"]) if video and video["sha256"] else ""

        _LOG.info(
            "job_start jobId=%s setId=%s videoId=%s sha256=%s durationMs=%s",
            work.job_id,
            row["set_id"],
            row["video_id"],
            video_sha256,
            duration_ms,
        )

        stage = {"stage": "preprocessing", "pct": 0.1}
        conn.execute(
            "UPDATE analysis_jobs SET stage_json=? WHERE id=?",
            (json.dumps(stage), work.job_id),
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
        failed_stage: str | None = None
        failure_reason: str | None = None
        barbell_cache_key: str | None = None
        exercise = str(row["exercise"])
        video_path = find_local_video_path(video_sha256)
        if video_path is None:
            barbell_error = "video file not found; set SSC_VIDEO_DIR and name file as <sha256>.mp4"
            failed_stage = "video_lookup"
            failure_reason = barbell_error
            _LOG.warning("video_not_found jobId=%s sha256=%s", work.job_id, video_sha256)
        else:
            _LOG.info("video_found jobId=%s sha256=%s path=%s", work.job_id, video_sha256, video_path)
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
                    "warnings": [
                        {
                            "code": "quality_check_failed",
                            "label": "质量检查失败",
                            "message": "视频质量检查失败，分析结果可能不稳定。",
                        }
                    ],
                }
                _LOG.exception("video_quality_failed jobId=%s", work.job_id)

            stage = {"stage": "barbell_detecting", "pct": 0.6}
            conn.execute(
                "UPDATE analysis_jobs SET stage_json=? WHERE id=?",
                (json.dumps(stage), work.job_id),
            )
            conn.commit()
            try:
                detector = get_barbell_detector()
                sample_fps = _env_float("SSC_BAR_DETECT_FPS", 15.0)
                batch_size = _env_int("SSC_BAR_DETECT_BATCH", 8)
                max_frames = os.environ.get("SSC_BAR_MAX_FRAMES")
                max_frames_val = int(max_frames) if max_frames and max_frames.isdigit() else None
                barbell_cache_key = _barbell_cache_key(
                    detector=detector,
                    sample_fps=sample_fps,
                    batch_size=batch_size,
                    max_frames=max_frames_val,
                )

                cached_barbell = _load_json_cache(
                    conn,
                    table="barbell_cache",
                    where={
                        "video_sha256": video_sha256,
                        "cache_key": barbell_cache_key,
                    },
                    value_column="result_json",
                )
                if cached_barbell is not None:
                    barbell_result = cached_barbell
                    _LOG.info(
                        "bar_detect_cache_hit jobId=%s sha256=%s cacheKey=%s",
                        work.job_id,
                        video_sha256,
                        barbell_cache_key,
                    )
                else:
                    t0 = time.monotonic()
                    _LOG.info(
                        "bar_detect_start jobId=%s sampleFps=%.2f batchSize=%s maxFrames=%s model=%s device=%s imgsz=%s conf=%.3f iou=%.3f",
                        work.job_id,
                        sample_fps,
                        batch_size,
                        max_frames_val,
                        detector.model_path,
                        detector.device,
                        detector.imgsz,
                        detector.conf,
                        detector.iou,
                    )

                    barbell_result = detector.detect_video(
                        video_path,
                        sample_fps=sample_fps,
                        max_frames=max_frames_val,
                        batch_size=batch_size,
                    )
                    dt = time.monotonic() - t0
                    _store_json_cache(
                        conn,
                        table="barbell_cache",
                        payload={
                            "video_sha256": video_sha256,
                            "cache_key": barbell_cache_key,
                        },
                        value_column="result_json",
                        value=barbell_result,
                    )
                    conn.commit()
                    _LOG.info(
                        "bar_detect_cache_store jobId=%s sha256=%s cacheKey=%s elapsedSec=%.3f",
                        work.job_id,
                        video_sha256,
                        barbell_cache_key,
                        dt,
                    )

                frames = barbell_result.get("frames") if isinstance(barbell_result, dict) else None
                n_frames = len(frames) if isinstance(frames, list) else 0
                _LOG.info(
                    "bar_detect_done jobId=%s elapsedSec=%.3f frames=%s frame=%sx%s sourceFps=%s sampleFps=%s",
                    work.job_id,
                    0.0 if cached_barbell is not None else dt,
                    n_frames,
                    barbell_result.get("frameWidth"),
                    barbell_result.get("frameHeight"),
                    barbell_result.get("sourceFps"),
                    barbell_result.get("sampleFps"),
                )

                t1 = time.monotonic()
                vbt_result = compute_vbt_from_barbell(barbell_result, bar_end_diameter_cm=5.0)
                dt_v = time.monotonic() - t1

                if isinstance(vbt_result, dict) and vbt_result.get("error"):
                    _LOG.warning("vbt_error jobId=%s error=%s", work.job_id, vbt_result.get("error"))
                elif isinstance(vbt_result, dict):
                    reps = vbt_result.get("reps")
                    n_reps = len(reps) if isinstance(reps, list) else 0
                    scale = vbt_result.get("scaleCmPerPx")
                    scale_from = vbt_result.get("scaleFrom")
                    start_ext = vbt_result.get("startExtremum") if isinstance(vbt_result, dict) else None
                    avgs: list[str] = []
                    if isinstance(reps, list):
                        for r in reps[:5]:
                            if isinstance(r, dict) and isinstance(r.get("avgVelocityMps"), (int, float)):
                                avgs.append(f"{float(r['avgVelocityMps']):.3f}")
                    _LOG.info(
                        "vbt_done jobId=%s elapsedSec=%.3f reps=%s startExtremum=%s scaleCmPerPx=%s scaleFrom=%s avgMps=%s",
                        work.job_id,
                        dt_v,
                        n_reps,
                        start_ext,
                        scale,
                        scale_from,
                        ",".join(avgs),
                    )
            except Exception as e:
                barbell_error = str(e)
                failed_stage = "bar_detect"
                failure_reason = barbell_error
                _LOG.exception("bar_detect_failed jobId=%s", work.job_id)

        if isinstance(barbell_result, dict):
            try:
                overlay_result = build_overlay_from_barbell(barbell_result)
            except Exception as e:
                overlay_result = {"anchor": "plate", "frames": [], "error": str(e)}
                _LOG.exception("overlay_build_failed jobId=%s", work.job_id)

            if isinstance(overlay_result, dict) and overlay_result.get("error"):
                _LOG.warning("overlay_error jobId=%s error=%s", work.job_id, overlay_result.get("error"))

        stage = {"stage": "pose_detecting", "pct": 0.72}
        conn.execute(
            "UPDATE analysis_jobs SET stage_json=? WHERE id=?",
            (json.dumps(stage), work.job_id),
        )
        conn.commit()

        if video_path is not None:
            try:
                pose_cache_key = _pose_cache_key(
                    exercise=exercise,
                    barbell_cache_key=barbell_cache_key or "barbell-miss",
                )
                cached_pose = _load_json_cache(
                    conn,
                    table="pose_cache",
                    where={
                        "video_sha256": video_sha256,
                        "exercise": exercise,
                        "cache_key": pose_cache_key,
                    },
                    value_column="result_json",
                )
                if cached_pose is not None:
                    pose_result = cached_pose
                    _LOG.info(
                        "pose_cache_hit jobId=%s sha256=%s exercise=%s cacheKey=%s",
                        work.job_id,
                        video_sha256,
                        exercise,
                        pose_cache_key,
                    )
                else:
                    pose_result = infer_pose(
                        video_path=video_path,
                        exercise=exercise,
                        duration_ms=duration_ms,
                        barbell_result=barbell_result,
                    )
                    _store_json_cache(
                        conn,
                        table="pose_cache",
                        payload={
                            "video_sha256": video_sha256,
                            "exercise": exercise,
                            "cache_key": pose_cache_key,
                        },
                        value_column="result_json",
                        value=pose_result,
                    )
                    conn.commit()
                    _LOG.info(
                        "pose_cache_store jobId=%s sha256=%s exercise=%s cacheKey=%s",
                        work.job_id,
                        video_sha256,
                        exercise,
                        pose_cache_key,
                    )
            except Exception as e:
                pose_result = {
                    "quality": {"usable": False, "confidence": 0.0, "reason": str(e)},
                    "keypoints": [],
                    "overlay": {"frames": []},
                    "exercise": exercise,
                    "durationMs": duration_ms,
                }
                _LOG.exception("pose_infer_failed jobId=%s", work.job_id)

        if failed_stage is None and isinstance(vbt_result, dict) and vbt_result.get("error"):
            failed_stage = "vbt"
            failure_reason = str(vbt_result.get("error"))

        if failed_stage is not None and failure_reason is not None:
            _mark_job_failed(
                conn,
                job_id=work.job_id,
                failed_stage=failed_stage,
                failure_reason=failure_reason,
                pct=(0.75 if failed_stage == "vbt" else 0.6),
            )
            conn.close()
            continue

        stage = {"stage": "extracting_features", "pct": 0.8}
        conn.execute(
            "UPDATE analysis_jobs SET stage_json=? WHERE id=?",
            (json.dumps(stage), work.job_id),
        )
        conn.commit()

        phases_result = segment_phases(
            exercise=exercise,
            overlay_result=overlay_result,
            vbt_result=vbt_result,
        )
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
        conn.execute(
            "UPDATE analysis_jobs SET stage_json=? WHERE id=?",
            (json.dumps(stage), work.job_id),
        )
        conn.commit()

        rule_analysis_result = build_analysis_result(
            exercise=exercise,
            features=features_result,
            phases=phases_result,
            video_quality=video_quality_result,
        )
        llm_cache_key: str | None = None
        if _llm_cache_enabled():
            llm_cache_key = build_fused_analysis_cache_key(
                exercise=exercise,
                features=features_result,
                phases=phases_result,
                pose_result=pose_result,
                video_quality=video_quality_result,
                rule_analysis=rule_analysis_result,
                has_video=bool(video_path),
            )
        cached_llm = (
            _load_json_cache(
                conn,
                table="llm_cache",
                where={
                    "video_sha256": video_sha256,
                    "exercise": exercise,
                    "cache_key": llm_cache_key,
                },
                value_column="analysis_json",
            )
            if llm_cache_key
            else None
        )
        if cached_llm is not None and llm_cache_key is not None:
            analysis_result = cached_llm
            fusion_result = _load_json_cache(
                conn,
                table="llm_cache",
                where={
                    "video_sha256": video_sha256,
                    "exercise": exercise,
                    "cache_key": llm_cache_key,
                },
                value_column="fusion_json",
            ) or {"enabled": True, "used": False, "reason": "cache_read_failed"}
            if isinstance(fusion_result, dict):
                fusion_result = {**fusion_result, "cacheHit": True}
            _log_llm_usage(
                conn,
                video_sha256=video_sha256,
                set_id=row["set_id"],
                exercise=exercise,
                model=(fusion_result or {}).get("model") if isinstance(fusion_result, dict) else None,
                cache_key=llm_cache_key,
                cache_hit=True,
                status="cached",
                error=None,
                request_metrics=None,
            )
            conn.commit()
            _LOG.info(
                "llm_cache_hit jobId=%s sha256=%s exercise=%s cacheKey=%s",
                work.job_id,
                video_sha256,
                exercise,
                llm_cache_key,
            )
        else:
            analysis_result, fusion_result = build_fused_analysis(
                exercise=exercise,
                features=features_result,
                phases=phases_result,
                pose_result=pose_result,
                video_quality=video_quality_result,
                rule_analysis=rule_analysis_result,
                video_path=video_path,
                duration_ms=duration_ms,
            )
            fusion_meta = fusion_result if isinstance(fusion_result, dict) else {}
            request_metrics = fusion_meta.get("requestMetrics") if isinstance(fusion_meta, dict) else None
            if fusion_meta.get("enabled"):
                _log_llm_usage(
                    conn,
                    video_sha256=video_sha256,
                    set_id=row["set_id"],
                    exercise=exercise,
                    model=fusion_meta.get("model") if isinstance(fusion_meta, dict) else None,
                    cache_key=llm_cache_key or "llm-disabled",
                    cache_hit=False,
                    status="succeeded" if fusion_meta.get("used") else "failed",
                    error=fusion_meta.get("error") if isinstance(fusion_meta, dict) else None,
                    request_metrics=request_metrics if isinstance(request_metrics, dict) else None,
                )
            if llm_cache_key and isinstance(fusion_meta, dict) and fusion_meta.get("used"):
                _store_llm_cache(
                    conn,
                    video_sha256=video_sha256,
                    exercise=exercise,
                    cache_key=llm_cache_key,
                    analysis=analysis_result,
                    fusion=fusion_result,
                )
                _LOG.info(
                    "llm_cache_store jobId=%s sha256=%s exercise=%s cacheKey=%s",
                    work.job_id,
                    video_sha256,
                    exercise,
                    llm_cache_key,
                )
            conn.commit()

        top3_raw, all_findings_raw = build_findings_from_analysis(
            analysis=analysis_result,
            features=features_result,
        )
        top3 = [FindingEvent.model_validate(item) for item in top3_raw]
        all_findings = [FindingEvent.model_validate(item) for item in all_findings_raw]
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
            "analysisRule": rule_analysis_result,
            "analysisFusion": fusion_result,
            "analysis": analysis_result,
        }

        conn.execute(
            "INSERT OR REPLACE INTO reports(set_id,status,top3_json,all_json,meta_json,created_at) VALUES (?,?,?,?,?,?)",
            (
                row["set_id"],
                "succeeded",
                json.dumps([f.model_dump(by_alias=True) for f in top3]),
                json.dumps([f.model_dump(by_alias=True) for f in all_findings]),
                json.dumps(meta),
                now_iso(),
            ),
        )

        conn.execute(
            "UPDATE analysis_jobs SET status=?, finished_at=?, stage_json=? WHERE id=?",
            ("succeeded", now_iso(), json.dumps({"stage": "done", "pct": 1.0}), work.job_id),
        )
        conn.commit()
        conn.close()


app = FastAPI(title="Smart Strength Coach API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

_stop_event = threading.Event()
_worker_thread: threading.Thread | None = None


@app.on_event("startup")
def on_startup() -> None:
    _setup_logging()
    _LOG.info("startup dbPath=%s videoDir=%s", DB_PATH, os.path.abspath(VIDEO_DIR))
    init_db()
    global _worker_thread
    if _worker_thread is None:
        _worker_thread = threading.Thread(target=job_worker_loop, args=(_stop_event,), daemon=True)
        _worker_thread.start()
        _LOG.info("worker_started")


@app.on_event("shutdown")
def on_shutdown() -> None:
    _stop_event.set()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/videos")
def create_video(req: Request) -> dict[str, Any]:
    video_id = f"vid_{uuid.uuid4().hex}"
    return {
        "videoId": video_id,
        "upload": {
            "method": "POST",
            "url": str(req.url_for("upload_video", video_id=video_id)),
            "formField": "file",
        },
        "note": "MVP: uploads are stored locally on the server; set SSC_VIDEO_DIR to control storage path",
    }


@app.post("/v1/videos/{video_id}/finalize")
def finalize_video(video_id: str, req: VideoFinalizeRequest) -> dict[str, Any]:
    conn = db()

    by_id = conn.execute("SELECT id,sha256 FROM videos WHERE id=?", (video_id,)).fetchone()
    if by_id is not None:
        if by_id["sha256"] != req.sha256:
            conn.close()
            raise HTTPException(status_code=409, detail="video id already exists with different sha256")

        conn.execute(
            "UPDATE videos SET fps=?, width=?, height=?, duration_ms=? WHERE id=?",
            (req.fps, req.width, req.height, req.durationMs, video_id),
        )
        conn.commit()
        conn.close()
        return {"videoId": by_id["id"], "deduped": True}

    by_sha = conn.execute("SELECT id FROM videos WHERE sha256=?", (req.sha256,)).fetchone()
    if by_sha is not None:
        conn.close()
        return {"videoId": by_sha["id"], "deduped": True}

    try:
        conn.execute(
            "INSERT INTO videos(id,sha256,fps,width,height,duration_ms,created_at) VALUES (?,?,?,?,?,?,?)",
            (
                video_id,
                req.sha256,
                req.fps,
                req.width,
                req.height,
                req.durationMs,
                now_iso(),
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=409, detail="video already exists")

    conn.close()
    return {"videoId": video_id, "deduped": False}


@app.post("/v1/videos/{video_id}/upload", name="upload_video")
async def upload_video(video_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
    ensure_video_dir()

    filename = (file.filename or "upload.mp4").strip()
    _, ext = os.path.splitext(filename)
    ext = ext.lower()
    if ext not in (".mp4", ".mov", ".m4v", ".webm"):
        ext = ".mp4"

    tmp_path = os.path.join(os.path.abspath(VIDEO_DIR), f".{video_id}.uploading{ext}")
    h = hashlib.sha256()

    with open(tmp_path, "wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
            out.write(chunk)

    sha = h.hexdigest()
    final_path = os.path.join(os.path.abspath(VIDEO_DIR), f"{sha}{ext}")

    if os.path.exists(final_path):
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        conn = db()
        existing = conn.execute("SELECT id FROM videos WHERE sha256=?", (sha,)).fetchone()
        conn.close()
        return {"videoId": existing["id"] if existing else video_id, "sha256": sha, "deduped": True}

    os.replace(tmp_path, final_path)

    conn = db()
    by_id = conn.execute("SELECT id,sha256 FROM videos WHERE id=?", (video_id,)).fetchone()
    if by_id is not None and by_id["sha256"] != sha:
        conn.close()
        raise HTTPException(status_code=409, detail="video id already exists with different sha256")

    by_sha = conn.execute("SELECT id FROM videos WHERE sha256=?", (sha,)).fetchone()
    if by_sha is not None:
        conn.close()
        return {"videoId": by_sha["id"], "sha256": sha, "deduped": True}

    conn.execute(
        "INSERT INTO videos(id,sha256,created_at) VALUES (?,?,?)",
        (video_id, sha, now_iso()),
    )
    conn.commit()
    conn.close()

    return {"videoId": video_id, "sha256": sha, "deduped": False}


@app.post("/v1/workouts")
def create_workout(req: WorkoutCreateRequest) -> dict[str, str]:
    workout_id = f"wkt_{uuid.uuid4().hex}"
    conn = db()
    conn.execute(
        "INSERT INTO workouts(id,day,created_at) VALUES (?,?,?)",
        (workout_id, req.day, now_iso()),
    )
    conn.commit()
    conn.close()
    return {"workoutId": workout_id}


@app.post("/v1/workouts/{workout_id}/sets")
def create_set(workout_id: str, req: SetCreateRequest) -> dict[str, str]:
    set_id = f"set_{uuid.uuid4().hex}"
    conn = db()
    w = conn.execute("SELECT id FROM workouts WHERE id=?", (workout_id,)).fetchone()
    if w is None:
        conn.close()
        raise HTTPException(status_code=404, detail="workout not found")

    conn.execute(
        "INSERT INTO sets(id,workout_id,exercise,weight_kg,reps_done,rpe,video_id,created_at) VALUES (?,?,?,?,?,?,?,?)",
        (
            set_id,
            workout_id,
            req.exercise,
            req.weightKg,
            req.repsDone,
            req.rpe,
            req.videoId,
            now_iso(),
        ),
    )
    conn.commit()
    conn.close()
    return {"setId": set_id}


@app.post("/v1/sets/{set_id}/analysis-jobs")
def create_analysis_job(set_id: str, req: AnalysisJobCreateRequest) -> dict[str, Any]:
    conn = db()
    s = conn.execute("SELECT id,video_id FROM sets WHERE id=?", (set_id,)).fetchone()
    if s is None:
        conn.close()
        raise HTTPException(status_code=404, detail="set not found")
    if not s["video_id"]:
        conn.close()
        raise HTTPException(status_code=400, detail="set has no video")

    v = conn.execute("SELECT id,sha256 FROM videos WHERE id=?", (s["video_id"],)).fetchone()
    if v is None:
        conn.close()
        raise HTTPException(status_code=404, detail="video not found")

    if v["sha256"] != req.videoSha256:
        conn.close()
        raise HTTPException(status_code=400, detail="video sha256 mismatch")

    idempotency_key = json.dumps(
        {
            "sha256": req.videoSha256,
            "pipeline": req.pipelineVersion,
        },
        sort_keys=True,
    )

    existing = conn.execute(
        "SELECT id,status FROM analysis_jobs WHERE set_id=? AND pipeline_version=? AND calibration_json=? ORDER BY created_at DESC LIMIT 1",
        (set_id, req.pipelineVersion, idempotency_key),
    ).fetchone()
    if existing is not None and existing["status"] in ("queued", "running", "succeeded"):
        conn.close()
        return {"jobId": existing["id"], "status": existing["status"], "deduped": True}

    job_id = f"job_{uuid.uuid4().hex}"
    conn.execute(
        "INSERT INTO analysis_jobs(id,set_id,video_id,pipeline_version,calibration_json,status,created_at,stage_json) VALUES (?,?,?,?,?,?,?,?)",
        (
            job_id,
            set_id,
            s["video_id"],
            req.pipelineVersion,
            idempotency_key,
            "queued",
            now_iso(),
            json.dumps({"stage": "queued", "pct": 0.0}),
        ),
    )
    conn.commit()
    conn.close()

    enqueue_job(job_id)
    return {"jobId": job_id, "status": "queued", "deduped": False}


@app.get("/v1/analysis-jobs/{job_id}")
def get_analysis_job(job_id: str) -> dict[str, Any]:
    conn = db()
    row = conn.execute(
        "SELECT id,status,failed_stage,failure_reason,created_at,started_at,finished_at,stage_json FROM analysis_jobs WHERE id=?",
        (job_id,),
    ).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="job not found")

    stage = json.loads(row["stage_json"]) if row["stage_json"] else None
    return {
        "jobId": row["id"],
        "status": row["status"],
        "failedStage": row["failed_stage"],
        "failureReason": row["failure_reason"],
        "createdAt": row["created_at"],
        "startedAt": row["started_at"],
        "finishedAt": row["finished_at"],
        "progress": stage,
    }


@app.get("/v1/sets/{set_id}/report")
def get_report(set_id: str) -> Any:
    conn = db()
    rep = conn.execute(
        "SELECT status,top3_json,all_json,meta_json,created_at FROM reports WHERE set_id=?",
        (set_id,),
    ).fetchone()
    if rep is None:
        job = conn.execute(
            "SELECT id,status,failed_stage,failure_reason,stage_json,created_at,started_at,finished_at FROM analysis_jobs WHERE set_id=? ORDER BY created_at DESC LIMIT 1",
            (set_id,),
        ).fetchone()
        conn.close()
        if job is None:
            raise HTTPException(status_code=404, detail="report not found")

        progress = json.loads(job["stage_json"]) if job["stage_json"] else None
        if job["status"] in ("queued", "running"):
            return JSONResponse(
                status_code=202,
                content={
                    "status": "pending",
                    "jobId": job["id"],
                    "progress": progress,
                    "createdAt": job["created_at"],
                    "startedAt": job["started_at"],
                    "finishedAt": job["finished_at"],
                },
            )

        if job["status"] == "failed":
            return {
                "status": "failed",
                "jobId": job["id"],
                "failedStage": job["failed_stage"],
                "failureReason": job["failure_reason"],
                "progress": progress,
                "createdAt": job["created_at"],
                "startedAt": job["started_at"],
                "finishedAt": job["finished_at"],
            }

        return JSONResponse(status_code=404, content={"detail": "report not found"})

    conn.close()

    top3 = json.loads(rep["top3_json"])
    all_findings = json.loads(rep["all_json"])

    def decorate(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for f in findings:
            tr = f.get("timeRangeMs") or {}
            s0 = int(tr.get("start", 0))
            e0 = int(tr.get("end", 0))
            s = min(s0, e0)
            e = max(s0, e0)
            out.append(
                {
                    **f,
                    "timeRangeMmss": f"{ms_to_mmss(s)}-{ms_to_mmss(e)}",
                }
            )
        return out

    return {
        "status": rep["status"],
        "top3": decorate(top3),
        "all": decorate(all_findings),
        "meta": json.loads(rep["meta_json"]),
        "createdAt": rep["created_at"],
    }
