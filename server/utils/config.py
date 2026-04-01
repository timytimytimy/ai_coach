from __future__ import annotations

import os

_UTILS_DIR = os.path.dirname(__file__)
_SERVER_DIR = os.path.dirname(_UTILS_DIR)

DB_PATH = os.environ.get("SSC_DB_PATH", os.path.join(_SERVER_DIR, "app.db"))
VIDEO_DIR = os.environ.get("SSC_VIDEO_DIR", os.path.join(_SERVER_DIR, "upload_files"))
ACCESS_TOKEN_TTL_SECONDS = int(os.environ.get("SSC_AUTH_ACCESS_TTL_SEC", "900"))
REFRESH_TOKEN_TTL_SECONDS = int(os.environ.get("SSC_AUTH_REFRESH_TTL_SEC", str(30 * 24 * 3600)))
PASSWORD_SALT = os.environ.get("SSC_PASSWORD_SALT", "ssc-local-dev-salt")
DEFAULT_USER_REMAINING_QUOTA = int(os.environ.get("SSC_DEFAULT_USER_REMAINING_QUOTA", "20"))


def env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(float(value))
    except ValueError:
        return default
