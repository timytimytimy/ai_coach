from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any


def ensure_output_dirs(base_dir: Path) -> dict[str, Path]:
    raw_dir = base_dir / "raw"
    md_dir = base_dir / "markdown"
    raw_dir.mkdir(parents=True, exist_ok=True)
    md_dir.mkdir(parents=True, exist_ok=True)
    return {
        "raw": raw_dir,
        "markdown": md_dir,
        "index": base_dir / "index.jsonl",
    }


def write_document(
    *,
    output_dir: Path,
    source_name: str,
    payload: dict[str, Any],
) -> dict[str, str]:
    paths = ensure_output_dirs(output_dir)
    slug = _slugify(source_name)
    raw_path = paths["raw"] / f"{slug}.json"
    md_path = paths["markdown"] / f"{slug}.md"

    raw_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_path.write_text(payload["markdown"], encoding="utf-8")

    index_record = {
        "id": sha256(payload["url"].encode("utf-8")).hexdigest()[:16],
        "sourceName": source_name,
        "url": payload["url"],
        "title": payload["title"],
        "lift": payload["lift"],
        "sourceType": payload["sourceType"],
        "tags": payload["tags"],
        "markdownPath": str(md_path),
        "rawPath": str(raw_path),
    }
    with paths["index"].open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(index_record, ensure_ascii=False) + "\n")

    return {
        "raw": str(raw_path),
        "markdown": str(md_path),
    }


def _slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", value).strip("-")
    return value.lower() or "document"
