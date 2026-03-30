from __future__ import annotations

import json
import re
from urllib.parse import urlencode, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


def discover_video_urls_from_space(html: str, *, base_url: str, limit: int) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    seen: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"]).strip()
        full = _normalize_video_url(href, base_url=base_url)
        if not full or full in seen:
            continue
        seen.add(full)
        urls.append(full)
        if len(urls) >= limit:
            return urls

    for match in re.finditer(r'"(https?://www\.bilibili\.com/video/BV[0-9A-Za-z]+[^"]*)"', html):
        full = _normalize_video_url(match.group(1), base_url=base_url)
        if not full or full in seen:
            continue
        seen.add(full)
        urls.append(full)
        if len(urls) >= limit:
            return urls

    for match in re.finditer(r'"/video/(BV[0-9A-Za-z]+[^"]*)"', html):
        full = _normalize_video_url(f"/video/{match.group(1)}", base_url=base_url)
        if not full or full in seen:
            continue
        seen.add(full)
        urls.append(full)
        if len(urls) >= limit:
            return urls
    return urls


def fetch_video_subtitles(
    *,
    html: str,
    video_url: str,
    user_agent: str,
    timeout_sec: float,
    verify: bool = True,
) -> dict[str, object]:
    bvid, cid = _extract_bvid_and_cid(html, video_url=video_url)
    if not bvid or not cid:
        return {
            "available": False,
            "reason": "missing_bvid_or_cid",
            "tracks": [],
            "transcriptText": "",
        }

    api_url = f"https://api.bilibili.com/x/player/v2?{urlencode({'bvid': bvid, 'cid': cid})}"
    headers = {
        "User-Agent": user_agent,
        "Referer": video_url,
        "Accept": "application/json,text/plain,*/*",
    }
    with httpx.Client(timeout=timeout_sec, verify=verify, headers=headers, follow_redirects=True) as client:
        response = client.get(api_url)
        response.raise_for_status()
        data = response.json()

        subtitles = (((data or {}).get("data") or {}).get("subtitle") or {}).get("subtitles") or []
        tracks: list[dict[str, object]] = []
        transcript_lines: list[str] = []

        for item in subtitles:
            if not isinstance(item, dict):
                continue
            subtitle_url = item.get("subtitle_url")
            if not isinstance(subtitle_url, str) or not subtitle_url:
                continue
            if subtitle_url.startswith("//"):
                subtitle_url = f"https:{subtitle_url}"
            sub_resp = client.get(subtitle_url)
            sub_resp.raise_for_status()
            sub_json = sub_resp.json()
            body = sub_json.get("body") if isinstance(sub_json, dict) else None
            segments: list[dict[str, object]] = []
            if isinstance(body, list):
                for seg in body:
                    if not isinstance(seg, dict):
                        continue
                    content = seg.get("content")
                    start = seg.get("from")
                    end = seg.get("to")
                    if not isinstance(content, str):
                        continue
                    segments.append(
                        {
                            "fromSec": float(start) if isinstance(start, (int, float)) else None,
                            "toSec": float(end) if isinstance(end, (int, float)) else None,
                            "content": content.strip(),
                        }
                    )
                    if content.strip():
                        transcript_lines.append(content.strip())
            tracks.append(
                {
                    "lang": item.get("lan"),
                    "langName": item.get("lan_doc"),
                    "url": subtitle_url,
                    "segments": segments,
                }
            )

    transcript_text = "\n".join(line for line in transcript_lines if line).strip()
    return {
        "available": bool(tracks),
        "bvid": bvid,
        "cid": cid,
        "tracks": tracks,
        "transcriptText": transcript_text,
    }


def build_markdown_with_transcript(*, base_markdown: str, transcript_text: str) -> str:
    if not transcript_text.strip():
        return base_markdown
    appendix = "\n\n## 自动抓取字幕 / ASR\n\n" + transcript_text.strip() + "\n"
    return (base_markdown or "").rstrip() + appendix


def _normalize_video_url(href: str, *, base_url: str) -> str | None:
    if not href:
        return None
    if href.startswith("//"):
        href = f"https:{href}"
    full = urljoin(base_url, href)
    parsed = urlparse(full)
    if parsed.netloc not in {"www.bilibili.com", "m.bilibili.com"}:
        return None
    if "/video/BV" not in parsed.path:
        return None
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def _extract_bvid_and_cid(html: str, *, video_url: str) -> tuple[str | None, int | None]:
    bvid_match = re.search(r"/video/(BV[0-9A-Za-z]+)", video_url)
    bvid = bvid_match.group(1) if bvid_match else None
    cid = None

    initial = _extract_initial_state(html)
    if isinstance(initial, dict):
        video_data = initial.get("videoData")
        if isinstance(video_data, dict):
            if not bvid and isinstance(video_data.get("bvid"), str):
                bvid = video_data.get("bvid")
            if isinstance(video_data.get("cid"), int):
                cid = int(video_data["cid"])
        if cid is None:
            pages = initial.get("videoData", {}).get("pages") if isinstance(initial.get("videoData"), dict) else None
            if isinstance(pages, list) and pages and isinstance(pages[0], dict) and isinstance(pages[0].get("cid"), int):
                cid = int(pages[0]["cid"])

    if cid is None:
        cid_match = re.search(r'"cid":\s*([0-9]+)', html)
        if cid_match:
            cid = int(cid_match.group(1))

    return bvid, cid


def _extract_initial_state(html: str) -> dict[str, object] | None:
    match = re.search(r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;\s*\(function", html, flags=re.S)
    if not match:
        match = re.search(r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;", html, flags=re.S)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(1))
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None
