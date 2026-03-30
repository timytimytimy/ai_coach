from __future__ import annotations

from pathlib import Path
from typing import Any

from .bilibili import (
    build_markdown_with_transcript,
    discover_video_urls_from_space,
    fetch_video_subtitles,
)
from .config import CrawlConfig
from .fetch import fetch_html, is_allowed_by_robots
from .parse import parse_document
from .store import write_document


def run_crawl(config: CrawlConfig) -> list[dict[str, Any]]:
    output_dir = Path(config.output_dir)
    results: list[dict[str, Any]] = []

    for source in config.sources:
        if config.respect_robots and not is_allowed_by_robots(
            source.url,
            user_agent=config.user_agent,
        ):
            results.append(
                {
                    "name": source.name,
                    "url": source.url,
                    "status": "skipped_robots",
                }
            )
            continue

        if source.source_type == "bilibili_space":
            results.extend(
                _crawl_bilibili_space(
                    output_dir=output_dir,
                    source=source,
                    user_agent=config.user_agent,
                    timeout_sec=config.timeout_sec,
                )
            )
            continue

        results.append(
            _crawl_single_source(
                output_dir=output_dir,
                source_name=source.name,
                url=source.url,
                source_type=source.source_type,
                lift=source.lift,
                tags=source.tags,
                user_agent=config.user_agent,
                timeout_sec=config.timeout_sec,
            )
        )
    return results


def _crawl_bilibili_space(
    *,
    output_dir: Path,
    source: Any,
    user_agent: str,
    timeout_sec: float,
) -> list[dict[str, Any]]:
    fetched = fetch_html(
        source.url,
        user_agent=user_agent,
        timeout_sec=timeout_sec,
    )
    video_urls = discover_video_urls_from_space(
        fetched.html,
        base_url=fetched.final_url,
        limit=max(1, int(getattr(source, "max_items", 8))),
    )
    results: list[dict[str, Any]] = [
        {
            "name": source.name,
            "url": fetched.final_url,
            "status": "discovered",
            "discoveredCount": len(video_urls),
        }
    ]
    for index, video_url in enumerate(video_urls, start=1):
        child_name = f"{source.name}-video-{index:02d}"
        results.append(
            _crawl_single_source(
                output_dir=output_dir,
                source_name=child_name,
                url=video_url,
                source_type="bilibili_video",
                lift=source.lift,
                tags=list(source.tags),
                user_agent=user_agent,
                timeout_sec=timeout_sec,
            )
        )
    return results


def _crawl_single_source(
    *,
    output_dir: Path,
    source_name: str,
    url: str,
    source_type: str,
    lift: str,
    tags: list[str],
    user_agent: str,
    timeout_sec: float,
) -> dict[str, Any]:
    fetched = fetch_html(
        url,
        user_agent=user_agent,
        timeout_sec=timeout_sec,
    )
    parsed = parse_document(fetched.html, fallback_title=source_name)
    subtitles: dict[str, object] | None = None
    markdown = parsed.markdown

    if source_type == "bilibili_video":
        subtitles = fetch_video_subtitles(
            html=fetched.html,
            video_url=fetched.final_url,
            user_agent=user_agent,
            timeout_sec=timeout_sec,
        )
        transcript_text = subtitles.get("transcriptText") if isinstance(subtitles, dict) else ""
        if isinstance(transcript_text, str) and transcript_text.strip():
            markdown = build_markdown_with_transcript(
                base_markdown=markdown,
                transcript_text=transcript_text,
            )

    payload = {
        "name": source_name,
        "url": fetched.final_url,
        "sourceType": source_type,
        "lift": lift,
        "tags": tags,
        "title": parsed.title,
        "excerpt": parsed.excerpt,
        "headings": parsed.headings,
        "markdown": markdown,
        "statusCode": fetched.status_code,
        "contentType": fetched.content_type,
        "subtitles": subtitles,
    }
    written = write_document(
        output_dir=output_dir,
        source_name=source_name,
        payload=payload,
    )
    return {
        "name": source_name,
        "url": fetched.final_url,
        "status": "ok",
        "subtitleAvailable": bool(isinstance(subtitles, dict) and subtitles.get("available")),
        **written,
    }
