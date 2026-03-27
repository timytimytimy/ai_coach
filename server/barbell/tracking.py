from __future__ import annotations

from dataclasses import dataclass

from server.barbell.types import DetectedBox, Point2D


@dataclass
class _TrackState:
    pos: Point2D | None
    vel: Point2D
    miss: int


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else (hi if v > hi else v)


def _smooth(prev: Point2D, cur: Point2D, alpha: float) -> Point2D:
    return Point2D(prev.x + (cur.x - prev.x) * alpha, prev.y + (cur.y - prev.y) * alpha)


def _predict(pos: Point2D | None, vel: Point2D, dt: float) -> Point2D | None:
    if pos is None:
        return None
    return Point2D(pos.x + vel.x * dt, pos.y + vel.y * dt)


def _clamp_pt(p: Point2D, *, w: int, h: int) -> Point2D:
    return Point2D(_clamp(p.x, 0.0, max(0.0, w - 1.0)), _clamp(p.y, 0.0, max(0.0, h - 1.0)))


def _gate_from(
    *,
    diag: float,
    box: DetectedBox,
    vel: Point2D,
    dt: float,
    diag_min: float,
    diag_max: float,
    box_mul: float,
    vel_mul: float,
) -> float:
    vmag = (vel.x * vel.x + vel.y * vel.y) ** 0.5
    g = max(diag * diag_min, max(box.width, box.height) * box_mul, vmag * dt * vel_mul)
    return _clamp(g, diag * 0.03, diag * diag_max)


def _reassociation_limit_px(
    *,
    diag: float,
    box: DetectedBox,
    wh_ema: tuple[float, float] | None,
    miss: int,
) -> float:
    ref = max(box.width, box.height, 1.0)
    if wh_ema is not None:
        ref = max(ref, wh_ema[0], wh_ema[1])

    if miss <= 0:
        mult = 1.0
        hi = diag * 0.14
    elif miss == 1:
        mult = 1.35
        hi = diag * 0.22
    elif miss == 2:
        mult = 1.8
        hi = diag * 0.30
    else:
        mult = 2.4
        hi = diag * 0.45

    return _clamp(ref * mult, 36.0, hi)


def _plate_end_support_score(
    plate: DetectedBox,
    end_dets: list[DetectedBox],
) -> float | None:
    if not end_dets:
        return None

    plate_c = plate.center
    plate_w = max(plate.width, 1.0)
    plate_h = max(plate.height, 1.0)
    gate_x = max(28.0, plate_w * 1.45)
    gate_y = max(20.0, plate_h * 0.60)
    gate_r = max(32.0, max(plate_w, plate_h) * 1.15)

    best: float | None = None
    for end in end_dets:
        end_c = end.center
        dx = abs(end_c.x - plate_c.x)
        dy = abs(end_c.y - plate_c.y)
        radial = (dx * dx + dy * dy) ** 0.5
        score = max(dx / gate_x, dy / gate_y, radial / gate_r)
        if best is None or score < best:
            best = score
    return best


def _strict_reacquisition_limit_px(
    *,
    diag: float,
    box: DetectedBox,
    wh_ema: tuple[float, float] | None,
    vel: Point2D,
    dt: float,
) -> float:
    ref = max(box.width, box.height, 1.0)
    if wh_ema is not None:
        ref = max(ref, wh_ema[0], wh_ema[1])
    vmag = (vel.x * vel.x + vel.y * vel.y) ** 0.5
    return _clamp(max(ref * 1.15, vmag * dt * 1.35, 54.0), 54.0, diag * 0.12)


