from __future__ import annotations

import os
import sys
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from server.video.preprocess import _select_keyframe_times


class VideoPreprocessTests(unittest.TestCase):
    def test_select_keyframe_times_prioritizes_issue_windows(self) -> None:
        phases = [
            {"name": "ascent", "startMs": 1000, "endMs": 2200},
            {"name": "lockout", "startMs": 2200, "endMs": 2600},
        ]
        rule = {
            "issues": [
                {"timeRangeMs": {"start": 1300, "end": 1800}},
                {"timeRangeMs": {"start": 3600, "end": 4100}},
            ]
        }
        times = _select_keyframe_times(
            duration_ms=5000,
            phases=phases,
            rule_analysis=rule,
            max_frames=6,
        )

        self.assertLessEqual(len(times), 6)
        self.assertTrue(any(1300 <= t <= 1800 for t in times))
        self.assertTrue(any(3600 <= t <= 4100 for t in times))


if __name__ == "__main__":
    unittest.main()
