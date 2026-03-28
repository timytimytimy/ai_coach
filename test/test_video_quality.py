from __future__ import annotations

import os
import sys
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from server.analysis import build_analysis_result, extract_features
from server.video.quality import build_video_quality_summary


class VideoQualityTests(unittest.TestCase):
    def test_video_quality_summary_flattens_warning_codes(self) -> None:
        summary = build_video_quality_summary(
            {
                "quality": {"usable": False, "confidence": 0.42},
                "warnings": [
                    {"code": "too_dark", "message": "画面整体偏暗，可能影响杠铃和姿态识别。"},
                    {"code": "blurry", "message": "视频清晰度偏低，关键点和杠铃边缘可能不稳定。"},
                ],
            }
        )

        self.assertFalse(summary["videoQualityUsable"])
        self.assertEqual(summary["videoQualityWarningCount"], 2)
        self.assertEqual(summary["videoQualityWarningCodes"], ["too_dark", "blurry"])

    def test_analysis_surfaces_camera_quality_warning(self) -> None:
        video_quality = {
            "quality": {
                "usable": False,
                "confidence": 0.38,
                "primaryWarning": "强背光或高光区域较多，可能导致姿态和杠铃检测漂移。",
            },
            "warnings": [
                {
                    "code": "backlit_or_overexposed",
                    "message": "强背光或高光区域较多，可能导致姿态和杠铃检测漂移。",
                }
            ],
        }
        features = extract_features(
            exercise="squat",
            barbell_result=None,
            overlay_result={"frames": []},
            vbt_result={"reps": [], "samples": []},
            phases=[],
            pose_result={"quality": {"usable": False}},
            video_quality=video_quality,
        )
        analysis = build_analysis_result(
            exercise="squat",
            features=features,
            phases=[],
            video_quality=video_quality,
        )

        self.assertFalse(features["videoQualityUsable"])
        self.assertIn("backlit_or_overexposed", features["videoQualityWarningCodes"])
        self.assertEqual(
            analysis["cameraQualityWarning"],
            "强背光或高光区域较多，可能导致姿态和杠铃检测漂移。",
        )


if __name__ == "__main__":
    unittest.main()