@dataclass
class PlateTracker:
    state: _TrackState
    area_ema: float | None = None
    wh_ema: tuple[float, float] | None = None

    def _tracked_bbox(self, *, w: int, h: int) -> tuple[float, float, float, float] | None:
        if self.state.pos is None or self.wh_ema is None:
            return None
        bw, bh = self.wh_ema
        bw = max(1.0, bw)
        bh = max(1.0, bh)
        cx = self.state.pos.x
        cy = self.state.pos.y
        x1 = _clamp(cx - bw / 2.0, 0.0, max(0.0, w - 1.0))
        y1 = _clamp(cy - bh / 2.0, 0.0, max(0.0, h - 1.0))
        x2 = _clamp(cx + bw / 2.0, 0.0, max(0.0, w - 1.0))
        y2 = _clamp(cy + bh / 2.0, 0.0, max(0.0, h - 1.0))
        return (x1, y1, x2, y2)

    def step(
        self,
        *,
        dets: list[DetectedBox],
        w: int,
        h: int,
        diag: float,
        dt: float,
    ) -> tuple[DetectedBox | None, Point2D | None, tuple[float, float, float, float] | None]:
        raw_plate = [d for d in dets if d.cls == 1]
        raw_end = [d for d in dets if d.cls == 0]
        cands = [d for d in raw_plate if 0.6 <= d.aspect_ratio <= 1.7]

        if self.area_ema is not None and self.area_ema > 0:
            lo_a = self.area_ema * 0.45
            hi_a = self.area_ema * 2.20
            cands = [d for d in cands if lo_a <= d.area <= hi_a]

        if not cands:
            cands = raw_plate

        pred = _predict(self.state.pos, self.state.vel, dt)
        anchor = pred if pred is not None else self.state.pos
        support_scores = {
            id(d): _plate_end_support_score(d, raw_end)
            for d in cands
        }
        supported = [
            d
            for d in cands
            if support_scores.get(id(d)) is not None and support_scores[id(d)] <= 1.0
        ]
        reacq_without_support = anchor is not None and self.state.miss > 0 and not supported

        # Initial acquisition and post-miss reacquisition are the most fragile stages.
        # Prefer plate detections that also have a plausible nearby bar-end detection.
        if supported and (anchor is None or self.state.miss > 0):
            cands = supported

        best: DetectedBox | None = None
        best_score: float | None = None

        if anchor is None:
            for d in cands:
                size_bonus = min(1.0, (d.area**0.5) / max(1.0, diag * 0.18))
                support = support_scores.get(id(d))
                support_pen = 0.0
                if support is not None:
                    support_pen = max(0.0, support - 0.35) * 0.15
                elif raw_end:
                    support_pen = 0.25
                score = (1.0 - min(1.0, max(0.0, d.conf))) * 0.7 - size_bonus * 0.3 + support_pen
                if best_score is None or score < best_score:
                    best = d
                    best_score = score
        else:
            for pass_i in (0, 1):
                for d in cands:
                    g = _gate_from(
                        diag=diag,
                        box=d,
                        vel=self.state.vel,
                        dt=dt,
                        diag_min=0.18,
                        diag_max=0.45,
                        box_mul=4.2,
                        vel_mul=4.5,
                    )
                    if pass_i == 1:
                        g *= 1.8

                    c = d.center
                    dx = c.x - anchor.x
                    dy = c.y - anchor.y
                    dist = (dx * dx + dy * dy) ** 0.5
                    reassoc_limit = _reassociation_limit_px(
                        diag=diag,
                        box=d,
                        wh_ema=self.wh_ema,
                        miss=self.state.miss,
                    )
                    if reacq_without_support:
                        reassoc_limit = min(
                            reassoc_limit,
                            _strict_reacquisition_limit_px(
                                diag=diag,
                                box=d,
                                wh_ema=self.wh_ema,
                                vel=self.state.vel,
                                dt=dt,
                            ),
                        )
                    if dist > reassoc_limit:
                        continue
                    if dist > g:
                        continue

                    area_pen = 0.0
                    if self.area_ema is not None and self.area_ema > 0:
                        ratio = d.area / self.area_ema
                        area_pen = abs(ratio - 1.0) * (0.20 if pass_i == 1 else 0.35)

                    size_pen = 0.0
                    if self.wh_ema is not None and self.wh_ema[0] > 0 and self.wh_ema[1] > 0:
                        dw = abs(d.width - self.wh_ema[0]) / self.wh_ema[0]
                        dh = abs(d.height - self.wh_ema[1]) / self.wh_ema[1]
                        size_pen = (dw + dh) * (0.12 if pass_i == 1 else 0.20)

                    support_pen = 0.0
                    support = support_scores.get(id(d))
                    if support is not None:
                        support_pen = max(0.0, support - 0.35) * (0.08 if pass_i == 1 else 0.12)
                    elif supported:
                        support_pen = 0.18 if pass_i == 1 else 0.24

                    score = (
                        (dist / g)
                        + (1.0 - min(1.0, max(0.0, d.conf))) * (0.35 if pass_i == 1 else 0.45)
                        + area_pen
                        + size_pen
                        + support_pen
                    )
                    if best_score is None or score < best_score:
                        best = d
                        best_score = score

                if best is not None:
                    break

        if best is None:
            self.state.miss += 1
            if self.state.pos is not None:
                nxt = _predict(self.state.pos, self.state.vel, dt)
                if nxt is not None:
                    self.state.pos = _clamp_pt(nxt, w=w, h=h)
                self.state.vel = Point2D(self.state.vel.x * 0.98, self.state.vel.y * 0.98)
            return None, self.state.pos, self._tracked_bbox(w=w, h=h)

        c = best.center
        if self.state.pos is None:
            self.state.pos = _clamp_pt(c, w=w, h=h)
            self.state.vel = Point2D(0.0, 0.0)
        else:
            prev = self.state.pos
            self.state.pos = _clamp_pt(_smooth(self.state.pos, c, 0.85), w=w, h=h)
            inst_v = Point2D((c.x - prev.x) / dt, (c.y - prev.y) / dt)
            self.state.vel = _smooth(self.state.vel, inst_v, 0.75)

        self.state.miss = 0

        if self.area_ema is None:
            self.area_ema = best.area
        else:
            self.area_ema = self.area_ema * 0.9 + best.area * 0.1

        if self.wh_ema is None:
            self.wh_ema = (best.width, best.height)
        else:
            bw, bh = self.wh_ema
            self.wh_ema = (bw * 0.9 + best.width * 0.1, bh * 0.9 + best.height * 0.1)

        return best, self.state.pos


