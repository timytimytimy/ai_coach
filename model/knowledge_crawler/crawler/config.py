from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class SourceSpec(BaseModel):
    name: str
    url: str
    lift: Literal["squat", "bench", "deadlift", "general"] = "general"
    source_type: Literal["article", "forum", "guide", "video_page", "paper", "bilibili_space", "bilibili_video"] = "article"
    tags: list[str] = Field(default_factory=list)
    max_items: int = 8


class CrawlConfig(BaseModel):
    output_dir: Path
    user_agent: str = "SmartStrengthCoachKnowledgeBot/0.1"
    timeout_sec: float = 20.0
    respect_robots: bool = True
    sources: list[SourceSpec] = Field(default_factory=list)


def load_config(path: str | Path) -> CrawlConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return CrawlConfig.model_validate(raw)
