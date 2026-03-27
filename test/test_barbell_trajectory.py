from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from typing import Any

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from server.barbell_trajectory import BarbellTrajectoryDetector, default_model_path


def _count_present(frames: list[dict[str, Any]], key: str) -> int:
    n = 0
    for f in frames:
        if f.get(key) is not None:
            n += 1
    return n


def _write_csv(path: str, frames: list[dict[str, Any]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fp:
        w = csv.writer(fp)
        w.writerow(
            [
                "frameIndex",
                "timeMs",
                "endConf",
                "endX",
                "endY",
                "plateConf",
                "plateX",
                "plateY",
            ]
        )
        for f in frames:
            end = f.get("end") or {}
            plate = f.get("plate") or {}
            end_center = end.get("center") or {}
            plate_center = plate.get("center") or {}
            w.writerow(
                [
                    f.get("frameIndex"),
                    f.get("timeMs"),
                    end.get("conf"),
                    end_center.get("x"),
                    end_center.get("y"),
                    plate.get("conf"),
                    plate_center.get("x"),
                    plate_center.get("y"),
                ]
            )


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="test_barbell_trajectory")
    p.add_argument("video", help="Path to a local video file")
    p.add_argument(
        "--model",
        default=os.environ.get("SSC_YOLO_MODEL_PATH") or default_model_path(),
        help="Path to YOLOv8 .pt (default: SSC_YOLO_MODEL_PATH or ./model/best.pt)",
    )
    p.add_argument("--sample-fps", type=float, default=6.0)
    p.add_argument("--max-frames", type=int, default=None)
    p.add_argument("--out-json", default=None, help="Write full detection output JSON")
    p.add_argument("--out-csv", default=None, help="Write per-frame centers CSV")

    args = p.parse_args(argv)

    video_path = os.path.abspath(args.video)
    model_path = os.path.abspath(args.model)

    if not os.path.exists(video_path):
        print(f"video not found: {video_path}", file=sys.stderr)
        return 2

    if not os.path.exists(model_path):
        print(f"model not found: {model_path}", file=sys.stderr)
        return 2

    det = BarbellTrajectoryDetector(model_path=model_path)
    result = det.detect_video(video_path, sample_fps=float(args.sample_fps), max_frames=args.max_frames)

    frames = result.get("frames") or []
    n_frames = len(frames)
    n_end = _count_present(frames, "end")
    n_plate = _count_present(frames, "plate")

    print("OK")
    print(f"model: {result.get('modelPath')}")
    print(f"video: {result.get('videoPath')}")
    print(
        f"sourceFps: {result.get('sourceFps')} sampleFps: {result.get('sampleFps')} step: {result.get('step')}"
    )
    print(f"frames: {n_frames}  end_present: {n_end}  plate_present: {n_plate}")

    for f in frames[:5]:
        end = f.get("end")
        plate = f.get("plate")
        print(
            json.dumps(
                {
                    "frameIndex": f.get("frameIndex"),
                    "timeMs": f.get("timeMs"),
                    "end": end.get("center") if isinstance(end, dict) else None,
                    "plate": plate.get("center") if isinstance(plate, dict) else None,
                },
                ensure_ascii=False,
            )
        )

    if args.out_json:
        out_path = os.path.abspath(args.out_json)
        with open(out_path, "w", encoding="utf-8") as fp:
            json.dump(result, fp, ensure_ascii=False)
        print(f"wrote: {out_path}")

    if args.out_csv:
        out_path = os.path.abspath(args.out_csv)
        _write_csv(out_path, frames)
        print(f"wrote: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))