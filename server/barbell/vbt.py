from __future__ import annotations

from dataclasses import dataclass
import logging
from statistics import median
from typing import Any

_LOG = logging.getLogger("ssc.vbt")


@dataclass(frozen=True)
class VbtRep:
    repIndex: int
    startMs: int
    endMs: int
    displacementCm: float
    avgVelocityMps: float
    scaleCmPerPx: float


def compute_vbt_from_barbell(
    barbell_result: dict[str, Any] | None,
    *,
    bar_end_diameter_cm: float = 5.0,
    plate_diameter_cm: float = 45.0,
    min_displacement_cm: float = 5.0,
    min_rep_ms: int = 200,
    max_rep_ms: int = 4000,
) -> dict[str, Any] | None:
    if not barbell_result:
        return {
            "barEndDiameterCm": float(bar_end_diameter_cm),
            "error": "missing barbell trajectory",
        }

    frames = barbell_result.get("frames")
    if not isinstance(frames, list) or not frames:
        return {
            "barEndDiameterCm": float(bar_end_diameter_cm),
            "error": "missing barbell frames",
        }

    src_fps = barbell_result.get("sourceFps")
    src_fps_val = float(src_fps) if isinstance(src_fps, (int, float)) and float(src_fps) > 0 else None

    end_series = _extract_anchor_series(frames, src_fps_val=src_fps_val, anchor="end")
    plate_series = _extract_anchor_series(frames, src_fps_val=src_fps_val, anchor="plate")
    plate_scale = _estimate_scale_from_anchor(
        frames,
        anchor="plate",
        diameter_cm=float(plate_diameter_cm),
        expected_class=1,
    )
    end_scale = _estimate_scale_from_anchor(
        frames,
        anchor="end",
        diameter_cm=float(bar_end_diameter_cm),
        expected_class=0,
    )
    if plate_series is not None and end_scale is not None:
        plate_end_result = _compute_vbt_from_series(
            series=plate_series,
            src_fps_val=src_fps_val,
            cm_per_px=float(end_scale["cmPerPx"]),
            scale_from=end_scale["scaleFrom"],
            min_displacement_cm=min_displacement_cm,
            min_rep_ms=min_rep_ms,
            max_rep_ms=max_rep_ms,
        )
        if (
            plate_end_result is not None
            and plate_end_result["reps"]
            and _has_local_scale_support(
                frames,
                anchor="end",
                reps=plate_end_result["reps"],
                expected_class=0,
                min_hits=5,
                min_conf=0.35,
            )
        ):
            plate_end_result["motionSource"] = "plate"
            plate_end_result["scaleSource"] = "end"
            plate_end_result["barEndDiameterCm"] = float(bar_end_diameter_cm)
            return plate_end_result
        if plate_end_result is not None and plate_end_result["reps"] and plate_scale is not None:
            plate_fallback = _rescale_vbt_result(
                result=plate_end_result,
                cm_per_px=float(plate_scale["cmPerPx"]),
                scale_from=plate_scale["scaleFrom"],
            )
            plate_fallback["motionSource"] = "plate"
            plate_fallback["scaleSource"] = "plate"
            plate_fallback["plateDiameterCmAssumed"] = float(plate_diameter_cm)
            plate_fallback["barEndDiameterCm"] = float(bar_end_diameter_cm)
            return plate_fallback

    if plate_series is not None and plate_scale is not None:
        plate_result = _compute_vbt_from_series(
            series=plate_series,
            src_fps_val=src_fps_val,
            cm_per_px=float(plate_scale["cmPerPx"]),
            scale_from=plate_scale["scaleFrom"],
            min_displacement_cm=min_displacement_cm,
            min_rep_ms=min_rep_ms,
            max_rep_ms=max_rep_ms,
        )
        if plate_result is not None and plate_result["reps"]:
            plate_result["motionSource"] = "plate"
            plate_result["scaleSource"] = "plate"
            plate_result["plateDiameterCmAssumed"] = float(plate_diameter_cm)
            plate_result["barEndDiameterCm"] = float(bar_end_diameter_cm)
            return plate_result

    if end_series is not None and end_scale is not None:
        end_result = _compute_vbt_from_series(
            series=end_series,
            src_fps_val=src_fps_val,
            cm_per_px=float(end_scale["cmPerPx"]),
            scale_from=end_scale["scaleFrom"],
            min_displacement_cm=min_displacement_cm,
            min_rep_ms=min_rep_ms,
            max_rep_ms=max_rep_ms,
        )
        if end_result is not None and end_result["reps"]:
            end_result["motionSource"] = "end"
            end_result["scaleSource"] = "end"
            end_result["barEndDiameterCm"] = float(bar_end_diameter_cm)
            return end_result

    return {
        "barEndDiameterCm": float(bar_end_diameter_cm),
        "error": "no reliable plate/end combination for VBT",
    }


