from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from server import accel


class AccelTests(unittest.TestCase):
    def tearDown(self) -> None:
        accel.has_torch_mps.cache_clear()
        accel.has_onnx_coreml.cache_clear()

    def test_default_yolo_device_prefers_mps_on_apple_silicon(self) -> None:
        with mock.patch("server.accel.is_apple_silicon", return_value=True), mock.patch(
            "server.accel.has_torch_mps", return_value=True
        ):
            self.assertEqual(accel.default_yolo_device(), "mps")

    def test_default_yolo_device_falls_back_to_cpu(self) -> None:
        with mock.patch("server.accel.is_apple_silicon", return_value=False):
            self.assertEqual(accel.default_yolo_device(), "cpu")

    def test_default_rtmpose_device_prefers_coreml_on_apple_silicon(self) -> None:
        with mock.patch("server.accel.is_apple_silicon", return_value=True), mock.patch(
            "server.accel.has_onnx_coreml", return_value=True
        ):
            self.assertEqual(accel.default_rtmpose_device(), "mps")

    def test_explicit_env_overrides_auto_detection(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"SSC_YOLO_DEVICE": "cpu", "SSC_RTMPOSE_DEVICE": "cpu", "SSC_RTMPOSE_BACKEND": "onnxruntime"},
            clear=False,
        ):
            self.assertEqual(accel.default_yolo_device(), "cpu")
            self.assertEqual(accel.default_rtmpose_device(), "cpu")
            self.assertEqual(accel.default_rtmpose_backend(), "onnxruntime")


if __name__ == "__main__":
    unittest.main()
