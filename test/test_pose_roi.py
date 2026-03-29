from __future__ import annotations

import os
import sys
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from server.pose.pose import (
    _extract_barbell_anchors,
    _fill_short_pose_gaps,
    _pose_matches_barbell,
    _pose_roi_for_time,
    _smooth_pose_frames,
)


class PoseRoiTests(unittest.TestCase):
    def test_roi_is_symmetric_without_guessing_lifter_side(self) -> None:
        anchors = _extract_barbell_anchors(
            {
                "frames": [
                    {
                        "timeMs": 1000,
                        "plate": {
                            "center": {"x": 400.0, "y": 280.0},
                            "bbox": {"x1": 350.0, "y1": 230.0, "x2": 450.0, "y2": 330.0},
                        },
                    }
                ]
            }
        )
        roi = _pose_roi_for_time(
            anchors=anchors,
            time_ms=1000,
            frame_width=800,
            frame_height=1200,
            max_gap_ms=300,
            last_pose_center=None,
            last_pose_box=None,
        )
        self.assertIsNotNone(roi)
        assert roi is not None
        left = 400 - roi.x1
        right = roi.x2 - 400
        self.assertLess(abs(left - right), 4)
        self.assertGreater(roi.y2 - roi.y1, 700)

    def test_roi_uses_nearest_anchor_in_time(self) -> None:
        anchors = _extract_barbell_anchors(
            {
                "frames": [
                    {
                        "timeMs": 1000,
                        "plate": {
                            "center": {"x": 250.0, "y": 280.0},
                            "bbox": {"x1": 220.0, "y1": 250.0, "x2": 280.0, "y2": 310.0},
                        },
                    },
                    {
                        "timeMs": 2000,
                        "plate": {
                            "center": {"x": 520.0, "y": 280.0},
                            "bbox": {"x1": 480.0, "y1": 240.0, "x2": 560.0, "y2": 320.0},
                        },
                    },
                ]
            }
        )
        roi = _pose_roi_for_time(
            anchors=anchors,
            time_ms=1920,
            frame_width=800,
            frame_height=1200,
            max_gap_ms=250,
            last_pose_center=None,
            last_pose_box=None,
        )
        self.assertIsNotNone(roi)
        assert roi is not None
        self.assertGreater(roi.x2, 520)
        self.assertLess(roi.x1, 520)

    def test_roi_prefers_previous_pose_center_when_continuous(self) -> None:
        anchors = _extract_barbell_anchors(
            {
                "frames": [
                    {
                        "timeMs": 1000,
                        "plate": {
                            "center": {"x": 400.0, "y": 300.0},
                            "bbox": {"x1": 360.0, "y1": 260.0, "x2": 440.0, "y2": 340.0},
                        },
                    }
                ]
            }
        )
        roi = _pose_roi_for_time(
            anchors=anchors,
            time_ms=1020,
            frame_width=800,
            frame_height=1200,
            max_gap_ms=250,
            last_pose_center=(330.0, 520.0),
            last_pose_box=None,
        )
        self.assertIsNotNone(roi)
        assert roi is not None
        roi_center_x = (roi.x1 + roi.x2) / 2.0
        self.assertLess(abs(roi_center_x - 330.0), 20.0)

    def test_pose_match_rejects_person_far_from_barbell(self) -> None:
        anchor = {
            "timeMs": 1000.0,
            "cx": 420.0,
            "cy": 320.0,
            "plateWidth": 80.0,
        }
        far_keypoints = {
            "leftShoulder": {"x": 90.0, "y": 560.0},
            "rightShoulder": {"x": 130.0, "y": 560.0},
            "leftHip": {"x": 100.0, "y": 720.0},
            "rightHip": {"x": 140.0, "y": 720.0},
        }
        self.assertFalse(
            _pose_matches_barbell(
                keypoints=far_keypoints,
                anchor=anchor,
                exercise="squat",
                frame_width=720,
                frame_height=960,
            )
        )

    def test_pose_match_accepts_lifter_near_barbell(self) -> None:
        anchor = {
            "timeMs": 1000.0,
            "cx": 420.0,
            "cy": 320.0,
            "plateWidth": 80.0,
        }
        near_keypoints = {
            "leftShoulder": {"x": 360.0, "y": 360.0},
            "rightShoulder": {"x": 420.0, "y": 355.0},
            "leftHip": {"x": 380.0, "y": 500.0},
            "rightHip": {"x": 430.0, "y": 500.0},
        }
        self.assertTrue(
            _pose_matches_barbell(
                keypoints=near_keypoints,
                anchor=anchor,
                exercise="squat",
                frame_width=720,
                frame_height=960,
            )
        )

    def test_fill_short_pose_gaps_interpolates_middle_frame(self) -> None:
        frames = [
            {
                "timeMs": 0,
                "keypoints": {
                    "leftShoulder": {"x": 100.0, "y": 200.0},
                    "rightShoulder": {"x": 140.0, "y": 200.0},
                    "leftHip": {"x": 110.0, "y": 300.0},
                    "rightHip": {"x": 145.0, "y": 300.0},
                },
            },
            {"timeMs": 100, "keypoints": {}},
            {
                "timeMs": 200,
                "keypoints": {
                    "leftShoulder": {"x": 120.0, "y": 210.0},
                    "rightShoulder": {"x": 160.0, "y": 210.0},
                    "leftHip": {"x": 130.0, "y": 310.0},
                    "rightHip": {"x": 165.0, "y": 310.0},
                },
            },
        ]
        out = _fill_short_pose_gaps(frames, max_gap_frames=2)
        mid = out[1]["keypoints"]
        self.assertTrue(out[1]["interpolated"])
        self.assertAlmostEqual(mid["leftShoulder"]["x"], 110.0)
        self.assertAlmostEqual(mid["leftHip"]["y"], 305.0)

    def test_smooth_pose_frames_reduces_step_change(self) -> None:
        frames = [
            {
                "timeMs": 0,
                "keypoints": {
                    "leftShoulder": {"x": 100.0, "y": 200.0, "z": 0.0},
                },
            },
            {
                "timeMs": 100,
                "keypoints": {
                    "leftShoulder": {"x": 140.0, "y": 240.0, "z": 0.0},
                },
            },
        ]
        out = _smooth_pose_frames(frames, alpha=0.5)
        self.assertAlmostEqual(out[1]["keypoints"]["leftShoulder"]["x"], 120.0)
        self.assertAlmostEqual(out[1]["keypoints"]["leftShoulder"]["y"], 220.0)


if __name__ == "__main__":
    unittest.main()