def _rescale_vbt_result(
    *,
    result: dict[str, Any],
    cm_per_px: float,
    scale_from: dict[str, Any],
) -> dict[str, Any]:
    prev_scale = result.get("scaleCmPerPx")
    prev_scale_val = float(prev_scale) if isinstance(prev_scale, (int, float)) and float(prev_scale) > 0 else 1.0
    ratio = float(cm_per_px) / prev_scale_val

    reps_out: list[dict[str, Any]] = []
    for rep in result.get("reps") or []:
        if not isinstance(rep, dict):
            continue
        reps_out.append(
            {
                **rep,
                "displacementCm": float(rep.get("displacementCm", 0.0)) * ratio,
                "avgVelocityMps": float(rep.get("avgVelocityMps", 0.0)) * ratio,
                "scaleCmPerPx": float(cm_per_px),
            }
        )

    samples_out: list[dict[str, Any]] = []
    for sample in result.get("samples") or []:
        if not isinstance(sample, dict):
            continue
        speed = sample.get("speedMps")
        samples_out.append(
            {
                **sample,
                "speedMps": (float(speed) * ratio) if isinstance(speed, (int, float)) else None,
            }
        )

    return {
        **result,
        "scaleCmPerPx": float(cm_per_px),
        "scaleFrom": {
            **scale_from,
            "axis": result.get("scaleFrom", {}).get("axis"),
        },
        "reps": reps_out,
        "samples": samples_out,
    }


def _moving_average(xs: list[float], *, window: int) -> list[float]:
    if window <= 1 or len(xs) <= 2:
        return xs[:]

    w = max(1, int(window))
    half = w // 2
    out: list[float] = []
    for i in range(len(xs)):
        lo = max(0, i - half)
        hi = min(len(xs), i + half + 1)
        out.append(sum(xs[lo:hi]) / max(1, hi - lo))
    return out


def _extract_anchor_series(
    frames: list[dict[str, Any]],
    *,
    src_fps_val: float | None,
    anchor: str,
) -> dict[str, list[Any]] | None:
    xs: list[float] = []
    ys: list[float] = []
    times_ms: list[int] = []
    frame_idx: list[int] = []
    confs: list[float] = []

    for f in frames:
        if not isinstance(f, dict):
            continue
        node = f.get(anchor)
        if not isinstance(node, dict):
            continue
        if node.get("tracked") is True:
            continue
        center = node.get("center")
        if not isinstance(center, dict):
            continue
        x = center.get("x")
        y = center.get("y")
        conf = node.get("conf")
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            continue
        if not isinstance(conf, (int, float)) or float(conf) <= 0.0:
            continue
        fi = f.get("frameIndex")
        fi_int = int(fi) if isinstance(fi, (int, float)) else None

        t_ms: int | None = None
        if src_fps_val is not None and fi_int is not None:
            t_ms = int(round((fi_int / src_fps_val) * 1000.0))
        else:
            t = f.get("timeMs")
            if isinstance(t, (int, float)):
                t_ms = int(t)
        if t_ms is None:
            continue

        xs.append(float(x))
        ys.append(float(y))
        times_ms.append(int(t_ms))
        frame_idx.append(fi_int if fi_int is not None else len(frame_idx))
        confs.append(float(conf))

    if len(times_ms) < 8:
        return None

    xs, ys, times_ms, frame_idx, confs = _bridge_motion_gaps(
        xs=xs,
        ys=ys,
        times_ms=times_ms,
        frame_idx=frame_idx,
        confs=confs,
        max_gap_ms=180,
    )
    if len(times_ms) < 8:
        return None

    return {
        "xs": xs,
        "ys": ys,
        "timesMs": times_ms,
        "frameIndex": frame_idx,
        "confs": confs,
    }


