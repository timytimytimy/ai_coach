from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

from server.utils.accel import (
    default_rtmpose_backend,
    default_rtmpose_device,
    default_yolo_device,
    mediapipe_runtime_device,
    mediapipe_runtime_note,
)
from server.utils.config import VIDEO_DIR
from server.utils.db import db, now_iso
from server.fusion import llm_supports_video_input
from server.jobs.queue import pop_job
from server.pipeline import process_analysis_job
from server.pose import get_pose_impl

_LOG = logging.getLogger("ssc")


def ms_to_mmss(ms: int) -> str:
    s = max(0, ms // 1000)
    return f"{s // 60:02d}:{s % 60:02d}"


def runtime_summary(model_name: str) -> dict[str, Any]:
    return {
        "poseImpl": get_pose_impl(),
        "yoloDevice": default_yolo_device(),
        "rtmposeBackend": default_rtmpose_backend(),
        "rtmposeDevice": default_rtmpose_device(),
        "mediapipeDevice": mediapipe_runtime_device(),
        "mediapipeNote": mediapipe_runtime_note(),
        "llmModel": model_name,
        "llmVideoInput": llm_supports_video_input(model_name),
        "videoDir": os.path.abspath(VIDEO_DIR),
    }


def _mark_job_failed(conn, *, job_id: str, failure_reason: str) -> None:
    conn.execute(
        "UPDATE analysis_jobs SET status=?, failed_stage=?, failure_reason=?, finished_at=?, stage_json=? WHERE id=?",
        (
            "failed",
            "worker",
            failure_reason,
            now_iso(),
            '{"stage":"worker","pct":0.0}',
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
        try:
            row = conn.execute(
                "SELECT j.id,j.set_id,j.video_id,j.status,j.calibration_json,s.exercise FROM analysis_jobs j JOIN sets s ON s.id=j.set_id WHERE j.id = ?",
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

            process_analysis_job(conn, row)
        except Exception as exc:
            _LOG.exception("job_worker_failed jobId=%s", work.job_id)
            try:
                _mark_job_failed(conn, job_id=work.job_id, failure_reason=str(exc))
            finally:
                conn.close()
