from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class VideoFinalizeRequest(BaseModel):
    fps: int | None = Field(default=None, ge=1, le=240)
    width: int | None = Field(default=None, ge=1, le=10000)
    height: int | None = Field(default=None, ge=1, le=10000)
    durationMs: int | None = Field(default=None, alias="durationMs", ge=0, le=3_600_000)
    sha256: str = Field(min_length=8, max_length=128)


class WorkoutCreateRequest(BaseModel):
    day: str


class SetCreateRequest(BaseModel):
    exercise: Literal["squat", "bench", "deadlift"]
    weightKg: float | None = Field(default=None, alias="weightKg")
    repsDone: int | None = Field(default=None, alias="repsDone")
    rpe: float | None = None
    videoId: str | None = Field(default=None, alias="videoId")


class Calibration(BaseModel):
    plateDiameterMm: int | None = Field(default=None, alias="plateDiameterMm")


class AnalysisJobCreateRequest(BaseModel):
    videoSha256: str = Field(alias="videoSha256")
    calibration: Calibration | None = None
    pipelineVersion: str = Field(default="pipe-v1", alias="pipelineVersion")
    coachSoul: str | None = Field(default=None, alias="coachSoul")


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=128)
    displayName: str | None = Field(default=None, alias="displayName", max_length=64)


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class RefreshRequest(BaseModel):
    refreshToken: str = Field(alias="refreshToken", min_length=20)


class ProfileUpdateRequest(BaseModel):
    displayName: str = Field(alias="displayName", min_length=1, max_length=64)


class ChangePasswordRequest(BaseModel):
    currentPassword: str = Field(alias="currentPassword", min_length=8, max_length=128)
    newPassword: str = Field(alias="newPassword", min_length=8, max_length=128)
