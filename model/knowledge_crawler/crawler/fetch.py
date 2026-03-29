from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx


@dataclass
class FetchResult:
    url: str
    final_url: str
    status_code: int
    content_type: str
    html: str


def is_allowed_by_robots(url: str, *, user_agent: str) -> bool:
    parsed = urlparse(url)
    robots_url = urljoin(f"{parsed.scheme}://{parsed.netloc}", "/robots.txt")
    parser = RobotFileParser()
    try:
        parser.set_url(robots_url)
        parser.read()
        return parser.can_fetch(user_agent, url)
    except Exception:
        return True


def fetch_html(
    url: str,
    *,
    user_agent: str,
    timeout_sec: float,
    verify: bool = True,
) -> FetchResult:
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    with httpx.Client(
        follow_redirects=True,
        timeout=timeout_sec,
        verify=verify,
        headers=headers,
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        return FetchResult(
            url=url,
            final_url=str(response.url),
            status_code=response.status_code,
            content_type=content_type,
            html=response.text,
        )
