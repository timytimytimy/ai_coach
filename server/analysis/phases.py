from __future__ import annotations

from typing import Any


def segment_phases(
    *,
    exercise: str,
    overlay_result: dict[str, Any] | None,
    vbt_result: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    reps = vbt_result.get("reps") if isinstance(vbt_result, dict) else None
    if not isinstance(reps, list):
        return []

    out: list[dict[str, Any]] = []
    for rep in reps:
        if not isinstance(rep, dict):
            continue
        tr = rep.get("timeRangeMs")
        if not isinstance(tr, dict):
            continue
        start = tr.get("start")
        end = tr.get("end")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            continue
        start_ms = int(start)
        end_ms = int(end)
        if end_ms <= start_ms:
            continue
        duration = end_ms - start_ms
        bottom_ms = start_ms
        ascent_end = end_ms
        lockout_end = end_ms + min(250, max(80, duration // 5))
        descent_start = max(0, start_ms - min(700, max(120, duration // 2)))

        if exercise == "bench":
            out.extend(
                [
                    {"name": "descent", "repIndex": rep.get("repIndex"), "startMs": descent_start, "endMs": bottom_ms},
                    {"name": "chest_touch", "repIndex": rep.get("repIndex"), "startMs": bottom_ms, "endMs": min(ascent_end, bottom_ms + max(60, duration // 8))},
                    {"name": "press", "repIndex": rep.get("repIndex"), "startMs": bottom_ms, "endMs": ascent_end},
                    {"name": "lockout", "repIndex": rep.get("repIndex"), "startMs": ascent_end, "endMs": lockout_end},
                ]
            )
        elif exercise == "deadlift":
            out.extend(
                [
                    {"name": "slack_pull", "repIndex": rep.get("repIndex"), "startMs": max(0, start_ms - 180), "endMs": start_ms},
                    {"name": "floor_break", "repIndex": rep.get("repIndex"), "startMs": start_ms, "endMs": start_ms + max(80, duration // 4)},
                    {"name": "knee_pass", "repIndex": rep.get("repIndex"), "startMs": start_ms + max(80, duration // 4), "endMs": start_ms + max(140, duration // 2)},
                    {"name": "lockout", "repIndex": rep.get("repIndex"), "startMs": start_ms + max(140, duration // 2), "endMs": ascent_end},
                    {"name": "descent", "repIndex": rep.get("repIndex"), "startMs": ascent_end, "endMs": lockout_end},
                ]
            )
        else:
            out.extend(
                [
                    {"name": "descent", "repIndex": rep.get("repIndex"), "startMs": descent_start, "endMs": bottom_ms},
                    {"name": "bottom", "repIndex": rep.get("repIndex"), "startMs": bottom_ms, "endMs": min(ascent_end, bottom_ms + max(80, duration // 8))},
                    {"name": "ascent", "repIndex": rep.get("repIndex"), "startMs": bottom_ms, "endMs": ascent_end},
                    {"name": "lockout", "repIndex": rep.get("repIndex"), "startMs": ascent_end, "endMs": lockout_end},
                ]
            )
    return out
