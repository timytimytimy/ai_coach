from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException

from server.utils.auth import (
    create_session as _create_session,
    get_current_user as _get_current_user,
    normalize_username as _normalize_username,
    password_hash as _password_hash,
    password_verify as _password_verify,
    quota_snapshot as _quota_snapshot,
    serialize_user as _serialize_user,
    session_payload as _session_payload,
    token_hash as _token_hash,
    utc_now as _utc_now,
)
from server.utils.db import db, now_iso
from server.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    ProfileUpdateRequest,
    RefreshRequest,
    RegisterRequest,
)

router = APIRouter()


@router.post("/v1/auth/register")
def register(req: RegisterRequest) -> dict[str, Any]:
    username = _normalize_username(req.username)
    display_name = (req.displayName or username).strip() or username
    conn = db()
    existing = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    if existing is not None:
        conn.close()
        raise HTTPException(status_code=409, detail="username already exists")
    user_id = f"user_{uuid.uuid4().hex}"
    conn.execute(
        """
        INSERT INTO users(id,username,password_hash,display_name,created_at,updated_at,is_active)
        VALUES (?,?,?,?,?,?,1)
        """,
        (user_id, username, _password_hash(req.password), display_name, now_iso(), now_iso()),
    )
    session = _create_session(conn, user_id)
    conn.commit()
    user_row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    assert user_row is not None
    return {"user": _serialize_user(user_row), "session": _session_payload(session)}


@router.post("/v1/auth/login")
def login(req: LoginRequest) -> dict[str, Any]:
    username = _normalize_username(req.username)
    conn = db()
    user_row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if user_row is None or not _password_verify(req.password, user_row["password_hash"]):
        conn.close()
        raise HTTPException(status_code=401, detail="invalid username or password")
    if user_row["is_active"] != 1:
        conn.close()
        raise HTTPException(status_code=403, detail="user disabled")
    session = _create_session(conn, user_row["id"])
    conn.commit()
    conn.close()
    return {"user": _serialize_user(user_row), "session": _session_payload(session)}


@router.post("/v1/auth/refresh")
def refresh_session(req: RefreshRequest) -> dict[str, Any]:
    conn = db()
    row = conn.execute(
        """
        SELECT s.id,s.user_id,s.refresh_expires_at,s.revoked_at,u.id as u_id,u.username,u.display_name,u.created_at,u.is_active
        FROM auth_sessions s
        JOIN users u ON u.id=s.user_id
        WHERE s.refresh_token_hash=?
        """,
        (_token_hash(req.refreshToken),),
    ).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(status_code=401, detail="invalid refresh token")
    if row["revoked_at"] is not None:
        conn.close()
        raise HTTPException(status_code=401, detail="session revoked")
    if row["is_active"] != 1:
        conn.close()
        raise HTTPException(status_code=403, detail="user disabled")
    if datetime.fromisoformat(row["refresh_expires_at"]) <= _utc_now():
        conn.close()
        raise HTTPException(status_code=401, detail="refresh token expired")
    conn.execute("UPDATE auth_sessions SET revoked_at=?, updated_at=? WHERE id=?", (now_iso(), now_iso(), row["id"]))
    session = _create_session(conn, row["user_id"])
    conn.commit()
    user = {
        "id": row["u_id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "created_at": row["created_at"],
    }
    conn.close()
    return {"user": _serialize_user(user), "session": _session_payload(session)}


@router.post("/v1/auth/logout")
def logout(current_user: dict[str, Any] = Depends(_get_current_user)) -> dict[str, bool]:
    conn = db()
    conn.execute(
        "UPDATE auth_sessions SET revoked_at=?, updated_at=? WHERE id=?",
        (now_iso(), now_iso(), current_user["session_id"]),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@router.get("/v1/me")
def get_me(current_user: dict[str, Any] = Depends(_get_current_user)) -> dict[str, Any]:
    conn = db()
    quota = _quota_snapshot(conn, current_user["id"])
    conn.close()
    return {"user": {
        "userId": current_user["id"],
        "username": current_user["username"],
        "displayName": current_user["display_name"],
        "createdAt": current_user["created_at"],
    }, "quota": quota}


@router.patch("/v1/me/profile")
def update_profile(req: ProfileUpdateRequest, current_user: dict[str, Any] = Depends(_get_current_user)) -> dict[str, Any]:
    display_name = req.displayName.strip()
    conn = db()
    conn.execute(
        "UPDATE users SET display_name=?, updated_at=? WHERE id=?",
        (display_name, now_iso(), current_user["id"]),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM users WHERE id=?", (current_user["id"],)).fetchone()
    conn.close()
    assert row is not None
    return {"user": _serialize_user(row)}


@router.post("/v1/me/change-password")
def change_password(req: ChangePasswordRequest, current_user: dict[str, Any] = Depends(_get_current_user)) -> dict[str, bool]:
    conn = db()
    row = conn.execute("SELECT password_hash FROM users WHERE id=?", (current_user["id"],)).fetchone()
    if row is None or not _password_verify(req.currentPassword, row["password_hash"]):
        conn.close()
        raise HTTPException(status_code=401, detail="current password is incorrect")
    conn.execute(
        "UPDATE users SET password_hash=?, updated_at=? WHERE id=?",
        (_password_hash(req.newPassword), now_iso(), current_user["id"]),
    )
    conn.execute(
        "UPDATE auth_sessions SET revoked_at=?, updated_at=? WHERE user_id=?",
        (now_iso(), now_iso(), current_user["id"]),
    )
    conn.commit()
    conn.close()
    return {"ok": True}
