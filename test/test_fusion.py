from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from server.fusion import build_fused_analysis


class FusionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_key = os.environ.pop("OPENAI_API_KEY", None)
        self._old_flag = os.environ.pop("SSC_LLM_ANALYSIS", None)
        self._old_model = os.environ.pop("SSC_LLM_MODEL", None)

    def tearDown(self) -> None:
        self._restore("OPENAI_API_KEY", self._old_key)
        self._restore("SSC_LLM_ANALYSIS", self._old_flag)
        self._restore("SSC_LLM_MODEL", self._old_model)

    def _restore(self, key: str, value: str | None) -> None:
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    def test_fusion_falls_back_to_rules_when_disabled(self) -> None:
        rule_analysis = {
            "liftType": "squat",
            "confidence": 0.72,
            "issues": [
                {
                    "name": "slow_concentric_speed",
                    "title": "起立速度偏慢",
                    "severity": "medium",
                    "confidence": 0.72,
                    "evidenceSource": "vbt",
                    "visualEvidence": ["起立速度偏慢"],
                    "kinematicEvidence": ["平均速度 0.34 m/s"],
                    "timeRangeMs": {"start": 1000, "end": 2000},
                }
            ],
            "cue": "持续加速",
            "drills": ["pause squat"],
            "loadAdjustment": "next_set_minus_5_percent",
            "cameraQualityWarning": None,
        }

        analysis, meta = build_fused_analysis(
            exercise="squat",
            features={},
            phases=[],
            pose_result=None,
            video_quality=None,
            rule_analysis=rule_analysis,
        )

        self.assertEqual(analysis["source"], "rules")
        self.assertEqual(analysis["issues"][0]["name"], "slow_concentric_speed")
        self.assertFalse(meta["used"])

    def test_fusion_uses_llm_payload_when_available(self) -> None:
        os.environ["OPENAI_API_KEY"] = "test-key"
        os.environ["SSC_LLM_ANALYSIS"] = "1"
        os.environ["SSC_LLM_MODEL"] = "test-model"

        rule_analysis = {
            "liftType": "squat",
            "confidence": 0.72,
            "issues": [
                {
                    "name": "slow_concentric_speed",
                    "title": "起立速度偏慢",
                    "severity": "medium",
                    "confidence": 0.72,
                    "evidenceSource": "vbt",
                    "visualEvidence": ["起立速度偏慢"],
                    "kinematicEvidence": ["平均速度 0.34 m/s"],
                    "timeRangeMs": {"start": 1000, "end": 2000},
                }
            ],
            "cue": "持续加速",
            "drills": ["pause squat"],
            "loadAdjustment": "next_set_minus_5_percent",
            "cameraQualityWarning": None,
        }

        fake_payload = {
            "liftType": "squat",
            "confidence": 0.81,
            "issues": [
                {
                    "name": "mid_ascent_sticking_point",
                    "title": "起立中段卡顿",
                    "severity": "medium",
                    "confidence": 0.79,
                    "evidenceSource": "vbt",
                    "visualEvidence": ["中段速度明显掉下来"],
                    "kinematicEvidence": ["低速区持续约 280 ms"],
                    "timeRangeMs": {"start": 1300, "end": 1700},
                }
            ],
            "cue": "触底后继续向上推地",
            "drills": ["pause squat", "tempo squat"],
            "loadAdjustment": "hold_load_and_repeat_if_form_breaks",
            "cameraQualityWarning": None,
        }

        with patch(
            "server.fusion.llm._call_openai_chat",
            return_value=(fake_payload, {"latencyMs": 123, "usage": {"promptTokens": 10, "completionTokens": 5, "totalTokens": 15}}),
        ):
            analysis, meta = build_fused_analysis(
                exercise="squat",
                features={"repCount": 3},
                phases=[],
                pose_result=None,
                video_quality=None,
                rule_analysis=rule_analysis,
            )

        self.assertEqual(analysis["source"], "llm")
        self.assertEqual(analysis["issues"][0]["title"], "起立中段卡顿")
        self.assertEqual(meta["used"], True)
        self.assertEqual(meta["model"], "test-model")

    def test_fusion_merges_duplicate_ascent_speed_issues(self) -> None:
        os.environ["OPENAI_API_KEY"] = "test-key"
        os.environ["SSC_LLM_ANALYSIS"] = "1"

        rule_analysis = {
            "liftType": "squat",
            "confidence": 0.72,
            "issues": [],
            "cue": "持续加速",
            "drills": ["pause squat"],
            "loadAdjustment": "next_set_minus_5_percent",
            "cameraQualityWarning": None,
        }

        fake_payload = {
            "liftType": "squat",
            "confidence": 0.81,
            "issues": [
                {
                    "name": "slow_concentric_speed",
                    "title": "起立速度偏慢",
                    "severity": "medium",
                    "confidence": 0.76,
                    "evidenceSource": "fusion",
                    "visualEvidence": ["起立节奏偏慢"],
                    "kinematicEvidence": ["平均速度 0.339 m/s"],
                    "timeRangeMs": {"start": 36900, "end": 38467},
                },
                {
                    "name": "grindy_ascent",
                    "title": "起立过程过于吃力",
                    "severity": "medium",
                    "confidence": 0.74,
                    "evidenceSource": "fusion",
                    "visualEvidence": ["整次 rep 发力吃力"],
                    "kinematicEvidence": ["持续 1567 ms"],
                    "timeRangeMs": {"start": 36900, "end": 38467},
                },
            ],
            "cue": "持续加速",
            "drills": ["pause squat"],
            "loadAdjustment": "next_set_minus_5_percent",
            "cameraQualityWarning": None,
        }

        with patch(
            "server.fusion.llm._call_openai_chat",
            return_value=(fake_payload, {"latencyMs": 123, "usage": {"promptTokens": 10, "completionTokens": 5, "totalTokens": 15}}),
        ):
            analysis, meta = build_fused_analysis(
                exercise="squat",
                features={},
                phases=[],
                pose_result=None,
                video_quality=None,
                rule_analysis=rule_analysis,
            )

        self.assertTrue(meta["used"])
        self.assertEqual(len(analysis["issues"]), 1)
        self.assertEqual(analysis["issues"][0]["name"], "slow_concentric_speed")
        self.assertIn("持续 1.6s", analysis["issues"][0]["kinematicEvidence"])

    def test_fusion_maps_handbook_style_names_to_stable_taxonomy(self) -> None:
        os.environ["OPENAI_API_KEY"] = "test-key"
        os.environ["SSC_LLM_ANALYSIS"] = "1"

        rule_analysis = {
            "liftType": "squat",
            "confidence": 0.72,
            "issues": [],
            "cue": "持续加速",
            "drills": ["pause squat"],
            "loadAdjustment": "next_set_minus_5_percent",
            "cameraQualityWarning": None,
        }

        fake_payload = {
            "liftType": "squat",
            "confidence": 0.8,
            "issues": [
                {
                    "name": "butt_wink_like_issue",
                    "title": "底部骨盆眨眼明显",
                    "severity": "medium",
                    "confidence": 0.75,
                    "evidenceSource": "fusion",
                    "visualEvidence": ["底部骨盆后倾明显"],
                    "kinematicEvidence": ["腰椎曲度变化较大"],
                    "timeRangeMs": {"start": 1200, "end": 1700},
                }
            ],
            "cue": "下蹲时保持骨盆中立",
            "drills": ["pause squat"],
            "loadAdjustment": "hold_load",
            "cameraQualityWarning": None,
        }

        with patch(
            "server.fusion.llm._call_openai_chat",
            return_value=(fake_payload, {"latencyMs": 123, "usage": {"promptTokens": 10, "completionTokens": 5, "totalTokens": 15}}),
        ):
            analysis, meta = build_fused_analysis(
                exercise="squat",
                features={},
                phases=[],
                pose_result=None,
                video_quality=None,
                rule_analysis=rule_analysis,
            )

        self.assertTrue(meta["used"])
        self.assertEqual(analysis["issues"][0]["name"], "pelvic_wink")
        self.assertEqual(analysis["issues"][0]["title"], "底部骨盆眨眼")

    def test_fusion_binds_recommendations_to_taxonomy(self) -> None:
        os.environ["OPENAI_API_KEY"] = "test-key"
        os.environ["SSC_LLM_ANALYSIS"] = "1"

        rule_analysis = {
            "liftType": "squat",
            "confidence": 0.72,
            "issues": [],
            "cue": "持续加速",
            "drills": ["pause squat"],
            "loadAdjustment": "next_set_minus_5_percent",
            "cameraQualityWarning": None,
        }

        fake_payload = {
            "liftType": "squat",
            "confidence": 0.8,
            "issues": [
                {
                    "name": "bar_path_issue",
                    "title": "杠铃路径飘了",
                    "severity": "medium",
                    "confidence": 0.74,
                    "evidenceSource": "fusion",
                    "visualEvidence": ["杠铃路径向前漂"],
                    "kinematicEvidence": ["横向漂移 7.2 cm"],
                    "timeRangeMs": {"start": 1300, "end": 1800},
                }
            ],
            "cue": "说得很长很散的一句建议，不够稳定，也不想直接拿来给用户看",
            "drills": ["架上蹲", "节奏深蹲"],
            "loadAdjustment": "some_random_policy",
            "cameraQualityWarning": None,
        }

        with patch(
            "server.fusion.llm._call_openai_chat",
            return_value=(fake_payload, {"latencyMs": 123, "usage": {"promptTokens": 10, "completionTokens": 5, "totalTokens": 15}}),
        ):
            analysis, meta = build_fused_analysis(
                exercise="squat",
                features={},
                phases=[],
                pose_result=None,
                video_quality=None,
                rule_analysis=rule_analysis,
            )

        self.assertTrue(meta["used"])
        self.assertEqual(analysis["issues"][0]["name"], "bar_path_drift")
        self.assertEqual(analysis["cue"], "全程把杠稳在中足上方，起立时不要让杠向前跑")
        self.assertEqual(analysis["drills"], ["pin squat", "tempo squat"])
        self.assertEqual(
            analysis["loadAdjustment"], "hold_load_and_repeat_if_form_breaks"
        )

    def test_fusion_maps_bench_arch_issue_to_structured_taxonomy(self) -> None:
        os.environ["OPENAI_API_KEY"] = "test-key"
        os.environ["SSC_LLM_ANALYSIS"] = "1"

        rule_analysis = {
            "liftType": "bench",
            "confidence": 0.7,
            "issues": [],
            "cue": "桥和上背先固定住",
            "drills": ["paused bench"],
            "loadAdjustment": "hold_load",
            "cameraQualityWarning": None,
        }

        fake_payload = {
            "liftType": "bench",
            "confidence": 0.79,
            "issues": [
                {
                    "name": "arch_collapse_like_issue",
                    "title": "桥塌得比较明显",
                    "severity": "medium",
                    "confidence": 0.74,
                    "evidenceSource": "fusion",
                    "visualEvidence": ["离心到底时桥高度明显掉下去"],
                    "kinematicEvidence": ["当前项目暂无直接量化"],
                    "timeRangeMs": {"start": 1100, "end": 1900},
                }
            ],
            "cue": "随便说一句",
            "drills": ["paused bench"],
            "loadAdjustment": "some_random_policy",
            "cameraQualityWarning": None,
        }

        with patch(
            "server.fusion.llm._call_openai_chat",
            return_value=(fake_payload, {"latencyMs": 123, "usage": {"promptTokens": 10, "completionTokens": 5, "totalTokens": 15}}),
        ):
            analysis, meta = build_fused_analysis(
                exercise="bench",
                features={},
                phases=[],
                pose_result=None,
                video_quality=None,
                rule_analysis=rule_analysis,
            )

        self.assertTrue(meta["used"])
        self.assertEqual(analysis["issues"][0]["name"], "bench_arch_collapse")
        self.assertEqual(analysis["issues"][0]["title"], "桥塌陷")
        self.assertEqual(analysis["cue"], "保持胸骨抬高，让桥在离心和推起中都不被压塌")

    def test_fusion_maps_deadlift_tension_issue_to_structured_taxonomy(self) -> None:
        os.environ["OPENAI_API_KEY"] = "test-key"
        os.environ["SSC_LLM_ANALYSIS"] = "1"

        rule_analysis = {
            "liftType": "deadlift",
            "confidence": 0.7,
            "issues": [],
            "cue": "启动前先接住杠",
            "drills": ["paused deadlift"],
            "loadAdjustment": "hold_load",
            "cameraQualityWarning": None,
        }

        fake_payload = {
            "liftType": "deadlift",
            "confidence": 0.78,
            "issues": [
                {
                    "name": "setup_tension_problem",
                    "title": "启动前张力不足",
                    "severity": "medium",
                    "confidence": 0.73,
                    "evidenceSource": "fusion",
                    "visualEvidence": ["抓住杠就直接拉，启动前没有接住杠铃"],
                    "kinematicEvidence": ["当前项目暂无直接量化"],
                    "timeRangeMs": {"start": 400, "end": 900},
                }
            ],
            "cue": "随便说一句",
            "drills": ["setup tension drill", "paused deadlift"],
            "loadAdjustment": "some_random_policy",
            "cameraQualityWarning": None,
        }

        with patch(
            "server.fusion.llm._call_openai_chat",
            return_value=(fake_payload, {"latencyMs": 123, "usage": {"promptTokens": 10, "completionTokens": 5, "totalTokens": 15}}),
        ):
            analysis, meta = build_fused_analysis(
                exercise="deadlift",
                features={},
                phases=[],
                pose_result=None,
                video_quality=None,
                rule_analysis=rule_analysis,
            )

        self.assertTrue(meta["used"])
        self.assertEqual(
            analysis["issues"][0]["name"], "deadlift_tension_preset_failure"
        )
        self.assertEqual(analysis["issues"][0]["title"], "启动前张力预设不足")
        self.assertEqual(
            analysis["cue"], "拉之前先把自己和杠连成一个整体，再让杠离地"
        )

    def test_fusion_maps_bench_uncontrolled_descent_to_structured_taxonomy(self) -> None:
        os.environ["OPENAI_API_KEY"] = "test-key"
        os.environ["SSC_LLM_ANALYSIS"] = "1"

        rule_analysis = {
            "liftType": "bench",
            "confidence": 0.7,
            "issues": [],
            "cue": "先把桥和上背固定住",
            "drills": ["paused bench"],
            "loadAdjustment": "hold_load",
            "cameraQualityWarning": None,
        }

        fake_payload = {
            "liftType": "bench",
            "confidence": 0.79,
            "issues": [
                {
                    "name": "bench_descent_problem",
                    "title": "卧推动作里下放不受控",
                    "severity": "medium",
                    "confidence": 0.74,
                    "evidenceSource": "fusion",
                    "visualEvidence": ["杠下放太快，触胸前还在修路线"],
                    "kinematicEvidence": ["当前项目暂无直接量化"],
                    "timeRangeMs": {"start": 1100, "end": 1900},
                }
            ],
            "cue": "随便说一句",
            "drills": ["paused bench"],
            "loadAdjustment": "some_random_policy",
            "cameraQualityWarning": None,
        }

        with patch(
            "server.fusion.llm._call_openai_chat",
            return_value=(fake_payload, {"latencyMs": 123, "usage": {"promptTokens": 10, "completionTokens": 5, "totalTokens": 15}}),
        ):
            analysis, meta = build_fused_analysis(
                exercise="bench",
                features={},
                phases=[],
                pose_result=None,
                video_quality=None,
                rule_analysis=rule_analysis,
            )

        self.assertTrue(meta["used"])
        self.assertEqual(analysis["issues"][0]["name"], "bench_uncontrolled_descent")
        self.assertEqual(analysis["issues"][0]["title"], "卧推离心不受控")
        self.assertEqual(
            analysis["cue"], "先把下放节奏控住，让杠稳定落到同一个触胸点，再去追求更快的推起"
        )

    def test_fusion_maps_sumo_abduction_issue_to_structured_taxonomy(self) -> None:
        os.environ["OPENAI_API_KEY"] = "test-key"
        os.environ["SSC_LLM_ANALYSIS"] = "1"

        rule_analysis = {
            "liftType": "deadlift",
            "confidence": 0.7,
            "issues": [],
            "cue": "先把身体和杠接上",
            "drills": ["sumo wedge drill"],
            "loadAdjustment": "hold_load",
            "cameraQualityWarning": None,
        }

        fake_payload = {
            "liftType": "deadlift",
            "confidence": 0.78,
            "issues": [
                {
                    "name": "sumo_external_rotation_problem",
                    "title": "外展打开不足，做得像宽站传统拉",
                    "severity": "medium",
                    "confidence": 0.73,
                    "evidenceSource": "fusion",
                    "visualEvidence": ["膝和髋没有真正打开，动作像宽站传统拉"],
                    "kinematicEvidence": ["当前项目暂无直接量化"],
                    "timeRangeMs": {"start": 400, "end": 900},
                }
            ],
            "cue": "随便说一句",
            "drills": ["sumo wedge drill", "bulgarian split squat"],
            "loadAdjustment": "some_random_policy",
            "cameraQualityWarning": None,
        }

        with patch(
            "server.fusion.llm._call_openai_chat",
            return_value=(fake_payload, {"latencyMs": 123, "usage": {"promptTokens": 10, "completionTokens": 5, "totalTokens": 15}}),
        ):
            analysis, meta = build_fused_analysis(
                exercise="deadlift",
                features={},
                phases=[],
                pose_result=None,
                video_quality=None,
                rule_analysis=rule_analysis,
            )

        self.assertTrue(meta["used"])
        self.assertEqual(analysis["issues"][0]["name"], "sumo_abduction_disconnect")
        self.assertEqual(
            analysis["issues"][0]["title"], "外展打开不足，导致相扑像宽站传统拉"
        )

    def test_fusion_maps_squat_knee_track_issue_to_structured_taxonomy(self) -> None:
        os.environ["OPENAI_API_KEY"] = "test-key"
        os.environ["SSC_LLM_ANALYSIS"] = "1"

        rule_analysis = {
            "liftType": "squat",
            "confidence": 0.71,
            "issues": [],
            "cue": "脚踩稳、膝跟脚尖同向",
            "drills": ["tempo squat"],
            "loadAdjustment": "hold_load",
            "cameraQualityWarning": None,
        }

        fake_payload = {
            "liftType": "squat",
            "confidence": 0.8,
            "issues": [
                {
                    "name": "knee_cave_pattern",
                    "title": "膝轨迹控制不足，触底后膝往里收",
                    "severity": "medium",
                    "confidence": 0.75,
                    "evidenceSource": "fusion",
                    "visualEvidence": ["触底后膝盖明显往里收"],
                    "kinematicEvidence": ["当前项目暂无直接量化"],
                    "timeRangeMs": {"start": 1500, "end": 2300},
                }
            ],
            "cue": "随便说一句",
            "drills": ["tempo squat", "box squat"],
            "loadAdjustment": "random_policy",
            "cameraQualityWarning": None,
        }

        with patch(
            "server.fusion.llm._call_openai_chat",
            return_value=(fake_payload, {"latencyMs": 123, "usage": {"promptTokens": 10, "completionTokens": 5, "totalTokens": 15}}),
        ):
            analysis, meta = build_fused_analysis(
                exercise="squat",
                features={},
                phases=[],
                pose_result=None,
                video_quality=None,
                rule_analysis=rule_analysis,
            )

        self.assertTrue(meta["used"])
        self.assertEqual(analysis["issues"][0]["name"], "squat_knee_track_collapse")
        self.assertEqual(analysis["issues"][0]["title"], "膝轨迹控制不足")

    def test_fusion_maps_deadlift_shrug_issue_to_structured_taxonomy(self) -> None:
        os.environ["OPENAI_API_KEY"] = "test-key"
        os.environ["SSC_LLM_ANALYSIS"] = "1"

        rule_analysis = {
            "liftType": "deadlift",
            "confidence": 0.7,
            "issues": [],
            "cue": "先把髋锁定做干净",
            "drills": ["overload lockout work"],
            "loadAdjustment": "hold_load",
            "cameraQualityWarning": None,
        }

        fake_payload = {
            "liftType": "deadlift",
            "confidence": 0.78,
            "issues": [
                {
                    "name": "shruggy_lockout",
                    "title": "锁定耸肩，手臂代偿明显",
                    "severity": "medium",
                    "confidence": 0.73,
                    "evidenceSource": "fusion",
                    "visualEvidence": ["锁定阶段明显耸肩并用手臂补动作"],
                    "kinematicEvidence": ["当前项目暂无直接量化"],
                    "timeRangeMs": {"start": 400, "end": 900},
                }
            ],
            "cue": "随便说一句",
            "drills": ["overload lockout work", "banded deadlift"],
            "loadAdjustment": "some_random_policy",
            "cameraQualityWarning": None,
        }

        with patch(
            "server.fusion.llm._call_openai_chat",
            return_value=(fake_payload, {"latencyMs": 123, "usage": {"promptTokens": 10, "completionTokens": 5, "totalTokens": 15}}),
        ):
            analysis, meta = build_fused_analysis(
                exercise="deadlift",
                features={},
                phases=[],
                pose_result=None,
                video_quality=None,
                rule_analysis=rule_analysis,
            )

        self.assertTrue(meta["used"])
        self.assertEqual(analysis["issues"][0]["name"], "deadlift_shrug_arm_takeover")
        self.assertEqual(analysis["issues"][0]["title"], "锁定耸肩，手臂代偿")

    def test_fusion_restricts_drills_to_exercise_candidate_pool(self) -> None:
        os.environ["OPENAI_API_KEY"] = "test-key"
        os.environ["SSC_LLM_ANALYSIS"] = "1"

        rule_analysis = {
            "liftType": "bench",
            "confidence": 0.7,
            "issues": [],
            "cue": "桥和上背先固定住",
            "drills": ["paused bench"],
            "loadAdjustment": "hold_load",
            "cameraQualityWarning": None,
        }

        fake_payload = {
            "liftType": "bench",
            "confidence": 0.79,
            "issues": [
                {
                    "name": "bench_arch_collapse",
                    "title": "桥塌陷",
                    "severity": "medium",
                    "confidence": 0.74,
                    "evidenceSource": "fusion",
                    "visualEvidence": ["离心到底时桥高度明显掉下去"],
                    "kinematicEvidence": ["当前项目暂无直接量化"],
                    "timeRangeMs": {"start": 1100, "end": 1900},
                }
            ],
            "cue": "随便说一句",
            "drills": ["pause squat", "pin squat"],
            "loadAdjustment": "some_random_policy",
            "cameraQualityWarning": None,
        }

        with patch(
            "server.fusion.llm._call_openai_chat",
            return_value=(fake_payload, {"latencyMs": 123, "usage": {"promptTokens": 10, "completionTokens": 5, "totalTokens": 15}}),
        ):
            analysis, meta = build_fused_analysis(
                exercise="bench",
                features={},
                phases=[],
                pose_result=None,
                video_quality=None,
                rule_analysis=rule_analysis,
            )

        self.assertTrue(meta["used"])
        self.assertEqual(analysis["issues"][0]["name"], "bench_arch_collapse")
        self.assertEqual(analysis["drills"], ["paused bench", "spoto press"])

    def test_fusion_maps_squat_hip_shoot_issue_to_structured_taxonomy(self) -> None:
        os.environ["OPENAI_API_KEY"] = "test-key"
        os.environ["SSC_LLM_ANALYSIS"] = "1"

        rule_analysis = {
            "liftType": "squat",
            "confidence": 0.71,
            "issues": [],
            "cue": "先把胸背撑住",
            "drills": ["pause squat"],
            "loadAdjustment": "hold_load",
            "cameraQualityWarning": None,
        }

        fake_payload = {
            "liftType": "squat",
            "confidence": 0.8,
            "issues": [
                {
                    "name": "good_morning_squat",
                    "title": "起立像先抬屁股再站起来",
                    "severity": "medium",
                    "confidence": 0.75,
                    "evidenceSource": "fusion",
                    "visualEvidence": ["触底后臀部先明显上抬"],
                    "kinematicEvidence": ["躯干角度变化偏大"],
                    "timeRangeMs": {"start": 1500, "end": 2300},
                }
            ],
            "cue": "说得很散的一句建议",
            "drills": ["pause squat", "box squat"],
            "loadAdjustment": "random_policy",
            "cameraQualityWarning": None,
        }

        with patch(
            "server.fusion.llm._call_openai_chat",
            return_value=(fake_payload, {"latencyMs": 123, "usage": {"promptTokens": 10, "completionTokens": 5, "totalTokens": 15}}),
        ):
            analysis, meta = build_fused_analysis(
                exercise="squat",
                features={},
                phases=[],
                pose_result=None,
                video_quality=None,
                rule_analysis=rule_analysis,
            )

        self.assertTrue(meta["used"])
        self.assertEqual(analysis["issues"][0]["name"], "hip_shoot_in_squat")
        self.assertEqual(analysis["issues"][0]["title"], "深蹲起立先抬臀")
        self.assertEqual(
            analysis["cue"], "触底时先把胸口和背撑住，让髋膝一起向上展开"
        )

    def test_fusion_preserves_full_screening_checklist(self) -> None:
        os.environ["OPENAI_API_KEY"] = "test-key"
        os.environ["SSC_LLM_ANALYSIS"] = "1"

        rule_analysis = {
            "liftType": "squat",
            "confidence": 0.71,
            "issues": [],
            "cue": "先把胸背撑住",
            "drills": ["pause squat"],
            "loadAdjustment": "hold_load",
            "cameraQualityWarning": None,
        }

        fake_payload = {
            "liftType": "squat",
            "confidence": 0.8,
            "screeningChecklist": [
                {
                    "code": "slow_concentric_speed",
                    "title": "起立速度偏慢",
                    "visualAssessment": "present",
                    "structuredAssessment": "present",
                    "finalAssessment": "present",
                    "confidence": 0.82,
                    "reason": "最后两次明显变慢",
                    "evidenceSource": "vbt",
                },
                {
                    "code": "pelvic_wink",
                    "title": "底部骨盆眨眼",
                    "visualAssessment": "possible",
                    "structuredAssessment": "not_supported",
                    "finalAssessment": "possible",
                    "confidence": 0.42,
                    "reason": "机位和遮挡限制，证据偏弱",
                    "evidenceSource": "pose",
                },
            ],
            "issues": [
                {
                    "name": "slow_concentric_speed",
                    "title": "起立速度偏慢",
                    "severity": "medium",
                    "confidence": 0.75,
                    "evidenceSource": "fusion",
                    "visualEvidence": ["最后两次起立更慢"],
                    "kinematicEvidence": ["平均速度下降"],
                    "timeRangeMs": {"start": 1500, "end": 2300},
                }
            ],
            "cue": "说得很散的一句建议",
            "drills": ["pause squat"],
            "loadAdjustment": "random_policy",
            "cameraQualityWarning": None,
        }

        with patch(
            "server.fusion.llm._call_openai_chat",
            return_value=(fake_payload, {"latencyMs": 123, "usage": {"promptTokens": 10, "completionTokens": 5, "totalTokens": 15}}),
        ):
            analysis, meta = build_fused_analysis(
                exercise="squat",
                features={},
                phases=[],
                pose_result=None,
                video_quality=None,
                rule_analysis=rule_analysis,
            )

        self.assertEqual(analysis["source"], "llm")
        self.assertTrue(meta["used"])
        checklist = meta["screeningChecklist"]
        self.assertTrue(any(item["code"] == "slow_concentric_speed" and item["status"] == "present" for item in checklist))
        self.assertTrue(any(item["code"] == "pelvic_wink" and item["status"] == "possible" for item in checklist))
        self.assertTrue(any(item["code"] == "bar_path_drift" and item["status"] == "not_supported" for item in checklist))
        self.assertTrue(
            any(
                item["code"] == "pelvic_wink"
                and item["visualAssessment"] == "possible"
                and item["structuredAssessment"] == "not_supported"
                and item["finalAssessment"] == "possible"
                for item in checklist
            )
        )
        self.assertEqual(meta["screeningSummary"]["total"], len(checklist))
        self.assertEqual(meta["screeningSummary"]["present"], 1)
        self.assertEqual(meta["screeningSummary"]["possible"], 1)
        self.assertEqual(meta["requestMetrics"]["usage"]["totalTokens"], 15)

    def test_fusion_backfills_screening_reason_and_confidence_when_missing(self) -> None:
        os.environ["OPENAI_API_KEY"] = "test-key"
        os.environ["SSC_LLM_ANALYSIS"] = "1"

        rule_analysis = {
            "liftType": "squat",
            "confidence": 0.71,
            "issues": [],
            "cue": "先把胸背撑住",
            "drills": ["pause squat"],
            "loadAdjustment": "hold_load",
            "cameraQualityWarning": None,
        }

        fake_payload = {
            "liftType": "squat",
            "confidence": 0.8,
            "screeningChecklist": [
                {
                    "code": "slow_concentric_speed",
                    "visualAssessment": "present",
                    "structuredAssessment": "present",
                    "finalAssessment": "present",
                    "evidenceSource": "vbt",
                },
                {
                    "code": "forward_weight_shift",
                    "visualAssessment": "possible",
                    "structuredAssessment": "not_supported",
                    "finalAssessment": "possible",
                    "evidenceSource": "fusion",
                },
            ],
            "issues": [
                {
                    "name": "slow_concentric_speed",
                    "title": "起立速度偏慢",
                    "severity": "medium",
                    "confidence": 0.75,
                    "evidenceSource": "fusion",
                    "visualEvidence": ["最后两次起立更慢"],
                    "kinematicEvidence": ["平均速度下降"],
                    "timeRangeMs": {"start": 1500, "end": 2300},
                }
            ],
            "cue": "说得很散的一句建议",
            "drills": ["pause squat"],
            "loadAdjustment": "random_policy",
            "cameraQualityWarning": None,
        }

        with patch(
            "server.fusion.llm._call_openai_chat",
            return_value=(fake_payload, {"latencyMs": 123, "usage": {"promptTokens": 10, "completionTokens": 5, "totalTokens": 15}}),
        ):
            _, meta = build_fused_analysis(
                exercise="squat",
                features={},
                phases=[],
                pose_result=None,
                video_quality=None,
                rule_analysis=rule_analysis,
            )

        checklist = meta["screeningChecklist"]
        slow = next(item for item in checklist if item["code"] == "slow_concentric_speed")
        shift = next(item for item in checklist if item["code"] == "forward_weight_shift")
        pelvic = next(item for item in checklist if item["code"] == "pelvic_wink")

        self.assertGreater(slow["confidence"], 0.7)
        self.assertIn("结构化证据也支持", slow["reason"])
        self.assertGreater(shift["confidence"], 0.5)
        self.assertIn("继续观察", shift["reason"])
        self.assertLess(pelvic["confidence"], 0.3)
        self.assertIn("暂时无法稳定判断", pelvic["reason"])


if __name__ == "__main__":
    unittest.main()
