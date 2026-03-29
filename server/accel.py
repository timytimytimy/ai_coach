from __future__ import annotations

import os
import platform
import sys
from functools import lru_cache


def is_apple_silicon() -> bool:
    return sys.platform == "darwin" and platform.machine().lower() in {"arm64", "aarch64"}


@lru_cache(maxsize=1)
def has_torch_mps() -> bool:
    try:
        import torch  # type: ignore
    except Exception:
        return False
    try:
        return bool(torch.backends.mps.is_available())
    except Exception:
        return False


@lru_cache(maxsize=1)
def has_onnx_coreml() -> bool:
    try:
        import onnxruntime as ort  # type: ignore
    except Exception:
        return False
    try:
        return "CoreMLExecutionProvider" in ort.get_available_providers()
    except Exception:
        return False


def default_yolo_device() -> str:
    explicit = os.environ.get("SSC_YOLO_DEVICE")
    if explicit:
        return explicit
    if is_apple_silicon() and has_torch_mps():
        return "mps"
    return "cpu"


def default_rtmpose_backend() -> str:
    explicit = os.environ.get("SSC_RTMPOSE_BACKEND")
    if explicit:
        return explicit
    return "onnxruntime"


def default_rtmpose_device() -> str:
    explicit = os.environ.get("SSC_RTMPOSE_DEVICE")
    if explicit:
        return explicit
    if is_apple_silicon() and has_onnx_coreml():
        return "mps"
    return "cpu"


def mediapipe_runtime_device() -> str:
    explicit = os.environ.get("SSC_MEDIAPIPE_DEVICE")
    if explicit:
        return explicit
    return "cpu"


def mediapipe_runtime_note() -> str:
    if is_apple_silicon():
        return "mediapipe python falls back to cpu on macOS; no direct MPS path in current pipeline"
    return "cpu"
