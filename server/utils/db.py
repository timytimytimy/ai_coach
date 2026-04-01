from __future__ import annotations

import logging
import os
import shutil
import sqlite3
from datetime import datetime, timezone

from server.utils.config import DB_PATH, VIDEO_DIR
from server.utils.config import DEFAULT_USER_REMAINING_QUOTA

_LOG = logging.getLogger("ssc")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    if not column_exists(conn, table, column):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def ensure_video_dir() -> str:
    path = os.path.abspath(VIDEO_DIR)
    os.makedirs(path, exist_ok=True)
    return path


def _legacy_db_path() -> str:
    return os.path.join(os.path.dirname(__file__), "app.db")


def _legacy_video_dir() -> str:
    return os.path.join(os.path.dirname(__file__), "videos")


def _server_legacy_video_dir() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "videos")


def _table_count(path: str, table: str) -> int:
    if not os.path.exists(path):
        return -1
    conn = sqlite3.connect(path)
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        if row is None or int(row[0]) == 0:
            return -1
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    finally:
        conn.close()


def _migrate_legacy_db_if_needed() -> None:
    canonical = os.path.abspath(DB_PATH)
    legacy = os.path.abspath(_legacy_db_path())
    if canonical == legacy or not os.path.exists(legacy):
        return

    os.makedirs(os.path.dirname(canonical), exist_ok=True)
    if not os.path.exists(canonical):
        shutil.move(legacy, canonical)
        _LOG.info("migrated_db_from_legacy src=%s dst=%s", legacy, canonical)
        return

    canonical_users = _table_count(canonical, "users")
    legacy_users = _table_count(legacy, "users")
    if legacy_users > canonical_users:
        backup = f"{canonical}.bak"
        shutil.move(canonical, backup)
        shutil.move(legacy, canonical)
        _LOG.warning(
            "replaced_canonical_db_with_legacy src=%s dst=%s backup=%s canonicalUsers=%s legacyUsers=%s",
            legacy,
            canonical,
            backup,
            canonical_users,
            legacy_users,
        )
        return

    if legacy_users <= 0:
        return

    canonical_conn = sqlite3.connect(canonical)
    legacy_conn = sqlite3.connect(legacy)
    canonical_conn.row_factory = sqlite3.Row
    legacy_conn.row_factory = sqlite3.Row
    try:
        tables = [
            "users",
            "auth_sessions",
            "user_usage_daily",
            "videos",
            "workouts",
            "sets",
            "analysis_jobs",
            "reports",
            "barbell_cache",
            "pose_cache",
            "llm_cache",
            "llm_usage_logs",
            "lift_classification_cache",
        ]
        copied = 0
        for table in tables:
            exists = legacy_conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()[0]
            if not exists:
                continue
            canonical_columns = [row["name"] for row in canonical_conn.execute(f"PRAGMA table_info({table})")]
            legacy_columns = [row["name"] for row in legacy_conn.execute(f"PRAGMA table_info({table})")]
            columns = [column for column in canonical_columns if column in legacy_columns]
            if not columns:
                continue
            rows = legacy_conn.execute(f"SELECT {','.join(columns)} FROM {table}").fetchall()
            if not rows:
                continue
            placeholders = ",".join("?" for _ in columns)
            canonical_conn.executemany(
                f"INSERT OR IGNORE INTO {table}({','.join(columns)}) VALUES ({placeholders})",
                [tuple(row[col] for col in columns) for row in rows],
            )
            copied += len(rows)
        if copied:
            canonical_conn.commit()
            _LOG.info("merged_legacy_db_rows src=%s dst=%s rows=%s", legacy, canonical, copied)
    finally:
        canonical_conn.close()
        legacy_conn.close()


def _migrate_legacy_video_dir_if_needed() -> None:
    canonical = os.path.abspath(VIDEO_DIR)
    os.makedirs(canonical, exist_ok=True)
    for legacy_path in {_legacy_video_dir(), _server_legacy_video_dir()}:
        legacy = os.path.abspath(legacy_path)
        if canonical == legacy or not os.path.isdir(legacy):
            continue
        moved = 0
        for name in os.listdir(legacy):
            src = os.path.join(legacy, name)
            dst = os.path.join(canonical, name)
            if not os.path.isfile(src) or os.path.exists(dst):
                continue
            shutil.move(src, dst)
            moved += 1
        if moved:
            _LOG.info("migrated_upload_files_from_legacy src=%s dst=%s moved=%s", legacy, canonical, moved)
        try:
            if not os.listdir(legacy):
                os.rmdir(legacy)
        except OSError:
            pass


def init_db() -> None:
    _migrate_legacy_db_if_needed()
    _migrate_legacy_video_dir_if_needed()
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

        CREATE TABLE IF NOT EXISTS lift_classification_cache(
          video_sha256 TEXT NOT NULL,
          cache_key TEXT NOT NULL,
          result_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          PRIMARY KEY(video_sha256, cache_key)
        );

        CREATE TABLE IF NOT EXISTS users(
          id TEXT PRIMARY KEY,
          username TEXT NOT NULL UNIQUE,
          password_hash TEXT NOT NULL,
          display_name TEXT NOT NULL,
          remaining_quota INTEGER NOT NULL DEFAULT 20,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          is_active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS auth_sessions(
          id TEXT PRIMARY KEY,
          user_id TEXT NOT NULL,
          access_token_hash TEXT NOT NULL UNIQUE,
          refresh_token_hash TEXT NOT NULL UNIQUE,
          access_expires_at TEXT NOT NULL,
          refresh_expires_at TEXT NOT NULL,
          revoked_at TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS user_usage_daily(
          user_id TEXT NOT NULL,
          day TEXT NOT NULL,
          uploads_used INTEGER NOT NULL DEFAULT 0,
          analyses_used INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          PRIMARY KEY(user_id, day)
        );
        """
    )
    ensure_column(
        conn,
        "users",
        "remaining_quota",
        f"remaining_quota INTEGER NOT NULL DEFAULT {DEFAULT_USER_REMAINING_QUOTA}",
    )
    conn.execute(
        "UPDATE users SET remaining_quota=? WHERE remaining_quota IS NULL",
        (DEFAULT_USER_REMAINING_QUOTA,),
    )
    ensure_column(conn, "videos", "user_id", "user_id TEXT")
    ensure_column(conn, "workouts", "user_id", "user_id TEXT")
    ensure_column(conn, "sets", "user_id", "user_id TEXT")
    ensure_column(conn, "analysis_jobs", "user_id", "user_id TEXT")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions(user_id)"
    )
    conn.commit()
    conn.close()