@dataclass
class EndTracker:
    state: _TrackState
    wh_ema: tuple[float, float] | None = None

    def _tracked_bbox(self, *, w: int, h: int) -> tuple[float, float, float, float] | None:
        if self.state.pos is None or self.wh_ema is None:
            return None
        bw, bh = self.wh_ema
        bw = max(1.0, bw)
        bh = max(1.0, bh)
        cx = self.state.pos.x
        cy = self.state.pos.y
        x1 = _clamp(cx - bw / 2.0, 0.0, max(0.0, w - 1.0))
        y1 = _clamp(cy - bh / 2.0, 0.0, max(0.0, h - 1.0))
        x2 = _clamp(cx + bw / 2.0, 0.0, max(0.0, w - 1.0))
        y2 = _clamp(cy + bh / 2.0, 0.0, max(0.0, h - 1.0))
        return (x1, y1, x2, y2)

    def step(
        self,
        *,
        dets: list[DetectedBox],
        w: int,
        h: int,
        diag: float,
        dt: float,
        plate_center: Point2D | None,
        plate_wh: tuple[float, float] | None,
    ) -> tuple[DetectedBox | None, Point2D | None, tuple[float, float, float, float] | None]:
        cands = [d for d in dets if d.cls == 0]

        pred = _predict(self.state.pos, self.state.vel, dt)
        anchor = pred if pred is not None else self.state.pos

        best: DetectedBox | None = None
        best_score: float | None = None

        for d in cands:
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

            if anchor is None:
                score = (1.0 - min(1.0, max(0.0, d.conf)))
            else:
                g = _gate_from(
                    diag=diag,
                    box=d,
                    vel=self.state.vel,
                    dt=dt,
                    diag_min=0.20,
                    diag_max=0.50,
                    box_mul=4.8,
                    vel_mul=5.0,
                )
                dx = c.x - anchor.x
                dy = c.y - anchor.y
                dist = (dx * dx + dy * dy) ** 0.5
                if dist > g:
                    continue
                score = (dist / g) + (1.0 - min(1.0, max(0.0, d.conf))) * 0.55

            if best_score is None or score < best_score:
                best = d
                best_score = score

        if best is None:
            self.state.miss += 1
            if self.state.pos is not None:
                nxt = _predict(self.state.pos, self.state.vel, dt)
                if nxt is not None:
                    self.state.pos = _clamp_pt(nxt, w=w, h=h)
                self.state.vel = Point2D(self.state.vel.x * 0.97, self.state.vel.y * 0.97)
            return None, self.state.pos, self._tracked_bbox(w=w, h=h)

        c = best.center
        if self.state.pos is None:
            self.state.pos = _clamp_pt(c, w=w, h=h)
            self.state.vel = Point2D(0.0, 0.0)
        else:
            prev = self.state.pos
            self.state.pos = _clamp_pt(_smooth(self.state.pos, c, 0.82), w=w, h=h)
            inst_v = Point2D((c.x - prev.x) / dt, (c.y - prev.y) / dt)
            self.state.vel = _smooth(self.state.vel, inst_v, 0.75)

        self.state.miss = 0

        if self.wh_ema is None:
            self.wh_ema = (best.width, best.height)
        else:
            bw, bh = self.wh_ema
            self.wh_ema = (bw * 0.9 + best.width * 0.1, bh * 0.9 + best.height * 0.1)

        return best, self.state.pos
