from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from server.utils.auth import get_current_user as _get_current_user
from server.utils.db import db
from server.jobs import ms_to_mmss

router = APIRouter()


@router.get("/v1/analysis-jobs/{job_id}")
def get_analysis_job(job_id: str, current_user: dict[str, Any] = Depends(_get_current_user)) -> dict[str, Any]:
    conn = db()
    row = conn.execute(
        "SELECT id,user_id,status,failed_stage,failure_reason,created_at,started_at,finished_at,stage_json FROM analysis_jobs WHERE id=?",
        (job_id,),
    ).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="job not found")
    if row["user_id"] and row["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="job belongs to another user")

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


@router.get("/v1/sets/{set_id}/report")
def get_report(set_id: str, current_user: dict[str, Any] = Depends(_get_current_user)) -> Any:
    conn = db()
    owned = conn.execute("SELECT user_id FROM sets WHERE id=?", (set_id,)).fetchone()
    if owned is None:
        conn.close()
        raise HTTPException(status_code=404, detail="set not found")
    if owned["user_id"] and owned["user_id"] != current_user["id"]:
        conn.close()
        raise HTTPException(status_code=403, detail="set belongs to another user")
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
        for finding in findings:
            tr = finding.get("timeRangeMs") or {}
            s0 = int(tr.get("start", 0))
            e0 = int(tr.get("end", 0))
            s = min(s0, e0)
            e = max(s0, e0)
            out.append({**finding, "timeRangeMmss": f"{ms_to_mmss(s)}-{ms_to_mmss(e)}"})
        return out

    return {
        "status": rep["status"],
        "top3": decorate(top3),
        "all": decorate(all_findings),
        "meta": json.loads(rep["meta_json"]),
        "createdAt": rep["created_at"],
    }
