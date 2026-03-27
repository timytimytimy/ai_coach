from __future__ import annotations

import os
import sys
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from server.barbell.vbt import _instant_concentric_speed_mps, compute_vbt_from_barbell


class VbtScaleTests(unittest.TestCase):
    def test_detects_multiple_reps_across_brief_top_pauses(self) -> None:
        cycle = [340.0, 360.0, 430.0, 500.0, 560.0, 590.0, 555.0, 500.0, 430.0, 360.0, 340.0]
        ys = ([340.0] * 8) + (cycle * 3) + ([340.0] * 8)
        frames: list[dict[str, object]] = []
        for i, y in enumerate(ys):
            frames.append(
                {
                    "frameIndex": i,
                    "timeMs": i * 100,
                    "end": {
                        "class": 0,
                        "tracked": False,
                        "center": {"x": 10.0, "y": y},
                        "bbox": {"x1": 8.0, "y1": y - 2.0, "x2": 12.0, "y2": y + 2.0},
                        "conf": 0.9,
                    },
                }
            )

        res = compute_vbt_from_barbell({"sourceFps": 10.0, "frames": frames})

        self.assertIsInstance(res, dict)
        assert isinstance(res, dict)
        reps = res["reps"]
        self.assertEqual(len(reps), 3)
        self.assertEqual([r["repIndex"] for r in reps], [1, 2, 3])
        self.assertTrue(all(r["avgVelocityMps"] > 0.0 for r in reps))

    def test_scale_ignores_tracked_boxes(self) -> None:
        frames: list[dict[str, object]] = []

        for i in range(10):
            y = 100 - i
            frames.append(
                {
                    "frameIndex": i,
                    "timeMs": i * 100,
                    "end": {
                        "class": 0,
                        "tracked": False,
                        "center": {"x": 10.0, "y": float(y)},
                        "bbox": {"x1": 8.0, "y1": float(y - 2), "x2": 12.0, "y2": float(y + 2)},
                        "conf": 0.9,
                    },
                }
            )

        for i in range(10, 40):
            y = 90 - i
            frames.append(
                {
                    "frameIndex": i,
                    "timeMs": i * 100,
                    "end": {
                        "tracked": True,
                        "center": {"x": 10.0, "y": float(y)},
                        "bbox": {"x1": -10.0, "y1": float(y - 20), "x2": 30.0, "y2": float(y + 20)},
                        "conf": 0.0,
                    },
                }
            )

        res = compute_vbt_from_barbell({"sourceFps": 10.0, "frames": frames})

        self.assertIsInstance(res, dict)
        assert isinstance(res, dict)
        self.assertAlmostEqual(res["scaleCmPerPx"], 1.25)
        self.assertEqual(res["scaleFrom"]["chosenDiameterPx"], 4.0)
        self.assertEqual(res["motionSource"], "end")
        self.assertEqual(res["scaleSource"], "end")
        self.assertIn("samples", res)
        self.assertEqual(len(res["samples"]), 10)

    def test_instant_concentric_speed_changes_with_signal_slope(self) -> None:
        signal = [100.0, 90.0, 70.0, 68.0, 67.0]
        times_ms = [0, 100, 200, 300, 400]

        v1 = _instant_concentric_speed_mps(
            signal=signal,
            times_ms=times_ms,
            idx=1,
            cm_per_px=1.25,
            direction=-1.0,
        )
        v2 = _instant_concentric_speed_mps(
            signal=signal,
            times_ms=times_ms,
            idx=3,
            cm_per_px=1.25,
            direction=-1.0,
        )

        self.assertIsNotNone(v1)
        self.assertIsNotNone(v2)
        assert v1 is not None and v2 is not None
        self.assertGreater(v1, v2)
        self.assertGreater(v1, 0.0)
        self.assertGreaterEqual(v2, 0.0)

    def test_vbt_ignores_tracked_end_drift_when_plate_is_stable(self) -> None:
        frames: list[dict[str, object]] = []
        plate_ys = [340.0, 360.0, 390.0, 430.0, 470.0, 500.0, 520.0, 500.0, 470.0, 430.0, 390.0, 360.0, 340.0]
        drift_ys = [340.0, 360.0, 390.0, 430.0, 470.0, 520.0, 610.0, 700.0, 520.0, 330.0, 250.0, 500.0, 340.0]

        for i, (py, ey) in enumerate(zip(plate_ys, drift_ys)):
            frames.append(
                {
                    "frameIndex": i,
                    "timeMs": i * 100,
                    "plate": {
                        "class": 1,
                        "tracked": False,
                        "center": {"x": 120.0, "y": py},
                        "bbox": {"x1": 30.0, "y1": py - 90.0, "x2": 210.0, "y2": py + 90.0},
                        "conf": 0.9,
                    },
                    "end": {
                        "class": 0,
                        "tracked": False,
                        "center": {"x": 150.0, "y": ey},
                        "bbox": {"x1": 140.0, "y1": ey - 10.0, "x2": 160.0, "y2": ey + 10.0},
                        "conf": 0.9,
                    },
                }
            )

        res = compute_vbt_from_barbell({"sourceFps": 10.0, "frames": frames})

        self.assertIsInstance(res, dict)
        assert isinstance(res, dict)
        reps = res["reps"]
        self.assertEqual(len(reps), 1)
        self.assertLess(reps[0]["avgVelocityMps"], 0.6)
        self.assertGreater(reps[0]["avgVelocityMps"], 0.15)
        self.assertEqual(res["motionSource"], "plate")
        self.assertEqual(res["scaleSource"], "end")

    def test_end_scale_requires_local_support_near_rep_window(self) -> None:
        frames: list[dict[str, object]] = []
        plate_ys = ([340.0] * 8) + [340.0, 360.0, 390.0, 430.0, 470.0, 500.0, 520.0, 500.0, 470.0, 430.0, 390.0, 360.0, 340.0]

        for i, py in enumerate(plate_ys):
            frame: dict[str, object] = {
                "frameIndex": i,
                "timeMs": i * 100,
                "plate": {
                    "class": 1,
                    "tracked": False,
                    "center": {"x": 120.0, "y": py},
                    "bbox": {"x1": 30.0, "y1": py - 90.0, "x2": 210.0, "y2": py + 90.0},
                    "conf": 0.9,
                },
            }
            if i < 4:
                frame["end"] = {
                    "class": 0,
                    "tracked": False,
                    "center": {"x": 150.0, "y": 340.0 + i * 2.0},
                    "bbox": {"x1": 140.0, "y1": 330.0, "x2": 160.0, "y2": 350.0},
                    "conf": 0.95,
                }
            frames.append(frame)

        res = compute_vbt_from_barbell({"sourceFps": 10.0, "frames": frames})

        self.assertIsInstance(res, dict)
        assert isinstance(res, dict)
        self.assertEqual(len(res["reps"]), 1)
        self.assertEqual(res["motionSource"], "plate")
        self.assertEqual(res["scaleSource"], "plate")
        self.assertIn("plateDiameterCmAssumed", res)


if __name__ == "__main__":
    unittest.main()
