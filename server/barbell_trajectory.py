from __future__ import annotations

from server.barbell.paths import default_model_path, find_local_video_path
from server.barbell.trajectory import BarbellTrajectoryDetector

__all__ = ["BarbellTrajectoryDetector", "default_model_path", "find_local_video_path"]

if False:
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
        return self._model

    def detect_video(
        self,
        video_path: str,
        *,
        sample_fps: float = 6.0,
        max_frames: int | None = None,
    ) -> dict[str, Any]:
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
        frames: list[dict[str, Any]] = []

        idx = 0
        kept = 0

        last_plate: Point2D | None = None
        last_plate_v = Point2D(0.0, 0.0)
        last_plate_miss = 0
        last_plate_area: float | None = None

        last_end: Point2D | None = None
        last_end_v = Point2D(0.0, 0.0)
        last_end_miss = 0

        frame_w: int = 0
        frame_h: int = 0

        def clamp(v: float, lo: float, hi: float) -> float:
            return lo if v < lo else (hi if v > hi else v)

        def clamp_pt(p: Point2D) -> Point2D:
            return Point2D(clamp(p.x, 0.0, max(0.0, w - 1.0)), clamp(p.y, 0.0, max(0.0, h - 1.0)))

        def smooth(prev: Point2D, cur: Point2D, alpha: float) -> Point2D:
            return Point2D(prev.x + (cur.x - prev.x) * alpha, prev.y + (cur.y - prev.y) * alpha)

        def predict(pos: Point2D | None, vel: Point2D, dt: float) -> Point2D | None:
            if pos is None:
                return None
            return Point2D(pos.x + vel.x * dt, pos.y + vel.y * dt)

        def aspect_ok(d: DetectedBox, lo: float, hi: float) -> bool:
            x1, y1, x2, y2 = d.xyxy
            bw = max(1.0, x2 - x1)
            bh = max(1.0, y2 - y1)
            r = bw / bh
            return lo <= r <= hi

        while True:
            ok, frame_bgr = cap.read()
            if not ok:
                break

            if idx % step != 0:
                idx += 1
                continue

            kept += 1
            if max_frames is not None and kept > max_frames:
                break

            h, w = frame_bgr.shape[:2]
            if frame_w == 0:
                frame_w = int(w)
                frame_h = int(h)
            diag = (w * w + h * h) ** 0.5

            dt = step / src_fps
            if dt <= 0:
                dt = 1.0 / max(1.0, src_fps)

            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            results = model.predict(
                source=frame_rgb,
                verbose=False,
                device=self.device,
                imgsz=self.imgsz,
                conf=self.conf,
                iou=self.iou,
            )

            dets: list[DetectedBox] = []
            r0 = results[0]
            if getattr(r0, "boxes", None) is not None and len(r0.boxes) > 0:
                for b in r0.boxes:
                    cls = int(b.cls.item())
                    conf = float(b.conf.item())
                    x1, y1, x2, y2 = [float(v) for v in b.xyxy[0].tolist()]
                    dets.append(DetectedBox(cls=cls, conf=conf, xyxy=(x1, y1, x2, y2)))

            # --- Plate tracking: predicted association + size continuity + dead-reckoning
            raw_plate = [d for d in dets if d.cls == 1]
            plate_cands = [d for d in raw_plate if aspect_ok(d, 0.6, 1.7)]
            if last_plate_area is not None and last_plate_area > 0:
                lo_a = last_plate_area * 0.45
                hi_a = last_plate_area * 2.20
                plate_cands = [d for d in plate_cands if lo_a <= d.area <= hi_a]

            if not plate_cands:
                plate_cands = raw_plate

            plate_pred = predict(last_plate, last_plate_v, dt)
            plate_anchor = plate_pred if plate_pred is not None else last_plate

            def plate_gate(det: DetectedBox) -> float:
                bw = max(1.0, det.xyxy[2] - det.xyxy[0])
                bh = max(1.0, det.xyxy[3] - det.xyxy[1])
                vmag = (last_plate_v.x * last_plate_v.x + last_plate_v.y * last_plate_v.y) ** 0.5
                g = max(diag * 0.18, max(bw, bh) * 4.2, vmag * dt * 4.5)
                return clamp(g, diag * 0.03, diag * 0.45)

            best_plate: DetectedBox | None = None
            best_plate_score: float | None = None

            if plate_anchor is None:
                for d in plate_cands:
                    size_bonus = min(1.0, (d.area**0.5) / max(1.0, diag * 0.18))
                    score = -float(d.conf) * 0.75 - size_bonus * 0.25
                    if best_plate_score is None or score < best_plate_score:
                        best_plate = d
                        best_plate_score = score
            else:
                for d in plate_cands:
                    g = plate_gate(d)
                    c = d.center
                    dx = c.x - plate_anchor.x
                    dy = c.y - plate_anchor.y
                    dist = (dx * dx + dy * dy) ** 0.5
                    if dist > g:
                        continue
                    area_pen = 0.0
                    if last_plate_area is not None and last_plate_area > 0:
                        ratio = d.area / last_plate_area
                        area_pen = abs(ratio - 1.0) * 0.35
                    score = (dist / g) + (1.0 - min(1.0, max(0.0, d.conf))) * 0.45 + area_pen
                    if best_plate_score is None or score < best_plate_score:
                        best_plate = d
                        best_plate_score = score

                if best_plate is None:
                    for d in plate_cands:
                        g = plate_gate(d) * 1.8
                        c = d.center
                        dx = c.x - plate_anchor.x
                        dy = c.y - plate_anchor.y
                        dist = (dx * dx + dy * dy) ** 0.5
                        if dist > g:
                            continue
                        area_pen = 0.0
                        if last_plate_area is not None and last_plate_area > 0:
                            ratio = d.area / last_plate_area
                            area_pen = abs(ratio - 1.0) * 0.20
                        score = (dist / g) + (1.0 - min(1.0, max(0.0, d.conf))) * 0.35 + area_pen
                        if best_plate_score is None or score < best_plate_score:
                            best_plate = d
                            best_plate_score = score

            if best_plate is None:
                last_plate_miss += 1
                if last_plate is not None:
                    nxt = predict(last_plate, last_plate_v, dt)
                    if nxt is not None:
                        last_plate = clamp_pt(nxt)
                    last_plate_v = Point2D(last_plate_v.x * 0.98, last_plate_v.y * 0.98)
            else:
                c = best_plate.center
                if last_plate is None:
                    last_plate = c
                    last_plate_v = Point2D(0.0, 0.0)
                else:
                    prev_pos = last_plate
                    last_plate = clamp_pt(smooth(last_plate, c, 0.85))
                    inst_v = Point2D((c.x - prev_pos.x) / dt, (c.y - prev_pos.y) / dt)
                    last_plate_v = smooth(last_plate_v, inst_v, 0.75)
                last_plate_miss = 0
                if last_plate_area is None:
                    last_plate_area = best_plate.area
                else:
                    last_plate_area = last_plate_area * 0.9 + best_plate.area * 0.1

            plate_center = last_plate
            plate_wh: tuple[float, float] | None = None
            if best_plate is not None:
                plate_wh = (
                    max(1.0, best_plate.xyxy[2] - best_plate.xyxy[0]),
                    max(1.0, best_plate.xyxy[3] - best_plate.xyxy[1]),
                )

            # --- End tracking: predicted association + gated by proximity to plate
            end_cands = [d for d in dets if d.cls == 0]
            end_pred = predict(last_end, last_end_v, dt)
            end_anchor = end_pred if end_pred is not None else last_end

            def end_gate(det: DetectedBox) -> float:
                bw = max(1.0, det.xyxy[2] - det.xyxy[0])
                bh = max(1.0, det.xyxy[3] - det.xyxy[1])
                vmag = (last_end_v.x * last_end_v.x + last_end_v.y * last_end_v.y) ** 0.5
                g = max(diag * 0.20, max(bw, bh) * 4.8, vmag * dt * 5.0)
                return clamp(g, diag * 0.04, diag * 0.50)

            best_end: DetectedBox | None = None
            best_end_score: float | None = None

            for d in end_cands:
                c = d.center

                if plate_center is not None:
                    dxp = c.x - plate_center.x
                    dyp = c.y - plate_center.y
                    dist_p = (dxp * dxp + dyp * dyp) ** 0.5
                    plate_gate_r = diag * 0.28
                    if plate_wh is not None:
                        plate_gate_r = max(plate_gate_r, max(plate_wh) * 3.8)
                        if abs(dyp) > plate_wh[1] * 1.3:
                            continue
                    if dist_p > plate_gate_r:
                        continue

                if end_anchor is None:
                    score = (1.0 - min(1.0, max(0.0, d.conf)))
                else:
                    g = end_gate(d)
                    dx = c.x - end_anchor.x
                    dy = c.y - end_anchor.y
                    dist = (dx * dx + dy * dy) ** 0.5
                    if dist > g:
                        continue
                    score = (dist / g) + (1.0 - min(1.0, max(0.0, d.conf))) * 0.55

                if best_end_score is None or score < best_end_score:
                    best_end = d
                    best_end_score = score

            if best_end is None:
                last_end_miss += 1
                if last_end is not None:
                    nxt = predict(last_end, last_end_v, dt)
                    if nxt is not None:
                        last_end = clamp_pt(nxt)
                    last_end_v = Point2D(last_end_v.x * 0.97, last_end_v.y * 0.97)
            else:
                c = best_end.center
                if last_end is None:
                    last_end = c
                    last_end_v = Point2D(0.0, 0.0)
                else:
                    prev_pos = last_end
                    last_end = clamp_pt(smooth(last_end, c, 0.82))
                    inst_v = Point2D((c.x - prev_pos.x) / dt, (c.y - prev_pos.y) / dt)
                    last_end_v = smooth(last_end_v, inst_v, 0.75)
                last_end_miss = 0

            def pack(det: DetectedBox | None, pos: Point2D | None) -> dict[str, Any] | None:
                if pos is None:
                    return None
                if det is None:
                    return {"conf": 0.0, "center": {"x": pos.x, "y": pos.y}, "bbox": None}
                x1, y1, x2, y2 = det.xyxy
                return {
                    "conf": det.conf,
                    "center": {"x": pos.x, "y": pos.y},
                    "bbox": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                }

            t_ms = int(round((idx / src_fps) * 1000.0))
            frames.append(
                {
                    "frameIndex": idx,
                    "timeMs": t_ms,
                    "end": pack(best_end, last_end),
                    "plate": pack(best_plate, last_plate),
                }
            )

            idx += 1

        cap.release()

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

    def _aspect_ok(self, d: DetectedBox, *, lo: float, hi: float) -> bool:
        x1, y1, x2, y2 = d.xyxy
        w = max(1.0, x2 - x1)
        h = max(1.0, y2 - y1)
        r = w / h
        return lo <= r <= hi

    def _box_wh(self, d: DetectedBox | None) -> tuple[float, float] | None:
        if d is None:
            return None
        x1, y1, x2, y2 = d.xyxy
        return max(1.0, x2 - x1), max(1.0, y2 - y1)

    def _pick_tracked(
        self,
        dets: list[DetectedBox],
        *,
        prev: Point2D | None,
        vel: Point2D | None,
        diag: float,
        prefer_large_when_uninit: bool,
        max_jump_frac: float,
        ref_center: Point2D | None = None,
        ref_box_wh: tuple[float, float] | None = None,
    ) -> DetectedBox | None:
        if not dets:
            return None

        if prev is None and ref_center is None:
            best = dets[0]
            best_score = -1.0
            for d in dets:
                size_bonus = 0.0
                if prefer_large_when_uninit:
                    size_bonus = min(1.0, (d.area ** 0.5) / max(1.0, diag * 0.18))
                score = float(d.conf) * 0.75 + size_bonus * 0.25
                if score > best_score:
                    best = d
                    best_score = score
            return best

        def predict(p: Point2D | None, v: Point2D | None) -> Point2D | None:
            if p is None:
                return None
            if v is None:
                return p
            return Point2D(p.x + v.x, p.y + v.y)

        pred = predict(prev, vel)
        anchor = pred if pred is not None else prev
        gate = max(8.0, diag * max_jump_frac)

        best: DetectedBox | None = None
        best_score: float | None = None

        for d in dets:
            c = d.center

            score = 0.0

            if anchor is not None:
                dx = c.x - anchor.x
                dy = c.y - anchor.y
                dist = (dx * dx + dy * dy) ** 0.5
                if dist > gate:
                    continue
                score += dist / gate

            if ref_center is not None:
                dxr = c.x - ref_center.x
                dyr = c.y - ref_center.y
                dist_r = (dxr * dxr + dyr * dyr) ** 0.5
                ref_gate = gate
                if ref_box_wh is not None:
                    ref_gate = max(ref_gate, max(ref_box_wh) * 2.2)
                    if abs(dyr) > ref_box_wh[1] * 0.9:
                        continue
                if dist_r > ref_gate:
                    continue
                score += (dist_r / ref_gate) * 0.9

            score += (1.0 - min(1.0, max(0.0, d.conf))) * 0.25

            if best is None or best_score is None or score < best_score:
                best = d
                best_score = score

        return best

    def _aspect_ok(self, d: DetectedBox, *, lo: float, hi: float) -> bool:
        x1, y1, x2, y2 = d.xyxy
        w = max(1.0, x2 - x1)
        h = max(1.0, y2 - y1)
        r = w / h
        return lo <= r <= hi

    def _serialize_track(self, d: DetectedBox | None, center: Point2D | None) -> dict[str, Any] | None:
        if center is None:
            return None
        if d is None:
            return {
                "conf": 0.0,
                "center": {"x": center.x, "y": center.y},
                "bbox": None,
            }
        x1, y1, x2, y2 = d.xyxy
        return {
            "conf": d.conf,
            "center": {"x": center.x, "y": center.y},
            "bbox": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
        }