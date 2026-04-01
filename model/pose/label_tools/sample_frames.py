from __future__ import annotations

import argparse
import hashlib
import json
import logging
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from server.barbell import BarbellTrajectoryDetector, default_model_path
from server.barbell.vbt import compute_vbt_from_barbell


LOG = logging.getLogger("pose.sample_frames")

VIDEO_SUFFIXES = {".mp4", ".mov"}
DEFAULT_SAMPLE_TYPES = ["v_min", "bottom", "dvdt_max", "setup", "random"]
DEFAULT_TYPE_PRIORITY = {"v_min": 5, "bottom": 4, "dvdt_max": 3, "setup": 2, "random": 1}


@dataclass
class SeriesPoint:
    frame_index: int
    time_ms: int
    x: float
    y: float
    signed_velocity: float
    speed: float
    acceleration: float


@dataclass
class CandidateFrame:
    rep_id: int
    frame_index: int
    time_ms: int
    sample_type: str
    priority: int
    x: float
    y: float
    velocity: float
    acceleration: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="VBT-driven keyframe sampler for pose labeling.")
    parser.add_argument("--input-dir", required=True, help="Input video directory (mp4/mov).")
    parser.add_argument("--output-dir", required=True, help="Output directory for sampled frames and metadata.")
    parser.add_argument("--model-path", default=default_model_path(), help="YOLO model path for barbell detection.")
    parser.add_argument("--device", default="cpu", help="Inference device for ultralytics YOLO.")
    parser.add_argument("--sample-fps", type=float, default=30.0, help="Sampling FPS for barbell trajectory detection.")
    parser.add_argument("--max-frames-per-video", type=int, default=30, help="Max sampled frames to keep per video.")
    parser.add_argument("--min-gap-frames", type=int, default=10, help="Minimum frame distance between sampled frames in the same rep.")
    parser.add_argument("--setup-offset-frames", type=int, default=8, help="How many frames before concentric start to sample setup.")
    parser.add_argument("--seed", type=int, default=7, help="Random seed for deterministic random-frame picks.")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    input_dir = Path(args.input_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    frames_dir = output_dir / "frames"
    meta_dir = output_dir / "metadata"

    if not input_dir.exists() or not input_dir.is_dir():
        raise SystemExit(f"input_dir does not exist or is not a directory: {input_dir}")

    frames_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)

    detector = BarbellTrajectoryDetector(
        model_path=args.model_path,
        device=args.device,
    )

    manifest: list[dict[str, Any]] = []
    for video_path in sorted(input_dir.iterdir(), key=lambda p: p.name.lower()):
        if not video_path.is_file() or video_path.suffix.lower() not in VIDEO_SUFFIXES:
            continue
        try:
            entries = sample_video(
                detector=detector,
                video_path=video_path,
                frames_dir=frames_dir,
                meta_dir=meta_dir,
                sample_fps=float(args.sample_fps),
                max_frames_per_video=int(args.max_frames_per_video),
                min_gap_frames=int(args.min_gap_frames),
                setup_offset_frames=int(args.setup_offset_frames),
                seed=int(args.seed),
            )
            manifest.extend(entries)
            LOG.info("sample_video_done path=%s sampled=%s", video_path, len(entries))
        except Exception as exc:  # pragma: no cover - CLI fail-fast logging
            LOG.exception("sample_video_failed path=%s error=%s", video_path, exc)

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps({"samples": manifest}, ensure_ascii=False, indent=2), encoding="utf-8")
    LOG.info("sampling_done videos=%s samples=%s manifest=%s", len({m['video'] for m in manifest}), len(manifest), manifest_path)


def sample_video(
    *,
    detector: BarbellTrajectoryDetector,
    video_path: Path,
    frames_dir: Path,
    meta_dir: Path,
    sample_fps: float,
    max_frames_per_video: int,
    min_gap_frames: int,
    setup_offset_frames: int,
    seed: int,
) -> list[dict[str, Any]]:
    barbell_result = detector.detect_video(str(video_path), sample_fps=sample_fps)
    vbt_result = compute_vbt_from_barbell(barbell_result)
    if not vbt_result or not vbt_result.get("reps"):
        LOG.warning("no_vbt_reps path=%s", video_path)
        return []

    anchor = "plate" if vbt_result.get("motionSource") == "plate" else "end"
    series = build_series(barbell_result=barbell_result, anchor=anchor)
    if len(series) < 8:
        LOG.warning("insufficient_series path=%s anchor=%s", video_path, anchor)
        return []

    rep_candidates = build_rep_candidates(
        video_path=video_path,
        reps=vbt_result["reps"],
        series=series,
        min_gap_frames=min_gap_frames,
        setup_offset_frames=setup_offset_frames,
        seed=seed,
    )
    kept_candidates = apply_video_diversity_limit(
        per_rep=rep_candidates,
        max_frames_per_video=max_frames_per_video,
    )

    return save_candidates(
        video_path=video_path,
        candidates=kept_candidates,
        frames_dir=frames_dir,
        meta_dir=meta_dir,
    )


