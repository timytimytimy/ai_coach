from __future__ import annotations

import os
import sys
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from server.barbell.overlay import build_overlay_from_barbell


class OverlayTests(unittest.TestCase):
    def test_short_gap_is_interpolated(self) -> None:
        frames = [
            {
                "timeMs": 0,
                "plate": {
                    "tracked": False,
                    "center": {"x": 100.0, "y": 200.0},
                    "bbox": {"x1": 90.0, "y1": 190.0, "x2": 110.0, "y2": 210.0},
                    "conf": 0.8,
                },
            },
            {"timeMs": 67, "plate": None},
            {
                "timeMs": 133,
                "plate": {
                    "tracked": False,
                    "center": {"x": 106.0, "y": 212.0},
                    "bbox": {"x1": 96.0, "y1": 202.0, "x2": 116.0, "y2": 222.0},
                    "conf": 0.85,
                },
            },
        ]

        out = build_overlay_from_barbell({"frameWidth": 720, "frameHeight": 960, "frames": frames})
        gap_frame = out["frames"][1]
        self.assertIsNotNone(gap_frame["point"])
        self.assertEqual(gap_frame["segmentId"], 1)
        self.assertAlmostEqual(gap_frame["point"]["x"], 103.0, places=1)
        self.assertAlmostEqual(gap_frame["point"]["y"], 206.0, places=1)


if __name__ == "__main__":
    unittest.main()