def _estimate_scale_from_anchor(
    frames: list[dict[str, Any]],
    *,
    anchor: str,
    diameter_cm: float,
    expected_class: int,
) -> dict[str, Any] | None:
    cand: list[tuple[float, float, int, int]] = []  # conf, diameter_px, frame_idx, time_ms
    for f in frames:
        if not isinstance(f, dict):
            continue
        node = f.get(anchor)
        if not isinstance(node, dict):
            continue
        if node.get("tracked") is True:
            continue
        node_cls = node.get("class")
        if node_cls is not None and int(node_cls) != expected_class:
            continue
        conf = node.get("conf")
        if not isinstance(conf, (int, float)) or float(conf) <= 0.0:
            continue
        bbox = node.get("bbox")
        if not isinstance(bbox, dict):
            continue
        x1 = bbox.get("x1")
        y1 = bbox.get("y1")
        x2 = bbox.get("x2")
        y2 = bbox.get("y2")
        if not all(isinstance(v, (int, float)) for v in (x1, y1, x2, y2)):
            continue
        dpx = max(1e-6, min(abs(float(x2) - float(x1)), abs(float(y2) - float(y1))))
        fi = f.get("frameIndex")
        t = f.get("timeMs")
        cand.append((float(conf), dpx, int(fi) if isinstance(fi, (int, float)) else -1, int(t) if isinstance(t, (int, float)) else -1))

    if not cand:
        return None

    cand.sort(reverse=True)
    top = cand[: min(30, len(cand))]
    med_d = float(median([d for _, d, _, _ in top]))
    scale_conf, scale_dpx, scale_fi, scale_t = min(top, key=lambda t: abs(t[1] - med_d))
    return {
        "cmPerPx": float(diameter_cm) / max(1e-6, float(scale_dpx)),
        "scaleFrom": {
            "anchor": anchor,
            "chosenFrameIndex": int(scale_fi),
            "chosenTimeMs": int(scale_t),
            "chosenConf": float(scale_conf),
            "chosenDiameterPx": float(scale_dpx),
            "diameterPxMedianTopN": float(med_d),
        },
    }


def _has_local_scale_support(
    frames: list[dict[str, Any]],
    *,
    anchor: str,
    reps: list[dict[str, Any]],
    expected_class: int,
    min_hits: int,
    min_conf: float,
) -> bool:
    windows: list[tuple[int, int]] = []
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
        windows.append((int(start), int(end)))

    if not windows:
        return False

    hits = 0
    for f in frames:
        if not isinstance(f, dict):
            continue
        t = f.get("timeMs")
        if not isinstance(t, (int, float)):
            continue
        t_ms = int(t)
        if not any(start <= t_ms <= end for start, end in windows):
            continue
        node = f.get(anchor)
        if not isinstance(node, dict):
            continue
        if node.get("tracked") is True:
            continue
        node_cls = node.get("class")
        if node_cls is not None and int(node_cls) != expected_class:
            continue
        conf = node.get("conf")
        if not isinstance(conf, (int, float)) or float(conf) < float(min_conf):
            continue
        bbox = node.get("bbox")
        if not isinstance(bbox, dict):
            continue
        hits += 1
        if hits >= int(min_hits):
            return True
    return False


