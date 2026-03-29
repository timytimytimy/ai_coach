from __future__ import annotations

from pathlib import Path
from typing import Any

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

        fetched = fetch_html(
            source.url,
            user_agent=config.user_agent,
            timeout_sec=config.timeout_sec,
        )
        parsed = parse_document(fetched.html, fallback_title=source.name)
        payload = {
            "name": source.name,
            "url": fetched.final_url,
            "sourceType": source.source_type,
            "lift": source.lift,
            "tags": source.tags,
            "title": parsed.title,
            "excerpt": parsed.excerpt,
            "headings": parsed.headings,
            "markdown": parsed.markdown,
            "statusCode": fetched.status_code,
            "contentType": fetched.content_type,
        }
        written = write_document(
            output_dir=output_dir,
            source_name=source.name,
            payload=payload,
        )
        results.append(
            {
                "name": source.name,
                "url": fetched.final_url,
                "status": "ok",
                **written,
            }
        )
    return results