def build_series(*, barbell_result: dict[str, Any], anchor: str) -> list[SeriesPoint]:
    raw_frames = barbell_result.get("frames") or []
    points: list[dict[str, Any]] = []
    for frame in raw_frames:
        if not isinstance(frame, dict):
            continue
        node = frame.get(anchor)
        if not isinstance(node, dict):
            continue
        center = node.get("center")
        if not isinstance(center, dict):
            continue
        x = center.get("x")
        y = center.get("y")
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            continue
        frame_index = frame.get("frameIndex")
        time_ms = frame.get("timeMs")
        if not isinstance(frame_index, (int, float)) or not isinstance(time_ms, (int, float)):
            continue
        points.append(
            {
                "frame_index": int(frame_index),
                "time_ms": int(time_ms),
                "x": float(x),
                "y": float(y),
            }
        )

    if len(points) < 3:
        return []

    smooth_x = moving_average([p["x"] for p in points], window=5)
    smooth_y = moving_average([p["y"] for p in points], window=5)

    series: list[SeriesPoint] = []
    for idx, point in enumerate(points):
        prev_i = max(0, idx - 1)
        next_i = min(len(points) - 1, idx + 1)
        dt_ms = max(1, points[next_i]["time_ms"] - points[prev_i]["time_ms"])
        dt_s = dt_ms / 1000.0
        dx = smooth_x[next_i] - smooth_x[prev_i]
        dy = smooth_y[next_i] - smooth_y[prev_i]
        signed_velocity = dy / dt_s
        speed = ((dx * dx + dy * dy) ** 0.5) / dt_s

        if series:
            prev_series = series[-1]
            prev_dt_s = max(1e-6, (point["time_ms"] - prev_series.time_ms) / 1000.0)
            acceleration = (signed_velocity - prev_series.signed_velocity) / prev_dt_s
        else:
            acceleration = 0.0

        series.append(
            SeriesPoint(
                frame_index=point["frame_index"],
                time_ms=point["time_ms"],
                x=smooth_x[idx],
                y=smooth_y[idx],
                signed_velocity=signed_velocity,
                speed=speed,
                acceleration=acceleration,
            )
        )
    return series


def moving_average(values: list[float], *, window: int) -> list[float]:
    if window <= 1 or len(values) <= 2:
        return values[:]
    half = window // 2
    out: list[float] = []
    for i in range(len(values)):
        lo = max(0, i - half)
        hi = min(len(values), i + half + 1)
        out.append(sum(values[lo:hi]) / max(1, hi - lo))
    return out


def build_rep_candidates(
    *,
    video_path: Path,
    reps: list[dict[str, Any]],
    series: list[SeriesPoint],
    min_gap_frames: int,
    setup_offset_frames: int,
    seed: int,
) -> dict[int, list[CandidateFrame]]:
    by_rep: dict[int, list[CandidateFrame]] = {}
    rnd = random.Random(_stable_seed(video_path.name, seed))

    for rep in reps:
        rep_id = int(rep.get("repIndex", 0))
        time_range = rep.get("timeRangeMs") or {}
        start_ms = int(time_range.get("start", 0))
        end_ms = int(time_range.get("end", 0))
        rep_points = [p for p in series if start_ms <= p.time_ms <= end_ms]
        if not rep_points:
            continue

        bottom = max(rep_points, key=lambda p: p.y)
        ascent_points = [p for p in rep_points if p.time_ms >= bottom.time_ms]
        positive_upward = [p for p in ascent_points if (-p.signed_velocity) > 1e-6]
        if positive_upward:
            v_min_point = min(positive_upward, key=lambda p: (-p.signed_velocity))
        else:
            v_min_point = min(ascent_points, key=lambda p: abs(p.signed_velocity))

        dvdt_point = max(rep_points, key=lambda p: abs(p.acceleration))
        setup_point = pick_setup_point(series=series, start_ms=start_ms, setup_offset_frames=setup_offset_frames)
        random_point = rnd.choice(rep_points)

        candidates = [
            make_candidate(rep_id=rep_id, point=v_min_point, sample_type="v_min"),
            make_candidate(rep_id=rep_id, point=bottom, sample_type="bottom"),
            make_candidate(rep_id=rep_id, point=dvdt_point, sample_type="dvdt_max"),
            make_candidate(rep_id=rep_id, point=setup_point, sample_type="setup"),
            make_candidate(rep_id=rep_id, point=random_point, sample_type="random"),
        ]

        by_rep[rep_id] = dedupe_candidates(candidates, min_gap_frames=min_gap_frames)

    return by_rep