def _compute_vbt_from_series(
    *,
    series: dict[str, list[Any]],
    src_fps_val: float | None,
    cm_per_px: float,
    scale_from: dict[str, Any],
    min_displacement_cm: float,
    min_rep_ms: int,
    max_rep_ms: int,
) -> dict[str, Any] | None:
    xs = [float(v) for v in series["xs"]]
    ys = [float(v) for v in series["ys"]]
    times_ms = [int(v) for v in series["timesMs"]]
    frame_idx = [int(v) for v in series["frameIndex"]]

    x_rng = _robust_range(xs)
    y_rng = _robust_range(ys)
    axis = "y" if y_rng >= x_rng else "x"
    signal = ys if axis == "y" else xs

    if _LOG.isEnabledFor(logging.DEBUG):
        _LOG.debug(
            "vbt_scale axis=%s cmPerPx=%.6f scaleFrom=%s",
            axis,
            float(cm_per_px),
            scale_from,
        )

    segment_signal = _moving_average(signal, window=3)
    s = _moving_average(signal, window=5)
    min_displacement_px = max(1e-6, (float(min_displacement_cm) / float(cm_per_px)))
    pairs, pair_method = _detect_concentric_pairs(
        signal=segment_signal,
        times_ms=times_ms,
        min_rep_ms=min_rep_ms,
        max_rep_ms=max_rep_ms,
        min_displacement_px=min_displacement_px,
    )
    start_extremum = "max"

    reps: list[VbtRep] = []
    rep_debug: list[dict[str, Any]] = []

    for start_i, end_i in pairs:
        start_ms = times_ms[start_i]
        end_ms = times_ms[end_i]
        dur_ms = end_ms - start_ms
        if not (min_rep_ms <= dur_ms <= max_rep_ms):
            continue

        disp_px = float(s[start_i] - s[end_i])
        if disp_px <= 0:
            continue
        disp_cm = disp_px * cm_per_px
        if disp_cm < min_displacement_cm:
            continue

        dur_s = dur_ms / 1000.0
        if src_fps_val is not None:
            df = frame_idx[end_i] - frame_idx[start_i]
            if df > 0:
                dur_s = df / src_fps_val
                start_ms = int(round((frame_idx[start_i] / src_fps_val) * 1000.0))
                end_ms = int(round((frame_idx[end_i] / src_fps_val) * 1000.0))
                dur_ms = end_ms - start_ms

        avg_mps = (disp_cm / 100.0) / max(1e-6, dur_s)
        rep_index = len(reps) + 1

        reps.append(
            VbtRep(
                repIndex=rep_index,
                startMs=int(start_ms),
                endMs=int(end_ms),
                displacementCm=float(disp_cm),
                avgVelocityMps=float(avg_mps),
                scaleCmPerPx=float(cm_per_px),
            )
        )
        rep_debug.append(
            {
                "axis": axis,
                "bottomFrameIndex": int(frame_idx[start_i]),
                "topFrameIndex": int(frame_idx[end_i]),
                "startExtremum": start_extremum,
                "segmentation": pair_method,
                "displacementPx": float(disp_px),
                "durationMs": int(dur_ms),
            }
        )

    samples: list[dict[str, Any]] = []
    direction = -1.0 if start_extremum == "max" else 1.0
    for i, t_ms in enumerate(times_ms):
        rep_index = _rep_index_at_ms(reps, int(t_ms))
        speed_mps = None
        if rep_index is not None:
            speed_mps = _instant_concentric_speed_mps(
                signal=s,
                times_ms=times_ms,
                idx=i,
                cm_per_px=cm_per_px,
                direction=direction,
            )
        samples.append(
            {
                "timeMs": int(t_ms),
                "repIndex": int(rep_index) if rep_index is not None else None,
                "speedMps": float(speed_mps) if speed_mps is not None else None,
            }
        )

    return {
        "startExtremum": start_extremum,
        "scaleCmPerPx": float(cm_per_px),
        "scaleFrom": {
            **scale_from,
            "axis": axis,
        },
        "reps": [
            {
                "repIndex": r.repIndex,
                "timeRangeMs": {"start": r.startMs, "end": r.endMs},
                "displacementCm": r.displacementCm,
                "avgVelocityMps": r.avgVelocityMps,
                "scaleCmPerPx": r.scaleCmPerPx,
                "debug": rep_debug[i],
            }
            for i, r in enumerate(reps)
        ],
        "samples": samples,
    }


def _bridge_motion_gaps(
    *,
    xs: list[float],
    ys: list[float],
    times_ms: list[int],
    frame_idx: list[int],
    confs: list[float],
    max_gap_ms: int,
) -> tuple[list[float], list[float], list[int], list[int], list[float]]:
    if len(times_ms) < 2:
        return xs, ys, times_ms, frame_idx, confs

    out_x: list[float] = [xs[0]]
    out_y: list[float] = [ys[0]]
    out_t: list[int] = [times_ms[0]]
    out_f: list[int] = [frame_idx[0]]
    out_c: list[float] = [confs[0]]

    for i in range(1, len(times_ms)):
        prev_t = int(times_ms[i - 1])
        cur_t = int(times_ms[i])
        dt = cur_t - prev_t
        prev_f = int(frame_idx[i - 1])
        cur_f = int(frame_idx[i])
        df = cur_f - prev_f
        if dt > 0 and df > 1 and dt <= max_gap_ms:
            for missing in range(1, df):
                alpha = missing / float(df)
                out_x.append(xs[i - 1] + (xs[i] - xs[i - 1]) * alpha)
                out_y.append(ys[i - 1] + (ys[i] - ys[i - 1]) * alpha)
                out_t.append(int(round(prev_t + dt * alpha)))
                out_f.append(prev_f + missing)
                out_c.append(min(float(confs[i - 1]), float(confs[i])) * 0.5)
        out_x.append(xs[i])
        out_y.append(ys[i])
        out_t.append(cur_t)
        out_f.append(cur_f)
        out_c.append(confs[i])

    return out_x, out_y, out_t, out_f, out_c


