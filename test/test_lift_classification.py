from __future__ import annotations

import os
import sys
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from server.video.classify_lift import (
    _analysis_exercise_for_lift_type,
    _normalize_lift_type,
)


class LiftClassificationTests(unittest.TestCase):
    def test_normalize_lift_type_aliases(self) -> None:
        self.assertEqual(_normalize_lift_type("bench press"), "bench")
        self.assertEqual(_normalize_lift_type("sumo deadlift"), "sumo_deadlift")
        self.assertEqual(_normalize_lift_type("conventional deadlift"), "deadlift")

    def test_analysis_exercise_maps_sumo_to_deadlift(self) -> None:
        self.assertEqual(_analysis_exercise_for_lift_type("sumo_deadlift"), "deadlift")
        self.assertEqual(_analysis_exercise_for_lift_type("squat"), "squat")


if __name__ == "__main__":
    unittest.main()