def pick_setup_point(*, series: list[SeriesPoint], start_ms: int, setup_offset_frames: int) -> SeriesPoint:
    before = [p for p in series if p.time_ms < start_ms]
    if not before:
        return min(series, key=lambda p: abs(p.time_ms - start_ms))
    idx = max(0, len(before) - 1 - max(0, setup_offset_frames))
    return before[idx]


def make_candidate(*, rep_id: int, point: SeriesPoint, sample_type: str) -> CandidateFrame:
    return CandidateFrame(
        rep_id=rep_id,
        frame_index=point.frame_index,
        time_ms=point.time_ms,
        sample_type=sample_type,
        priority=DEFAULT_TYPE_PRIORITY[sample_type],
        x=point.x,
        y=point.y,
        velocity=point.signed_velocity,
        acceleration=point.acceleration,
    )


def dedupe_candidates(candidates: list[CandidateFrame], *, min_gap_frames: int) -> list[CandidateFrame]:
    kept: list[CandidateFrame] = []
    for candidate in sorted(candidates, key=lambda c: (-c.priority, c.frame_index)):
        if any(abs(candidate.frame_index - existing.frame_index) < min_gap_frames for existing in kept):
            continue
        kept.append(candidate)
    kept.sort(key=lambda c: c.frame_index)
    return kept


def apply_video_diversity_limit(*, per_rep: dict[int, list[CandidateFrame]], max_frames_per_video: int) -> list[CandidateFrame]:
    if max_frames_per_video <= 0:
        return []

    rep_ids = sorted(per_rep.keys())
    if not rep_ids:
        return []

    max_reps = max(1, max_frames_per_video // len(DEFAULT_SAMPLE_TYPES))
    if len(rep_ids) > max_reps:
        rep_ids = evenly_pick(rep_ids, max_reps)

    kept: list[CandidateFrame] = []
    for rep_id in rep_ids:
        kept.extend(per_rep.get(rep_id, []))

    if len(kept) <= max_frames_per_video:
        return kept

    ranked = sorted(kept, key=lambda c: (-c.priority, c.rep_id, c.frame_index))
    return sorted(ranked[:max_frames_per_video], key=lambda c: (c.rep_id, c.frame_index))


def evenly_pick(items: list[int], count: int) -> list[int]:
    if count >= len(items):
        return items[:]
    if count <= 1:
        return [items[0]]
    step = (len(items) - 1) / float(count - 1)
    out = []
    seen = set()
    for i in range(count):
        item = items[round(i * step)]
        if item not in seen:
            out.append(item)
            seen.add(item)
    return out


def save_candidates(
    *,
    video_path: Path,
    candidates: list[CandidateFrame],
    frames_dir: Path,
    meta_dir: Path,
) -> list[dict[str, Any]]:
    if not candidates:
        return []

    try:
        import cv2  # type: ignore
    except Exception as exc:  # pragma: no cover - runtime dependency error
        raise RuntimeError("opencv-python-headless is required for frame export.") from exc

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video for frame export: {video_path}")

    manifest_entries: list[dict[str, Any]] = []
    try:
        for candidate in candidates:
            cap.set(cv2.CAP_PROP_POS_FRAMES, float(candidate.frame_index))
            ok, frame = cap.read()
            if not ok or frame is None:
                LOG.warning("frame_read_failed video=%s frame=%s", video_path, candidate.frame_index)
                continue

            image_name = f"{video_path.stem}_rep{candidate.rep_id:02d}_{candidate.sample_type}.jpg"
            image_path = frames_dir / image_name
            meta_path = meta_dir / f"{video_path.stem}_rep{candidate.rep_id:02d}_{candidate.sample_type}.json"

            if not cv2.imwrite(str(image_path), frame):
                LOG.warning("frame_write_failed path=%s", image_path)
                continue

            meta = {
                "video": video_path.name,
                "rep_id": candidate.rep_id,
                "frame_index": candidate.frame_index,
                "type": candidate.sample_type,
                "time": round(candidate.time_ms / 1000.0, 3),
                "time_ms": candidate.time_ms,
                "bar_x": round(candidate.x, 3),
                "bar_y": round(candidate.y, 3),
                "velocity": round(candidate.velocity, 6),
                "acceleration": round(candidate.acceleration, 6),
                "image_file": image_name,
            }
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            manifest_entries.append(meta)
    finally:
        cap.release()

    return manifest_entries


def _stable_seed(name: str, seed: int) -> int:
    digest = hashlib.sha256(f"{name}:{seed}".encode("utf-8")).hexdigest()[:12]
    return int(digest, 16)


if __name__ == "__main__":
    main()
