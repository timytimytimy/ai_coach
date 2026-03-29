from __future__ import annotations

import re
from dataclasses import dataclass

import trafilatura
from bs4 import BeautifulSoup


@dataclass
class ParsedDocument:
    title: str
    markdown: str
    excerpt: str
    headings: list[str]


def parse_document(html: str, *, fallback_title: str) -> ParsedDocument:
    markdown = trafilatura.extract(
        html,
        output_format="markdown",
        include_links=True,
        include_tables=False,
        favor_precision=True,
    )
    soup = BeautifulSoup(html, "html.parser")
    title = _pick_title(soup, fallback_title=fallback_title)
    headings = [
        node.get_text(" ", strip=True)
        for node in soup.find_all(re.compile("^h[1-3]$"))
        if node.get_text(" ", strip=True)
    ][:20]
    clean_markdown = (markdown or "").strip()
    excerpt = _build_excerpt(clean_markdown)
    return ParsedDocument(
        title=title,
        markdown=clean_markdown,
        excerpt=excerpt,
        headings=headings,
    )


def _pick_title(soup: BeautifulSoup, *, fallback_title: str) -> str:
    if soup.title and soup.title.get_text(strip=True):
        return soup.title.get_text(strip=True)
    h1 = soup.find("h1")
    if h1 and h1.get_text(" ", strip=True):
        return h1.get_text(" ", strip=True)
    return fallback_title


def _build_excerpt(markdown: str) -> str:
    text = re.sub(r"\s+", " ", markdown).strip()
    return text[:220]
