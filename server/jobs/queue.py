from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass
class JobWork:
    job_id: str


_job_queue: list[JobWork] = []
_job_lock = threading.Lock()


def enqueue_job(job_id: str) -> None:
    with _job_lock:
        _job_queue.append(JobWork(job_id=job_id))


def pop_job() -> JobWork | None:
    with _job_lock:
        if not _job_queue:
            return None
        return _job_queue.pop(0)
