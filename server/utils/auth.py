from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import Header, HTTPException

from server.utils.config import ACCESS_TOKEN_TTL_SECONDS, PASSWORD_SALT, REFRESH_TOKEN_TTL_SECONDS
from server.utils.db import db, now_iso


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_after(seconds: int) -> str:
    return (utc_now() + timedelta(seconds=seconds)).isoformat()


def normalize_username(value: str) -> str:
    username = value.strip().lower()
    if not re.fullmatch(r"[a-z0-9_]{3,32}", username):
        raise HTTPException(
            status_code=400,
            detail="username must be 3-32 chars of lowercase letters, numbers, or underscore",
        )
    return username


def password_hash(password: str) -> str:
    iterations = 200_000
    salt = PASSWORD_SALT.encode("utf-8")
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${digest.hex()}"


def password_verify(password: str, stored_hash: str) -> bool:
    try:
        scheme, iterations_text, digest_hex = stored_hash.split("$", 2)
        if scheme != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
    except Exception:
        return False
    computed = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        PASSWORD_SALT.encode("utf-8"),
        iterations,
    ).hex()
    return hmac.compare_digest(computed, digest_hex)


def issue_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def serialize_user(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    return {
        "userId": row["id"],
        "username": row["username"],
        "displayName": row["display_name"],
        "createdAt": row["created_at"],
    }


def quota_snapshot(conn: sqlite3.Connection, user_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT remaining_quota FROM users WHERE id=?",
        (user_id,),
    ).fetchone()
    remaining = int(row["remaining_quota"]) if row is not None else 0
    return {"remaining": max(0, remaining)}


def consume_daily_quota(
    conn: sqlite3.Connection, *, user_id: str, kind: Literal["uploads", "analyses"]
) -> dict[str, Any]:
    row = conn.execute(
        "SELECT remaining_quota FROM users WHERE id=?",
        (user_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="user not found")
    remaining = int(row["remaining_quota"])
    if remaining <= 0:
        action = "upload" if kind == "uploads" else "analysis"
        raise HTTPException(status_code=429, detail=f"{action} quota exceeded")
    conn.execute(
        "UPDATE users SET remaining_quota=?, updated_at=? WHERE id=?",
        (remaining - 1, now_iso(), user_id),
    )
    return quota_snapshot(conn, user_id)


def session_payload(session_row: dict[str, Any]) -> dict[str, Any]:
    return {
        "accessToken": session_row["access_token"],
        "refreshToken": session_row["refresh_token"],
        "accessExpiresAt": session_row["access_expires_at"],
        "refreshExpiresAt": session_row["refresh_expires_at"],
    }


def create_session(conn: sqlite3.Connection, user_id: str) -> dict[str, Any]:
    access_token = issue_token()
    refresh_token = issue_token()
    access_expires_at = iso_after(ACCESS_TOKEN_TTL_SECONDS)
    refresh_expires_at = iso_after(REFRESH_TOKEN_TTL_SECONDS)
    session_id = f"sess_{uuid.uuid4().hex}"
    conn.execute(
        """
        INSERT INTO auth_sessions(
          id,user_id,access_token_hash,refresh_token_hash,access_expires_at,
          refresh_expires_at,created_at,updated_at
        ) VALUES (?,?,?,?,?,?,?,?)
        """,
        (
            session_id,
            user_id,
            token_hash(access_token),
            token_hash(refresh_token),
            access_expires_at,
            refresh_expires_at,
            now_iso(),
            now_iso(),
        ),
    )
    return {
        "id": session_id,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "access_expires_at": access_expires_at,
        "refresh_expires_at": refresh_expires_at,
    }


def parse_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="missing authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="invalid authorization header")
    return token.strip()


def get_session_by_access_token(conn: sqlite3.Connection, token: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT s.id,s.user_id,s.access_expires_at,s.refresh_expires_at,s.revoked_at,
               u.id as u_id,u.username,u.display_name,u.created_at as user_created_at,u.is_active
        FROM auth_sessions s
        JOIN users u ON u.id=s.user_id
        WHERE s.access_token_hash=?
        """,
        (token_hash(token),),
    ).fetchone()


def get_current_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    token = parse_bearer_token(authorization)
    conn = db()
    row = get_session_by_access_token(conn, token)
    if row is None:
        conn.close()
        raise HTTPException(status_code=401, detail="invalid access token")
    if row["revoked_at"] is not None:
        conn.close()
        raise HTTPException(status_code=401, detail="session revoked")
    if row["is_active"] != 1:
        conn.close()
        raise HTTPException(status_code=403, detail="user disabled")
    if datetime.fromisoformat(row["access_expires_at"]) <= utc_now():
        conn.close()
        raise HTTPException(status_code=401, detail="access token expired")
    user = {
        "id": row["u_id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "created_at": row["user_created_at"],
        "session_id": row["id"],
    }
    conn.close()
    return user
