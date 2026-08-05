from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal

import typer

from .config import Settings
from .opinions import extract_opinions
from .reporting import write_artifacts
from .scheduling import schedule_hint
from .schemas import NormalizedPost, RunResult
from .scoring import score_candidate

app = typer.Typer(help="可移植的投资者观点跟踪与交易研究工具")


@app.command()
def init(workspace: Annotated[Path | None, typer.Option(help="数据工作目录")] = None) -> None:
    workspace = workspace or Path.cwd()
    path = Settings().save(workspace)
    typer.echo(f"已创建配置：{path}")


@app.command()
def profile(workspace: Annotated[Path | None, typer.Option()] = None) -> None:
    workspace = workspace or Path.cwd()
    typer.echo(json.dumps(Settings.load(workspace).trader_profile.model_dump(), ensure_ascii=False, indent=2))


@app.command("schedule-hint")
def show_schedule(kind: str = typer.Option("daily")) -> None:
    typer.echo(schedule_hint(kind))


@app.command()
def doctor() -> None:
    typer.echo("OK: Python 与核心依赖可用；浏览器适配器需由宿主 Agent 注入已授权会话。")


@app.command("analyze-file")
def analyze_file(
    input_path: Annotated[Path, typer.Option("--input", exists=True, readable=True)],
    output: Annotated[Path, typer.Option("--output")],
    complete: Annotated[bool, typer.Option(help="抓取数据是否完整")] = True,
) -> None:
    """分析宿主 Agent 抓取并标准化的帖子 JSON 数组。"""
    posts = [
        NormalizedPost.model_validate(item) for item in json.loads(input_path.read_text(encoding="utf-8"))
    ]
    opinions = extract_opinions(posts)
    candidates = [score_candidate(item, 0.5, 0.5, "C", complete) for item in opinions]
    status: Literal["complete", "incomplete", "failed"] = "complete" if complete else "incomplete"
    result = RunResult(status=status, posts_collected=len(posts), opinions=opinions, candidates=candidates)
    paths = write_artifacts(output, result, Settings().trader_profile)
    typer.echo(json.dumps({key: str(value) for key, value in paths.items()}, ensure_ascii=False))


def main() -> None:
    app()
