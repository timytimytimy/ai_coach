from __future__ import annotations

import os


def default_model_path() -> str:
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.join(repo_root, "model", "best.pt")


def find_local_video_path(video_sha256: str) -> str | None:
    if not video_sha256:
        return None

    base_dir = os.environ.get("SSC_VIDEO_DIR")
    if not base_dir:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "videos"))

    base_dir = os.path.abspath(base_dir)
    candidates = [
        os.path.join(base_dir, f"{video_sha256}.mp4"),
        os.path.join(base_dir, f"{video_sha256}.mov"),
        os.path.join(base_dir, f"{video_sha256}.m4v"),
        os.path.join(base_dir, f"{video_sha256}.webm"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None