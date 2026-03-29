from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from server import pose


class PoseSelectorTests(unittest.TestCase):
    def test_default_impl_is_mediapipe(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SSC_POSE_IMPL", None)
            self.assertEqual(pose.get_pose_impl(), "mediapipe")

    def test_rtmpose_aliases_route_to_v2(self) -> None:
        for value in ("rtmpose", "rtmpose_v2", "v2"):
            with self.subTest(value=value):
                with mock.patch.dict(os.environ, {"SSC_POSE_IMPL": value}, clear=False):
                    self.assertEqual(pose.get_pose_impl(), "rtmpose")

    def test_infer_pose_dispatches_to_selected_backend(self) -> None:
        payload = {
            "video_path": "/tmp/demo.mp4",
            "exercise": "squat",
            "duration_ms": 1000,
            "barbell_result": None,
        }
        with mock.patch.dict(os.environ, {"SSC_POSE_IMPL": "rtmpose"}, clear=False):
            with mock.patch("server.pose.infer_pose_v2", return_value={"quality": {"model": "rtmpose"}}) as rt, mock.patch(
                "server.pose.infer_pose_mediapipe", return_value={"quality": {"model": "mediapipe"}}
            ) as mp:
                result = pose.infer_pose(**payload)
                self.assertEqual(result["quality"]["model"], "rtmpose")
                rt.assert_called_once()
                mp.assert_not_called()

        with mock.patch.dict(os.environ, {"SSC_POSE_IMPL": "mediapipe"}, clear=False):
            with mock.patch("server.pose.infer_pose_v2", return_value={"quality": {"model": "rtmpose"}}) as rt, mock.patch(
                "server.pose.infer_pose_mediapipe", return_value={"quality": {"model": "mediapipe"}}
            ) as mp:
                result = pose.infer_pose(**payload)
                self.assertEqual(result["quality"]["model"], "mediapipe")
                mp.assert_called_once()
                rt.assert_not_called()


if __name__ == "__main__":
    unittest.main()
