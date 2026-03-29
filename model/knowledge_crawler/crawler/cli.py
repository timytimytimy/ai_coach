from __future__ import annotations

import json
from pathlib import Path

import typer

from .config import load_config
from .pipeline import run_crawl

app = typer.Typer(help="力量举知识库爬虫")


@app.command()
def crawl(
    config: Path = typer.Option(..., exists=True, dir_okay=False, readable=True),
) -> None:
    cfg = load_config(config)
    results = run_crawl(cfg)
    typer.echo(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
