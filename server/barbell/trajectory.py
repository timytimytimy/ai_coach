from __future__ import annotations

import logging
import os
from typing import Any

from server.barbell.paths import default_model_path
from server.barbell.tracking import EndTracker, PlateTracker, _TrackState
from server.barbell.types import DetectedBox, Point2D


_LOG = logging.getLogger("ssc.barbell")


class BarbellTrajectoryDetector:
    def __init__(
        self,
        model_path: str,
        *,
        device: str = "cpu",
        imgsz: int = 640,
        conf: float = 0.25,
        iou: float = 0.5,
    ) -> None:
        self.model_path = model_path
        self.device = device
        self.imgsz = imgsz
        self.conf = conf
        self.iou = iou
        self._model: Any | None = None

    def _load(self) -> Any:
        if self._model is not None:
            return self._model

        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"YOLO model not found: {self.model_path}")

        try:
            from ultralytics import YOLO  # type: ignore
        except Exception as e:
            raise RuntimeError(
                "ultralytics not installed. Add it to requirements and install dependencies."
            ) from e

        self._model = YOLO(self.model_path)
        _LOG.info(
            "yolo_loaded modelPath=%s device=%s imgsz=%s conf=%.3f iou=%.3f",
            self.model_path,
            self.device,
            self.imgsz,
            self.conf,
            self.iou,
        )
        return self._model

    def detect_video(
        self,
        video_path: str,
        *,
        sample_fps: float = 6.0,
        max_frames: int | None = None,
        batch_size: int = 8,
    ) -> dict[str, Any]:
        _LOG.info(
            "detect_video_start path=%s sampleFps=%.2f maxFrames=%s batchSize=%s",
            video_path,
            sample_fps,
            max_frames,
            batch_size,
        )
        try:
            import cv2  # type: ignore
        except Exception as e:
            raise RuntimeError(
                "opencv not installed. Add opencv-python-headless to requirements and install dependencies."
            ) from e

        model = self._load()

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError(f"cannot open video: {video_path}")

        src_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        if src_fps <= 0:
            src_fps = 30.0

        if sample_fps <= 0:
            sample_fps = src_fps

        step = max(1, int(round(src_fps / sample_fps)))

        plate = PlateTracker(state=_TrackState(pos=None, vel=Point2D(0.0, 0.0), miss=0))
        end = EndTracker(state=_TrackState(pos=None, vel=Point2D(0.0, 0.0), miss=0))

        frames: list[dict[str, Any]] = []
        frame_w = 0
        frame_h = 0

        idx = 0
        kept = 0

        batch_size = max(1, int(batch_size))
        pending_idx: list[int] = []
        pending_rgb: list[Any] = []

        def flush_pending() -> None:
            nonlocal frame_w, frame_h
            if not pending_rgb:
                return

            results = model.predict(
                source=pending_rgb,
                verbose=False,
                device=self.device,
                imgsz=self.imgsz,
                conf=self.conf,
                iou=self.iou,
                stream=False,
            )

            for frame_idx_val, r0 in zip(pending_idx, results):
                dets: list[DetectedBox] = []
                if getattr(r0, "boxes", None) is not None and len(r0.boxes) > 0:
                    for b in r0.boxes:
                        cls = int(b.cls.item())
                        conf = float(b.conf.item())
                        x1, y1, x2, y2 = [float(v) for v in b.xyxy[0].tolist()]
                        dets.append(DetectedBox(cls=cls, conf=conf, xyxy=(x1, y1, x2, y2)))

                diag = (frame_w * frame_w + frame_h * frame_h) ** 0.5
                dt = step / src_fps
                if dt <= 0:
                    dt = 1.0 / max(1.0, src_fps)

                best_plate, plate_pos, plate_bbox = _unpack_step(
                    plate.step(dets=dets, w=frame_w, h=frame_h, diag=diag, dt=dt)
                )

                plate_wh: tuple[float, float] | None = None
                if plate_bbox is not None:
                    plate_wh = (
                        max(1.0, plate_bbox[2] - plate_bbox[0]),
                        max(1.0, plate_bbox[3] - plate_bbox[1]),
                    )
                elif best_plate is not None:
                    plate_wh = (max(1.0, best_plate.width), max(1.0, best_plate.height))

                best_end, end_pos, end_bbox = _unpack_step(
                    end.step(
                        dets=dets,
                        w=frame_w,
                        h=frame_h,
                        diag=diag,
                        dt=dt,
                        plate_center=plate_pos,
                        plate_wh=plate_wh,
                    )
                )

                t_ms = int(round((frame_idx_val / src_fps) * 1000.0))
                frames.append(
                    {
                        "frameIndex": frame_idx_val,
                        "timeMs": t_ms,
                        "plate": _pack(best_plate, plate_pos, plate_bbox),
                        "end": _pack(best_end, end_pos, end_bbox),
                    }
                )

            pending_idx.clear()
            pending_rgb.clear()

        while True:
            if idx % step != 0:
                ok = cap.grab()
                if not ok:
                    break
                idx += 1
                continue

            ok, frame_bgr = cap.read()
            if not ok:
                break

            kept += 1
            if max_frames is not None and kept > max_frames:
                break

            h, w = frame_bgr.shape[:2]
            if frame_w == 0:
                frame_w = int(w)
                frame_h = int(h)

            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            pending_idx.append(idx)
            pending_rgb.append(frame_rgb)
            if len(pending_rgb) >= batch_size:
                flush_pending()

            idx += 1

        flush_pending()
        cap.release()

        _LOG.info(
            "detect_video_done path=%s kept=%s frame=%sx%s sourceFps=%.3f step=%s sampleFps=%.3f",
            video_path,
            kept,
            frame_w,
            frame_h,
            src_fps,
            step,
            min(sample_fps, src_fps),
        )

        return {
            "modelPath": self.model_path,
            "videoPath": video_path,
            "sourceFps": src_fps,
            "sampleFps": min(sample_fps, src_fps),
            "step": step,
            "frameWidth": frame_w,
            "frameHeight": frame_h,
            "frames": frames,
            "classMap": {"end": 0, "plate": 1},
            "note": "Coordinates are in OpenCV-decoded frame pixels (origin top-left, x right, y down); some videos have rotation metadata that browsers apply but OpenCV does not.",
        }


def _unpack_step(res: Any) -> tuple[DetectedBox | None, Point2D | None, tuple[float, float, float, float] | None]:
    if not isinstance(res, tuple):
        return None, None, None
    if len(res) == 2:
        det, pos = res
        return det, pos, None
    if len(res) >= 3:
        det, pos, bbox = res[0], res[1], res[2]
        return det, pos, bbox
    return None, None, None


def _pack(
    det: DetectedBox | None,
    pos: Point2D | None,
    bbox: tuple[float, float, float, float] | None,
) -> dict[str, Any] | None:
    if pos is None:
        return None

    payload: dict[str, Any] = {
        "conf": (det.conf if det is not None else 0.0),
        "center": {"x": pos.x, "y": pos.y},
        "bbox": None,
        "tracked": det is None,
    }
    if det is not None:
        payload["class"] = det.cls

    if bbox is None:
        if det is None:
            return payload
        x1, y1, x2, y2 = det.xyxy
        payload["bbox"] = {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
        return payload

    x1, y1, x2, y2 = bbox
    payload["bbox"] = {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
    return payload


def default_detector() -> BarbellTrajectoryDetector:
    return BarbellTrajectoryDetector(model_path=default_model_path())
