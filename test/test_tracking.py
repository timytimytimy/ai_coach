from __future__ import annotations

import math
import os
import sys
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from server.barbell.tracking import PlateTracker, _TrackState
from server.barbell.types import DetectedBox, Point2D


def _plate_box(*, x: float, y: float, w: float, h: float, conf: float) -> DetectedBox:
    return DetectedBox(
        cls=1,
        conf=conf,
        xyxy=(x - w / 2.0, y - h / 2.0, x + w / 2.0, y + h / 2.0),
    )


def _end_box(*, x: float, y: float, w: float, h: float, conf: float) -> DetectedBox:
    return DetectedBox(
        cls=0,
        conf=conf,
        xyxy=(x - w / 2.0, y - h / 2.0, x + w / 2.0, y + h / 2.0),
    )


def _unpack_step_result(res: object) -> tuple[DetectedBox | None, Point2D | None, object | None]:
    assert isinstance(res, tuple)
    if len(res) == 2:
        return res[0], res[1], None
    return res[0], res[1], res[2]


class TrackingTests(unittest.TestCase):
    def test_plate_tracker_prefers_gap_over_far_reassociation(self) -> None:
        tracker = PlateTracker(
            state=_TrackState(pos=Point2D(481.2, 585.3), vel=Point2D(0.0, 0.0), miss=0),
            area_ema=128.0 * 168.0,
            wh_ema=(128.0, 168.0),
        )
        far_static_plate = _plate_box(x=627.8, y=381.3, w=77.0, h=121.0, conf=0.53)

        det, pos, bbox = _unpack_step_result(
            tracker.step(
                dets=[far_static_plate],
                w=720,
                h=960,
                diag=math.hypot(720.0, 960.0),
                dt=1.0 / 6.0,
            )
        )

        self.assertIsNone(det)
        self.assertIsNotNone(pos)
        assert pos is not None
        self.assertAlmostEqual(pos.x, 481.2)
        self.assertAlmostEqual(pos.y, 585.3)
        self.assertIsNotNone(bbox)

    def test_plate_tracker_keeps_near_candidate_when_far_distractor_exists(self) -> None:
        tracker = PlateTracker(
            state=_TrackState(pos=Point2D(481.2, 585.3), vel=Point2D(0.0, 0.0), miss=0),
            area_ema=128.0 * 168.0,
            wh_ema=(128.0, 168.0),
        )
        near_plate = _plate_box(x=501.1, y=542.3, w=127.5, h=169.9, conf=0.40)
        far_static_plate = _plate_box(x=627.8, y=381.3, w=77.0, h=121.0, conf=0.53)

        det, pos, _ = _unpack_step_result(
            tracker.step(
                dets=[near_plate, far_static_plate],
                w=720,
                h=960,
                diag=math.hypot(720.0, 960.0),
                dt=1.0 / 6.0,
            )
        )

        self.assertEqual(det, near_plate)
        self.assertIsNotNone(pos)
        assert pos is not None
        self.assertLess(abs(pos.x - near_plate.center.x), 25.0)
        self.assertLess(abs(pos.y - near_plate.center.y), 25.0)

    def test_plate_tracker_prefers_plate_with_nearby_end_on_initial_pick(self) -> None:
        tracker = PlateTracker(
            state=_TrackState(pos=None, vel=Point2D(0.0, 0.0), miss=0),
            area_ema=None,
            wh_ema=None,
        )
        paired_plate = _plate_box(x=320.0, y=520.0, w=120.0, h=120.0, conf=0.56)
        nearby_end = _end_box(x=372.0, y=520.0, w=34.0, h=34.0, conf=0.62)
        distractor_plate = _plate_box(x=600.0, y=380.0, w=126.0, h=126.0, conf=0.81)

        det, pos, _ = _unpack_step_result(
            tracker.step(
                dets=[paired_plate, nearby_end, distractor_plate],
                w=720,
                h=960,
                diag=math.hypot(720.0, 960.0),
                dt=1.0 / 6.0,
            )
        )

        self.assertEqual(det, paired_plate)
        self.assertIsNotNone(pos)
        assert pos is not None
        self.assertAlmostEqual(pos.x, paired_plate.center.x)
        self.assertAlmostEqual(pos.y, paired_plate.center.y)

    def test_plate_tracker_keeps_gap_on_far_reacquisition_without_end_support(self) -> None:
        tracker = PlateTracker(
            state=_TrackState(pos=Point2D(371.0, 402.0), vel=Point2D(0.0, 0.0), miss=8),
            area_ema=128.0 * 168.0,
            wh_ema=(128.0, 168.0),
        )
        far_plate = _plate_box(x=532.0, y=519.0, w=146.0, h=174.0, conf=0.58)

        det, pos, bbox = _unpack_step_result(
            tracker.step(
                dets=[far_plate],
                w=720,
                h=960,
                diag=math.hypot(720.0, 960.0),
                dt=1.0 / 15.0,
            )
        )

        self.assertIsNone(det)
        self.assertIsNotNone(pos)
        self.assertIsNotNone(bbox)
        assert pos is not None
        self.assertLess(abs(pos.x - 371.0), 1.0)
        self.assertLess(abs(pos.y - 402.0), 1.0)

    def test_plate_tracker_allows_near_reacquisition_without_end_support(self) -> None:
        tracker = PlateTracker(
            state=_TrackState(pos=Point2D(371.0, 402.0), vel=Point2D(0.0, 120.0), miss=3),
            area_ema=128.0 * 168.0,
            wh_ema=(128.0, 168.0),
        )
        near_plate = _plate_box(x=392.0, y=520.0, w=136.0, h=170.0, conf=0.66)

        det, pos, _ = _unpack_step_result(
            tracker.step(
                dets=[near_plate],
                w=720,
                h=960,
                diag=math.hypot(720.0, 960.0),
                dt=1.0 / 15.0,
            )
        )

        self.assertEqual(det, near_plate)
        self.assertIsNotNone(pos)
        assert pos is not None
        self.assertGreater(pos.y, 450.0)


if __name__ == "__main__":
    unittest.main()
