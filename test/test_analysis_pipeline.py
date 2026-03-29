from __future__ import annotations

import os
import sys
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from server.analysis import (
    build_analysis_result,
    build_findings_from_analysis,
    build_score_result,
    extract_features,
    segment_phases,
)


class AnalysisPipelineTests(unittest.TestCase):
    def test_phase_feature_and_analysis_skeleton_shapes(self) -> None:
        overlay = {
            "frames": [
                {"timeMs": 0, "point": {"x": 100.0, "y": 400.0}},
                {"timeMs": 100, "point": {"x": 105.0, "y": 350.0}},
                {"timeMs": 200, "point": {"x": 120.0, "y": 300.0}},
            ]
        }
        vbt = {
            "scaleCmPerPx": 0.1,
            "reps": [
                {
                    "repIndex": 1,
                    "timeRangeMs": {"start": 1000, "end": 2200},
                    "avgVelocityMps": 0.32,
                }
            ],
            "samples": [
                {"timeMs": 1000, "repIndex": 1, "speedMps": 0.12},
                {"timeMs": 1200, "repIndex": 1, "speedMps": 0.45},
                {"timeMs": 1400, "repIndex": 1, "speedMps": 0.18},
                {"timeMs": 1600, "repIndex": 1, "speedMps": 0.17},
                {"timeMs": 1800, "repIndex": 1, "speedMps": 0.33},
            ],
            "motionSource": "plate",
            "scaleSource": "plate",
        }
        phases = segment_phases(exercise="squat", overlay_result=overlay, vbt_result=vbt)
        features = extract_features(
            exercise="squat",
            barbell_result=None,
            overlay_result=overlay,
            vbt_result=vbt,
            phases=phases,
            pose_result={"quality": {"usable": False}},
        )
        analysis = build_analysis_result(exercise="squat", features=features, phases=phases)

        self.assertGreaterEqual(len(phases), 4)
        self.assertEqual(features["repCount"], 1)
        self.assertIn("repSummaries", features)
        self.assertIn("issues", analysis)
        self.assertEqual(analysis["liftType"], "squat")
        self.assertLessEqual(len(analysis["issues"]), 3)
        self.assertEqual(analysis["issues"][0]["title"], "起立速度偏慢")

    def test_squat_rules_surface_sticking_and_drift(self) -> None:
        phases = [
            {"name": "ascent", "repIndex": 1, "startMs": 1000, "endMs": 2200},
        ]
        features = {
            "avgRepVelocityMps": 0.34,
            "velocityLossPct": 18.0,
            "repSummaries": [
                {
                    "repIndex": 1,
                    "timeRangeMs": {"start": 1000, "end": 2200},
                    "avgVelocityMps": 0.34,
                    "barPathDriftCm": 7.4,
                    "stickingRegion": {"startMs": 1400, "endMs": 1700, "durationMs": 300},
                }
            ],
        }

        analysis = build_analysis_result(exercise="squat", features=features, phases=phases)

        names = [issue["name"] for issue in analysis["issues"]]
        self.assertIn("slow_concentric_speed", names)
        self.assertIn("bar_path_drift", names)
        self.assertIn("mid_ascent_sticking_point", names)

    def test_squat_rules_surface_consistency_and_recommendation(self) -> None:
        phases = [
            {"name": "ascent", "repIndex": 1, "startMs": 1000, "endMs": 2200},
        ]
        features = {
            "avgRepVelocityMps": 0.33,
            "velocityLossPct": 22.0,
            "repVelocityCvPct": 14.5,
            "repSummaries": [
                {
                    "repIndex": 1,
                    "timeRangeMs": {"start": 1000, "end": 2600},
                    "avgVelocityMps": 0.33,
                    "durationMs": 1600,
                    "barPathDriftCm": 4.0,
                    "stickingRegion": None,
                },
                {
                    "repIndex": 2,
                    "timeRangeMs": {"start": 3000, "end": 4700},
                    "avgVelocityMps": 0.28,
                    "durationMs": 1700,
                    "barPathDriftCm": 4.8,
                    "stickingRegion": None,
                },
            ],
        }

        analysis = build_analysis_result(exercise="squat", features=features, phases=phases)
        names = [issue["name"] for issue in analysis["issues"]]
        self.assertIn("grindy_ascent", names)
        self.assertIn("rep_to_rep_velocity_drop", names)
        self.assertIn("pause squat", analysis["drills"])
        self.assertEqual(analysis["loadAdjustment"], "next_set_minus_5_percent")

    def test_findings_are_derived_from_analysis_issues(self) -> None:
        analysis = {
            "issues": [
                {
                    "name": "slow_concentric_speed",
                    "severity": "medium",
                    "confidence": 0.76,
                    "timeRangeMs": {"start": 1000, "end": 2200},
                }
            ]
        }
        features = {"repCount": 3}
        top3, all_findings = build_findings_from_analysis(
            analysis=analysis,
            features=features,
        )

        self.assertEqual(len(top3), 1)
        self.assertEqual(len(all_findings), 1)
        self.assertEqual(top3[0]["label"], "slow_concentric_speed")
        self.assertEqual(top3[0]["labelDisplay"], "起立速度偏慢")
        self.assertEqual(top3[0]["severity"], "medium")

    def test_pose_features_surface_torso_shift_signal(self) -> None:
        overlay = {"frames": []}
        vbt = {
            "scaleCmPerPx": 0.1,
            "reps": [
                {
                    "repIndex": 1,
                    "timeRangeMs": {"start": 1000, "end": 2200},
                    "avgVelocityMps": 0.42,
                }
            ],
            "samples": [],
        }
        phases = segment_phases(exercise="squat", overlay_result=overlay, vbt_result=vbt)
        pose = {
            "quality": {"usable": True},
            "primarySide": "left",
            "keypoints": [
                {
                    "timeMs": 1100,
                    "keypoints": {
                        "leftShoulder": {"x": 100.0, "y": 120.0},
                        "leftHip": {"x": 102.0, "y": 220.0},
                        "leftKnee": {"x": 110.0, "y": 320.0},
                        "leftAnkle": {"x": 116.0, "y": 420.0},
                    },
                },
                {
                    "timeMs": 1600,
                    "keypoints": {
                        "leftShoulder": {"x": 170.0, "y": 120.0},
                        "leftHip": {"x": 110.0, "y": 220.0},
                        "leftKnee": {"x": 120.0, "y": 320.0},
                        "leftAnkle": {"x": 126.0, "y": 420.0},
                    },
                },
            ],
        }

        features = extract_features(
            exercise="squat",
            barbell_result=None,
            overlay_result=overlay,
            vbt_result=vbt,
            phases=phases,
            pose_result=pose,
        )
        analysis = build_analysis_result(exercise="squat", features=features, phases=phases)

        self.assertGreater(float(features["avgTorsoLeanDeltaDeg"]), 12.0)
        torso_issue = next(
            issue for issue in analysis["issues"] if issue["name"] == "torso_position_shift"
        )
        self.assertEqual(torso_issue["evidenceSource"], "pose")

    def test_pose_summary_keeps_joint_quality_and_trusted_coverage(self) -> None:
        overlay = {"frames": []}
        vbt = {
            "scaleCmPerPx": 0.1,
            "reps": [
                {
                    "repIndex": 1,
                    "timeRangeMs": {"start": 1000, "end": 2200},
                    "avgVelocityMps": 0.42,
                }
            ],
            "samples": [],
        }
        phases = segment_phases(exercise="squat", overlay_result=overlay, vbt_result=vbt)
        pose = {
            "quality": {
                "usable": True,
                "jointQuality": {
                    "leftAnkle": {"trustedCoverage": 0.72},
                    "rightAnkle": {"trustedCoverage": 0.31},
                    "leftWrist": {"trustedCoverage": 0.81},
                },
            },
            "primarySide": "left",
            "keypoints": [
                {
                    "timeMs": 1100,
                    "keypoints": {
                        "leftShoulder": {"x": 100.0, "y": 120.0, "trusted": True},
                        "leftHip": {"x": 102.0, "y": 220.0, "trusted": True},
                        "leftKnee": {"x": 110.0, "y": 320.0, "trusted": True},
                        "leftAnkle": {"x": 116.0, "y": 420.0, "trusted": True},
                    },
                },
            ],
        }

        features = extract_features(
            exercise="squat",
            barbell_result=None,
            overlay_result=overlay,
            vbt_result=vbt,
            phases=phases,
            pose_result=pose,
        )
        self.assertEqual(features["trustedAnkleCoverage"], 0.72)
        self.assertEqual(features["trustedWristCoverage"], 0.81)
        self.assertIn("leftAnkle", features["poseJointQuality"])

    def test_deadlift_pose_features_surface_torso_and_hip_metrics(self) -> None:
        overlay = {"frames": []}
        vbt = {
            "scaleCmPerPx": 0.1,
            "reps": [
                {
                    "repIndex": 1,
                    "timeRangeMs": {"start": 1000, "end": 2200},
                    "avgVelocityMps": 0.31,
                }
            ],
            "samples": [],
        }
        phases = segment_phases(exercise="deadlift", overlay_result=overlay, vbt_result=vbt)
        pose = {
            "quality": {"usable": True},
            "primarySide": "left",
            "keypoints": [
                {
                    "timeMs": 1100,
                    "keypoints": {
                        "leftShoulder": {"x": 180.0, "y": 110.0, "trusted": True},
                        "leftHip": {"x": 120.0, "y": 220.0, "trusted": True},
                        "leftKnee": {"x": 118.0, "y": 320.0, "trusted": True},
                        "leftAnkle": {"x": 122.0, "y": 420.0, "trusted": True},
                    },
                },
                {
                    "timeMs": 1800,
                    "keypoints": {
                        "leftShoulder": {"x": 145.0, "y": 108.0, "trusted": True},
                        "leftHip": {"x": 122.0, "y": 220.0, "trusted": True},
                        "leftKnee": {"x": 121.0, "y": 320.0, "trusted": True},
                        "leftAnkle": {"x": 123.0, "y": 420.0, "trusted": True},
                    },
                },
            ],
        }

        features = extract_features(
            exercise="deadlift",
            barbell_result=None,
            overlay_result=overlay,
            vbt_result=vbt,
            phases=phases,
            pose_result=pose,
        )
        self.assertIsNotNone(features["maxTorsoLeanDeg"])
        self.assertIsNotNone(features["minHipAngleDeg"])
        analysis = build_analysis_result(exercise="deadlift", features=features, phases=phases)
        self.assertIn(
            "deadlift_tension_preset_failure",
            [issue["name"] for issue in analysis["issues"]],
        )

    def test_deadlift_pose_rules_surface_lockout_signal(self) -> None:
        phases = [
            {"name": "pull", "repIndex": 1, "startMs": 1000, "endMs": 2200},
            {"name": "lockout", "repIndex": 1, "startMs": 2200, "endMs": 2600},
        ]
        features = {
            "repSummaries": [
                {
                    "repIndex": 1,
                    "timeRangeMs": {"start": 1000, "end": 2600},
                    "avgVelocityMps": 0.36,
                    "durationMs": 1600,
                    "endTorsoLeanDeg": 21.5,
                    "stickingRegion": None,
                }
            ],
        }
        analysis = build_analysis_result(exercise="deadlift", features=features, phases=phases)
        self.assertIn(
            "lockout_rounding",
            [issue["name"] for issue in analysis["issues"]],
        )

    def test_bench_pose_features_surface_elbow_and_wrist_stack(self) -> None:
        overlay = {"frames": []}
        vbt = {
            "scaleCmPerPx": 0.1,
            "reps": [
                {
                    "repIndex": 1,
                    "timeRangeMs": {"start": 1000, "end": 2200},
                    "avgVelocityMps": 0.25,
                }
            ],
            "samples": [],
        }
        phases = segment_phases(exercise="bench", overlay_result=overlay, vbt_result=vbt)
        pose = {
            "quality": {"usable": True},
            "primarySide": "left",
            "keypoints": [
                {
                    "timeMs": 1100,
                    "keypoints": {
                        "leftShoulder": {"x": 180.0, "y": 200.0, "trusted": True},
                        "leftElbow": {"x": 220.0, "y": 240.0, "trusted": True},
                        "leftWrist": {"x": 245.0, "y": 275.0, "trusted": True},
                        "leftHip": {"x": 130.0, "y": 250.0, "trusted": True},
                        "leftKnee": {"x": 120.0, "y": 330.0, "trusted": True},
                    },
                },
            ],
        }

        features = extract_features(
            exercise="bench",
            barbell_result=None,
            overlay_result=overlay,
            vbt_result=vbt,
            phases=phases,
            pose_result=pose,
        )
        self.assertIsNotNone(features["minElbowAngleDeg"])
        self.assertIsNotNone(features["avgWristStackOffsetPx"])
        analysis = build_analysis_result(exercise="bench", features=features, phases=phases)
        self.assertIn(
            "bench_wrist_stack_break",
            [issue["name"] for issue in analysis["issues"]],
        )
        self.assertIn(
            "bench_elbow_flare_mismatch",
            [issue["name"] for issue in analysis["issues"]],
        )

    def test_squat_pose_rules_surface_foot_stability_signal(self) -> None:
        phases = [
            {"name": "descent", "repIndex": 1, "startMs": 1000, "endMs": 1800},
            {"name": "ascent", "repIndex": 1, "startMs": 1800, "endMs": 2600},
        ]
        features = {
            "trustedAnkleCoverage": 0.78,
            "repSummaries": [
                {
                    "repIndex": 1,
                    "timeRangeMs": {"start": 1000, "end": 2600},
                    "avgVelocityMps": 0.41,
                    "durationMs": 1600,
                    "barPathDriftCm": 6.2,
                    "stickingRegion": None,
                }
            ],
        }

        analysis = build_analysis_result(exercise="squat", features=features, phases=phases)
        self.assertIn(
            "unstable_foot_pressure",
            [issue["name"] for issue in analysis["issues"]],
        )

    def test_squat_pose_rules_surface_forward_shift_signal(self) -> None:
        phases = [
            {"name": "ascent", "repIndex": 1, "startMs": 1800, "endMs": 2600},
        ]
        features = {
            "trustedAnkleCoverage": 0.7,
            "repSummaries": [
                {
                    "repIndex": 1,
                    "timeRangeMs": {"start": 1000, "end": 2600},
                    "avgVelocityMps": 0.39,
                    "durationMs": 1600,
                    "barPathDriftCm": 8.1,
                    "torsoLeanDeltaDeg": 11.8,
                    "stickingRegion": None,
                }
            ],
        }

        analysis = build_analysis_result(exercise="squat", features=features, phases=phases)
        self.assertIn(
            "forward_weight_shift",
            [issue["name"] for issue in analysis["issues"]],
        )

    def test_score_result_surfaces_rep_and_overall_scores(self) -> None:
        features = {
            "repSummaries": [
                {
                    "repIndex": 1,
                    "timeRangeMs": {"start": 1000, "end": 2100},
                    "avgVelocityMps": 0.46,
                    "durationMs": 1100,
                    "barPathDriftCm": 1.8,
                    "stickingRegion": None,
                },
                {
                    "repIndex": 2,
                    "timeRangeMs": {"start": 3100, "end": 4700},
                    "avgVelocityMps": 0.33,
                    "durationMs": 1600,
                    "barPathDriftCm": 6.8,
                    "stickingRegion": {"startMs": 3600, "endMs": 3920, "durationMs": 320},
                },
            ]
        }
        analysis = {
            "confidence": 0.76,
            "issues": [
                {
                    "name": "slow_concentric_speed",
                    "title": "起立速度偏慢",
                    "evidenceSource": "vbt",
                    "severity": "medium",
                    "timeRangeMs": {"start": 3100, "end": 4700},
                }
            ],
        }
        video_quality = {"quality": {"usable": True, "confidence": 0.88}}

        score = build_score_result(
            exercise="squat",
            features=features,
            analysis=analysis,
            video_quality=video_quality,
        )

        self.assertEqual(score["bestRepIndex"], 1)
        self.assertEqual(score["weakestRepIndex"], 2)
        self.assertIsInstance(score["overall"], int)
        self.assertEqual(len(score["reps"]), 2)
        self.assertGreater(score["reps"][0]["score"], score["reps"][1]["score"])
        self.assertIn("speedRhythm", score["reps"][0]["dimensions"])

    def test_score_result_does_not_deduct_pose_issues_directly(self) -> None:
        features = {
            "repSummaries": [
                {
                    "repIndex": 1,
                    "timeRangeMs": {"start": 1000, "end": 2100},
                    "avgVelocityMps": 0.42,
                    "durationMs": 1150,
                    "barPathDriftCm": 2.2,
                    "stickingRegion": None,
                }
            ]
        }
        analysis = {
            "confidence": 0.7,
            "issues": [
                {
                    "name": "torso_position_shift",
                    "title": "起立时躯干角度变化偏大",
                    "evidenceSource": "pose",
                    "severity": "medium",
                    "timeRangeMs": {"start": 1000, "end": 2100},
                }
            ],
        }

        score = build_score_result(
            exercise="squat",
            features=features,
            analysis=analysis,
            video_quality={"quality": {"usable": True, "confidence": 0.9}},
        )

        rep = score["reps"][0]
        self.assertGreaterEqual(rep["dimensions"]["technicalExecution"], 95)
        self.assertFalse(any(reason["label"] == "起立时躯干角度变化偏大" for reason in rep["reasons"]))


if __name__ == "__main__":
    unittest.main()