def _robust_range(xs: list[float]) -> float:
    vals = [float(x) for x in xs if x is not None and x == x]
    if len(vals) < 6:
        return 0.0
    vals.sort()
    lo = vals[int(len(vals) * 0.1)]
    hi = vals[int(len(vals) * 0.9)]
    return float(max(0.0, hi - lo))


def _percentile(xs: list[float], q: float) -> float:
    vals = sorted(float(x) for x in xs if x is not None and x == x)
    if not vals:
        return 0.0
    idx = int((len(vals) - 1) * min(1.0, max(0.0, float(q))))
    return float(vals[idx])


def _local_argmax(xs: list[float], center: int, *, radius: int = 2) -> int:
    lo = max(0, center - radius)
    hi = min(len(xs) - 1, center + radius)
    best_i = lo
    best_v = xs[lo]
    for j in range(lo + 1, hi + 1):
        if xs[j] > best_v:
            best_v = xs[j]
            best_i = j
    return best_i


def _local_argmin(xs: list[float], center: int, *, radius: int = 2) -> int:
    lo = max(0, center - radius)
    hi = min(len(xs) - 1, center + radius)
    best_i = lo
    best_v = xs[lo]
    for j in range(lo + 1, hi + 1):
        if xs[j] < best_v:
            best_v = xs[j]
            best_i = j
    return best_i


def _detect_concentric_pairs(
    *,
    signal: list[float],
    times_ms: list[int],
    min_rep_ms: int,
    max_rep_ms: int,
    min_displacement_px: float,
) -> tuple[list[tuple[int, int]], str]:
    extrema_pairs = _detect_pairs_from_velocity_extrema(signal=signal, times_ms=times_ms)
    threshold_pairs = _detect_pairs_from_top_resets(
        signal=signal,
        times_ms=times_ms,
        min_rep_ms=min_rep_ms,
        max_rep_ms=max_rep_ms,
    )

    extrema_score = _count_valid_pairs(
        pairs=extrema_pairs,
        signal=signal,
        times_ms=times_ms,
        min_rep_ms=min_rep_ms,
        max_rep_ms=max_rep_ms,
        min_displacement_px=min_displacement_px,
    )
    threshold_score = _count_valid_pairs(
        pairs=threshold_pairs,
        signal=signal,
        times_ms=times_ms,
        min_rep_ms=min_rep_ms,
        max_rep_ms=max_rep_ms,
        min_displacement_px=min_displacement_px,
    )
    if threshold_score > extrema_score:
        return threshold_pairs, "top_reset"
    return extrema_pairs, "velocity_extrema"


def _detect_pairs_from_velocity_extrema(
    *,
    signal: list[float],
    times_ms: list[int],
) -> list[tuple[int, int]]:
    if len(signal) < 3:
        return []

    vels: list[float] = []
    for i in range(1, len(signal)):
        dt_ms = float(times_ms[i] - times_ms[i - 1])
        if dt_ms <= 0:
            dt_ms = 1.0
        vels.append((signal[i] - signal[i - 1]) / dt_ms)

    abs_vels = [abs(v) for v in vels if v == v]
    abs_vels.sort()
    vel_med = float(median(abs_vels)) if abs_vels else 0.0
    eps = max(0.005, vel_med * 0.2)

    extrema: list[tuple[str, int]] = []
    for i in range(1, len(vels)):
        v_prev = vels[i - 1]
        v_cur = vels[i]
        if v_prev >= eps and v_cur <= -eps:
            extrema.append(("max", _local_argmax(signal, i)))
        elif v_prev <= -eps and v_cur >= eps:
            extrema.append(("min", _local_argmin(signal, i)))

    extrema.sort(key=lambda t: t[1])
    pruned: list[tuple[str, int]] = []
    for typ, idx in extrema:
        if not pruned:
            pruned.append((typ, idx))
            continue
        if idx == pruned[-1][1]:
            continue
        if typ == pruned[-1][0]:
            prev_typ, prev_idx = pruned[-1]
            if typ == "max":
                if signal[idx] >= signal[prev_idx]:
                    pruned[-1] = (typ, idx)
            else:
                if signal[idx] <= signal[prev_idx]:
                    pruned[-1] = (typ, idx)
            continue
        pruned.append((typ, idx))

    out: list[tuple[int, int]] = []
    for a, b in zip(pruned, pruned[1:]):
        if a[0] == "max" and b[0] != "max":
            out.append((a[1], b[1]))
    return out


