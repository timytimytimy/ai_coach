from __future__ import annotations

import os
import sys
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from server.pose.pose_v2 import _map_rtmpose_person, _score_pose_candidate


class PoseV2Tests(unittest.TestCase):
    def test_map_rtmpose_person_keeps_core_body_points(self) -> None:
        person_points = [
            [10.0, 20.0],  # nose
            [0.0, 0.0],
            [0.0, 0.0],
            [0.0, 0.0],
            [0.0, 0.0],
            [30.0, 40.0],  # leftShoulder
            [50.0, 40.0],  # rightShoulder
            [28.0, 60.0],  # leftElbow
            [54.0, 60.0],  # rightElbow
            [25.0, 80.0],  # leftWrist
            [57.0, 80.0],  # rightWrist
            [34.0, 100.0],  # leftHip
            [48.0, 100.0],  # rightHip
            [34.0, 140.0],  # leftKnee
            [48.0, 140.0],  # rightKnee
            [34.0, 180.0],  # leftAnkle
            [48.0, 180.0],  # rightAnkle
        ]
        scores = [0.9] * 17

        mapped = _map_rtmpose_person(
            person_points=person_points,
            person_scores=scores,
            min_score=0.3,
            offset_x=100,
            offset_y=200,
        )

        self.assertIn("leftShoulder", mapped)
        self.assertIn("rightHip", mapped)
        self.assertEqual(mapped["nose"]["x"], 110.0)
        self.assertEqual(mapped["leftAnkle"]["y"], 380.0)

    def test_score_pose_candidate_prefers_anchor_and_previous_center_alignment(self) -> None:
        anchor = {"cx": 420.0, "cy": 320.0, "plateWidth": 80.0}
        last_pose_center = (390.0, 470.0)
        near = {
            "leftShoulder": {"x": 365.0, "y": 360.0, "visibility": 0.9},
            "rightShoulder": {"x": 425.0, "y": 356.0, "visibility": 0.9},
            "leftHip": {"x": 380.0, "y": 500.0, "visibility": 0.9},
            "rightHip": {"x": 430.0, "y": 500.0, "visibility": 0.9},
        }
        far = {
            "leftShoulder": {"x": 120.0, "y": 580.0, "visibility": 0.9},
            "rightShoulder": {"x": 180.0, "y": 580.0, "visibility": 0.9},
            "leftHip": {"x": 130.0, "y": 720.0, "visibility": 0.9},
            "rightHip": {"x": 190.0, "y": 720.0, "visibility": 0.9},
        }

        self.assertGreater(
            _score_pose_candidate(
                keypoints=near,
                anchor=anchor,
                last_pose_center=last_pose_center,
            ),
            _score_pose_candidate(
                keypoints=far,
                anchor=anchor,
                last_pose_center=last_pose_center,
            ),
        )


if __name__ == "__main__":
    unittest.main()
