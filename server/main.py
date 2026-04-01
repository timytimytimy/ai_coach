from __future__ import annotations

import logging
import os
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.utils.config import DB_PATH, VIDEO_DIR
from server.utils.db import init_db
from server.jobs import job_worker_loop, runtime_summary
from server.utils.logging_utils import setup_logging as _setup_logging
from server.routes import analysis_router, auth_router, videos_router, workouts_router

_LOG = logging.getLogger("ssc")

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
    runtime = runtime_summary(
        os.environ.get("SSC_LLM_MODEL") or os.environ.get("OPENAI_MODEL") or "gemini-3-pro-preview-new"
    )
    _LOG.info(
        "runtime poseImpl=%s yoloDevice=%s rtmposeBackend=%s rtmposeDevice=%s mediapipeDevice=%s mediapipeNote=%s llmModel=%s llmVideoInput=%s",
        runtime["poseImpl"],
        runtime["yoloDevice"],
        runtime["rtmposeBackend"],
        runtime["rtmposeDevice"],
        runtime["mediapipeDevice"],
        runtime["mediapipeNote"],
        runtime["llmModel"],
        runtime["llmVideoInput"],
    )
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


app.include_router(auth_router)
app.include_router(videos_router)
app.include_router(workouts_router)
app.include_router(analysis_router)
