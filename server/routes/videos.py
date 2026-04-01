from __future__ import annotations

import hashlib
import os
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from server.utils.auth import consume_daily_quota as _consume_daily_quota, get_current_user as _get_current_user
from server.utils.config import VIDEO_DIR
from server.utils.db import db, ensure_video_dir, now_iso
from server.schemas import VideoFinalizeRequest

router = APIRouter()


@router.post("/v1/videos")
def create_video(req: Request, current_user: dict[str, Any] = Depends(_get_current_user)) -> dict[str, Any]:
    import uuid
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


@router.post("/v1/videos/{video_id}/finalize")
def finalize_video(
    video_id: str,
    req: VideoFinalizeRequest,
    current_user: dict[str, Any] = Depends(_get_current_user),
) -> dict[str, Any]:
    conn = db()

    by_id = conn.execute("SELECT id,sha256,user_id FROM videos WHERE id=?", (video_id,)).fetchone()
    if by_id is not None:
        if by_id["user_id"] and by_id["user_id"] != current_user["id"]:
            conn.close()
            raise HTTPException(status_code=403, detail="video belongs to another user")
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

    by_sha = conn.execute("SELECT id,user_id FROM videos WHERE sha256=?", (req.sha256,)).fetchone()
    if by_sha is not None:
        conn.close()
        if by_sha["user_id"] and by_sha["user_id"] != current_user["id"]:
            raise HTTPException(status_code=409, detail="video already exists for another user")
        return {"videoId": by_sha["id"], "deduped": True}

    try:
        conn.execute(
            "INSERT INTO videos(id,user_id,sha256,fps,width,height,duration_ms,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (video_id, current_user["id"], req.sha256, req.fps, req.width, req.height, req.durationMs, now_iso()),
        )
        conn.commit()
    except Exception:
        conn.close()
        raise HTTPException(status_code=409, detail="video already exists")

    conn.close()
    return {"videoId": video_id, "deduped": False}


@router.post("/v1/videos/{video_id}/upload", name="upload_video")
async def upload_video(
    video_id: str,
    file: UploadFile = File(...),
    current_user: dict[str, Any] = Depends(_get_current_user),
) -> dict[str, Any]:
    conn = db()
    quota = _consume_daily_quota(conn, user_id=current_user["id"], kind="uploads")
    conn.commit()
    conn.close()
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
        existing = conn.execute("SELECT id,user_id FROM videos WHERE sha256=?", (sha,)).fetchone()
        conn.close()
        if existing is not None and existing["user_id"] and existing["user_id"] != current_user["id"]:
            raise HTTPException(status_code=409, detail="video already exists for another user")
        return {"videoId": existing["id"] if existing else video_id, "sha256": sha, "deduped": True, "quota": quota}

    os.replace(tmp_path, final_path)

    conn = db()
    by_id = conn.execute("SELECT id,sha256,user_id FROM videos WHERE id=?", (video_id,)).fetchone()
    if by_id is not None and by_id["sha256"] != sha:
        conn.close()
        raise HTTPException(status_code=409, detail="video id already exists with different sha256")
    if by_id is not None and by_id["user_id"] and by_id["user_id"] != current_user["id"]:
        conn.close()
        raise HTTPException(status_code=403, detail="video belongs to another user")

    by_sha = conn.execute("SELECT id,user_id FROM videos WHERE sha256=?", (sha,)).fetchone()
    if by_sha is not None:
        conn.close()
        if by_sha["user_id"] and by_sha["user_id"] != current_user["id"]:
            raise HTTPException(status_code=409, detail="video already exists for another user")
        return {"videoId": by_sha["id"], "sha256": sha, "deduped": True, "quota": quota}

    conn.execute(
        "INSERT INTO videos(id,user_id,sha256,created_at) VALUES (?,?,?,?)",
        (video_id, current_user["id"], sha, now_iso()),
    )
    conn.commit()
    conn.close()
    return {"videoId": video_id, "sha256": sha, "deduped": False, "quota": quota}