def _detect_pairs_from_top_resets(
    *,
    signal: list[float],
    times_ms: list[int],
    min_rep_ms: int,
    max_rep_ms: int,
) -> list[tuple[int, int]]:
    if len(signal) < 3:
        return []

    low = _percentile(signal, 0.15)
    high = _percentile(signal, 0.85)
    motion_range = max(0.0, high - low)
    if motion_range <= 1e-6:
        return []

    # Enter a rep once the bar reaches meaningful depth; finish it once the
    # bar returns to the top band again. This is more stable than relying on a
    # short negative->positive velocity flip at lockout.
    top_threshold = low + (motion_range * 0.12)
    bottom_threshold = low + (motion_range * 0.45)
    min_excursion_px = max(8.0, motion_range * 0.35)

    out: list[tuple[int, int]] = []
    active = False
    peak_i: int | None = None
    peak_v: float | None = None

    for i, v in enumerate(signal):
        if not active:
            if v >= bottom_threshold:
                active = True
                peak_i = i
                peak_v = v
            continue

        if peak_v is None or v > peak_v:
            peak_i = i
            peak_v = v

        if v > top_threshold or peak_i is None or peak_v is None:
            continue

        start_i = _local_argmax(signal, peak_i)
        end_i = _local_argmin(signal, i)
        if end_i <= start_i:
            end_i = i

        dur_ms = times_ms[end_i] - times_ms[start_i]
        disp_px = float(signal[start_i] - signal[end_i])
        if min_rep_ms <= dur_ms <= max_rep_ms and disp_px >= min_excursion_px:
            out.append((start_i, end_i))

        active = False
        peak_i = None
        peak_v = None

    return out


def _count_valid_pairs(
    *,
    pairs: list[tuple[int, int]],
    signal: list[float],
    times_ms: list[int],
    min_rep_ms: int,
    max_rep_ms: int,
    min_displacement_px: float,
) -> int:
    count = 0
    for start_i, end_i in pairs:
        if not (0 <= start_i < end_i < len(signal)):
            continue
        dur_ms = times_ms[end_i] - times_ms[start_i]
        disp_px = float(signal[start_i] - signal[end_i])
        if min_rep_ms <= dur_ms <= max_rep_ms and disp_px >= min_displacement_px:
            count += 1
    return count


def _bbox_wh_px_from_end(end: dict[str, Any]) -> tuple[float, float] | None:
    bbox = end.get("bbox")
    if not isinstance(bbox, dict):
        return None

    x1 = bbox.get("x1")
    y1 = bbox.get("y1")
    x2 = bbox.get("x2")
    y2 = bbox.get("y2")
    if not all(isinstance(v, (int, float)) for v in (x1, y1, x2, y2)):
        return None

    bw = abs(float(x2) - float(x1))
    bh = abs(float(y2) - float(y1))
    if bw <= 0 or bh <= 0:
        return None

    return bw, bh


def _rep_index_at_ms(reps: list[VbtRep], time_ms: int) -> int | None:
    for rep in reps:
        if rep.startMs <= time_ms <= rep.endMs:
            return int(rep.repIndex)
    return None


def _instant_concentric_speed_mps(
    *,
    signal: list[float],
    times_ms: list[int],
    idx: int,
    cm_per_px: float,
    direction: float,
) -> float | None:
    slopes_px_per_s: list[float] = []

    if idx > 0:
        dt_ms = times_ms[idx] - times_ms[idx - 1]
        if dt_ms > 0:
            slopes_px_per_s.append((signal[idx] - signal[idx - 1]) / (dt_ms / 1000.0))

    if idx + 1 < len(signal):
        dt_ms = times_ms[idx + 1] - times_ms[idx]
        if dt_ms > 0:
            slopes_px_per_s.append((signal[idx + 1] - signal[idx]) / (dt_ms / 1000.0))

    if not slopes_px_per_s:
        return None

    mean_slope = sum(slopes_px_per_s) / len(slopes_px_per_s)
    speed_mps = max(0.0, direction * mean_slope * float(cm_per_px) / 100.0)
    return float(speed_mps)
