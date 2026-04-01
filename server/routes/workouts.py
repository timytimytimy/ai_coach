from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from server.utils.auth import consume_daily_quota as _consume_daily_quota, get_current_user as _get_current_user
from server.utils.db import db, now_iso
from server.jobs import enqueue_job
from server.schemas import AnalysisJobCreateRequest, SetCreateRequest, WorkoutCreateRequest

router = APIRouter()


@router.post("/v1/workouts")
def create_workout(req: WorkoutCreateRequest, current_user: dict[str, Any] = Depends(_get_current_user)) -> dict[str, str]:
    workout_id = f"wkt_{uuid.uuid4().hex}"
    conn = db()
    conn.execute(
        "INSERT INTO workouts(id,user_id,day,created_at) VALUES (?,?,?,?)",
        (workout_id, current_user["id"], req.day, now_iso()),
    )
    conn.commit()
    conn.close()
    return {"workoutId": workout_id}


@router.post("/v1/workouts/{workout_id}/sets")
def create_set(
    workout_id: str,
    req: SetCreateRequest,
    current_user: dict[str, Any] = Depends(_get_current_user),
) -> dict[str, str]:
    set_id = f"set_{uuid.uuid4().hex}"
    conn = db()
    w = conn.execute("SELECT id,user_id FROM workouts WHERE id=?", (workout_id,)).fetchone()
    if w is None:
        conn.close()
        raise HTTPException(status_code=404, detail="workout not found")
    if w["user_id"] and w["user_id"] != current_user["id"]:
        conn.close()
        raise HTTPException(status_code=403, detail="workout belongs to another user")

    conn.execute(
        "INSERT INTO sets(id,user_id,workout_id,exercise,weight_kg,reps_done,rpe,video_id,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (set_id, current_user["id"], workout_id, req.exercise, req.weightKg, req.repsDone, req.rpe, req.videoId, now_iso()),
    )
    conn.commit()
    conn.close()
    return {"setId": set_id}


@router.post("/v1/sets/{set_id}/analysis-jobs")
def create_analysis_job(
    set_id: str,
    req: AnalysisJobCreateRequest,
    current_user: dict[str, Any] = Depends(_get_current_user),
) -> dict[str, Any]:
    conn = db()
    quota = _consume_daily_quota(conn, user_id=current_user["id"], kind="analyses")
    s = conn.execute("SELECT id,video_id,user_id FROM sets WHERE id=?", (set_id,)).fetchone()
    if s is None:
        conn.close()
        raise HTTPException(status_code=404, detail="set not found")
    if s["user_id"] and s["user_id"] != current_user["id"]:
        conn.close()
        raise HTTPException(status_code=403, detail="set belongs to another user")
    if not s["video_id"]:
        conn.close()
        raise HTTPException(status_code=400, detail="set has no video")

    v = conn.execute("SELECT id,sha256,user_id FROM videos WHERE id=?", (s["video_id"],)).fetchone()
    if v is None:
        conn.close()
        raise HTTPException(status_code=404, detail="video not found")
    if v["user_id"] and v["user_id"] != current_user["id"]:
        conn.close()
        raise HTTPException(status_code=403, detail="video belongs to another user")
    if v["sha256"] != req.videoSha256:
        conn.close()
        raise HTTPException(status_code=400, detail="video sha256 mismatch")

    idempotency_key = json.dumps({"sha256": req.videoSha256, "pipeline": req.pipelineVersion, "coachSoul": req.coachSoul}, sort_keys=True)
    existing = conn.execute(
        "SELECT id,status FROM analysis_jobs WHERE set_id=? AND pipeline_version=? AND calibration_json=? ORDER BY created_at DESC LIMIT 1",
        (set_id, req.pipelineVersion, idempotency_key),
    ).fetchone()
    if existing is not None and existing["status"] in ("queued", "running", "succeeded"):
        conn.commit()
        conn.close()
        return {"jobId": existing["id"], "status": existing["status"], "deduped": True, "quota": quota}

    job_id = f"job_{uuid.uuid4().hex}"
    conn.execute(
        "INSERT INTO analysis_jobs(id,user_id,set_id,video_id,pipeline_version,calibration_json,status,created_at,stage_json) VALUES (?,?,?,?,?,?,?,?,?)",
        (job_id, current_user["id"], set_id, s["video_id"], req.pipelineVersion, idempotency_key, "queued", now_iso(), json.dumps({"stage": "queued", "pct": 0.0})),
    )
    conn.commit()
    conn.close()
    enqueue_job(job_id)
    return {"jobId": job_id, "status": "queued", "deduped": False, "quota": quota}
