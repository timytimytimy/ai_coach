from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


IssueSeverity = Literal["low", "medium", "high"]
EvidenceSource = Literal["rule", "vbt", "barbell", "pose", "fusion"]


class TimeRangeMs(BaseModel):
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class FusionIssue(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    title: str = Field(min_length=1, max_length=80)
    severity: IssueSeverity
    confidence: float = Field(ge=0.0, le=1.0)
    evidenceSource: EvidenceSource = "fusion"
    visualEvidence: list[str] = Field(default_factory=list)
    kinematicEvidence: list[str] = Field(default_factory=list)
    timeRangeMs: TimeRangeMs


class FusionCoachFeedback(BaseModel):
    focus: str = Field(min_length=1, max_length=180)
    why: str = Field(min_length=1, max_length=320)
    nextSet: str = Field(min_length=1, max_length=180)
    keepWatching: list[str] = Field(default_factory=list, max_length=3)


class FusionAnalysis(BaseModel):
    liftType: str = Field(min_length=2, max_length=32)
    confidence: float = Field(ge=0.0, le=1.0)
    issues: list[FusionIssue] = Field(min_length=1, max_length=3)
    coachFeedback: FusionCoachFeedback
    cue: str = Field(min_length=1, max_length=120)
    drills: list[str] = Field(default_factory=list, max_length=2)
    loadAdjustment: str = Field(min_length=1, max_length=64)
    cameraQualityWarning: str | None = None


def llm_response_json_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "liftType",
            "confidence",
            "issues",
            "coachFeedback",
            "cue",
            "drills",
            "loadAdjustment",
            "cameraQualityWarning",
        ],
        "properties": {
            "liftType": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "issues": {
                "type": "array",
                "minItems": 1,
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "name",
                        "title",
                        "severity",
                        "confidence",
                        "evidenceSource",
                        "visualEvidence",
                        "kinematicEvidence",
                        "timeRangeMs",
                    ],
                    "properties": {
                        "name": {"type": "string"},
                        "title": {"type": "string"},
                        "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "evidenceSource": {
                            "type": "string",
                            "enum": ["rule", "vbt", "barbell", "pose", "fusion"],
                        },
                        "visualEvidence": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "kinematicEvidence": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "timeRangeMs": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["start", "end"],
                            "properties": {
                                "start": {"type": "integer", "minimum": 0},
                                "end": {"type": "integer", "minimum": 0},
                            },
                        },
                    },
                },
            },
            "coachFeedback": {
                "type": "object",
                "additionalProperties": False,
                "required": ["focus", "why", "nextSet", "keepWatching"],
                "properties": {
                    "focus": {"type": "string"},
                    "why": {"type": "string"},
                    "nextSet": {"type": "string"},
                    "keepWatching": {
                        "type": "array",
                        "maxItems": 3,
                        "items": {"type": "string"},
                    },
                },
            },
            "cue": {"type": "string"},
            "drills": {
                "type": "array",
                "maxItems": 2,
                "items": {"type": "string"},
            },
            "loadAdjustment": {"type": "string"},
            "cameraQualityWarning": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
            },
        },
    }
