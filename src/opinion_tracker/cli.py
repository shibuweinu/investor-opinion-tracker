from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal

import typer

from .config import Settings
from .execution import execute_confirmed
from .onboarding import landing_text, task_summary, write_landing
from .opinions import extract_opinions
from .reporting import write_artifacts
from .scheduling import schedule_hint
from .schemas import NormalizedPost, RunResult, TaskDraft, TraderProfile
from .scoring import score_candidate
from .task_state import TaskStore

app = typer.Typer(help="可移植的投资者观点跟踪与交易研究工具")


@app.command()
def init(
    workspace: Annotated[Path | None, typer.Option(help="数据工作目录")] = None,
    no_interactive: Annotated[bool, typer.Option("--no-interactive")] = False,
) -> None:
    workspace = workspace or Path.cwd()
    path = workspace / ".investor-opinion-tracker" / "config.json"
    settings = Settings.load(workspace) if path.exists() else Settings()
    if not path.exists():
        settings.save(workspace)
    landing = write_landing(workspace, settings)
    typer.echo(f"已创建配置：{path}")
    typer.echo(f"使用指南：{landing}")
    TaskStore(workspace).load()
    if no_interactive:
        typer.echo("等待收集任务需求：Agent 应先询问用户，再运行 onboard。")
    else:
        typer.echo("即将进入 onboarding；确认任务摘要之前不会抓取。")
        if typer.confirm("现在开始填写第一次任务？", default=True):
            _onboard_interactive(workspace)


def _save_onboarding(
    workspace: Path,
    user_url: str,
    lookback_days: int,
    report_type: str,
    accept_default_profile: bool,
    style: str | None = None,
    aggressiveness: str | None = None,
    max_loss_per_trade_pct: float | None = None,
) -> None:
    custom_profile = any(value is not None for value in (style, aggressiveness, max_loss_per_trade_pct))
    if not accept_default_profile and not custom_profile:
        raise typer.BadParameter("请先确认默认画像，或由 Agent 收集自定义画像")
    if report_type not in {"daily", "weekly"}:
        raise typer.BadParameter("报告类型必须是 daily 或 weekly")
    profile = TraderProfile(
        style=style or "mixed",  # type: ignore[arg-type]
        aggressiveness=aggressiveness or "balanced",  # type: ignore[arg-type]
        max_loss_per_trade_pct=max_loss_per_trade_pct or 0.5,
    )
    draft = TaskDraft.model_validate(
        {
            "user_urls": [user_url],
            "lookback_days": lookback_days,
            "qps": 1,
            "report_type": report_type,
            "trader_profile": profile.model_dump(),
        }
    )
    TaskStore(workspace).save_draft(draft)
    if not custom_profile:
        typer.echo("将使用 mixed / balanced / 单笔计划亏损 0.5%")
    typer.echo(task_summary(draft))


def _onboard_interactive(workspace: Path) -> None:
    user_url = typer.prompt("雪球博主主页")
    lookback_days = typer.prompt("回溯天数", default=5, type=int)
    report_type = typer.prompt("报告类型 daily/weekly", default="daily")
    typer.echo("默认画像：mixed / balanced / 单笔计划亏损 0.5%")
    accepted = typer.confirm("接受默认画像？", default=True)
    _save_onboarding(workspace, user_url, lookback_days, report_type, accepted)


@app.command()
def onboard(
    workspace: Annotated[Path | None, typer.Option()] = None,
    user_url: Annotated[str | None, typer.Option("--user-url")] = None,
    lookback_days: Annotated[int, typer.Option()] = 5,
    report_type: Annotated[str, typer.Option()] = "daily",
    accept_default_profile: Annotated[bool, typer.Option("--accept-default-profile")] = False,
    style: Annotated[str | None, typer.Option()] = None,
    aggressiveness: Annotated[str | None, typer.Option()] = None,
    max_loss_per_trade_pct: Annotated[float | None, typer.Option()] = None,
) -> None:
    """收集需求并保存未确认任务草稿。"""
    workspace = workspace or Path.cwd()
    if user_url is None:
        _onboard_interactive(workspace)
        return
    _save_onboarding(workspace, user_url, lookback_days, report_type, accept_default_profile,
                     style, aggressiveness, max_loss_per_trade_pct)


@app.command("task-status")
def task_status(workspace: Annotated[Path | None, typer.Option()] = None) -> None:
    workspace = workspace or Path.cwd()
    typer.echo(TaskStore(workspace).load().model_dump_json(indent=2))


@app.command("task-summary")
def show_task_summary(
    workspace: Annotated[Path | None, typer.Option()] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    workspace = workspace or Path.cwd()
    draft = TaskStore(workspace).load().draft
    if draft is None:
        raise typer.BadParameter("尚未创建任务草稿，请先运行 onboard")
    typer.echo(draft.model_dump_json(indent=2) if json_output else task_summary(draft))


@app.command("task-confirm")
def confirm_task(workspace: Annotated[Path | None, typer.Option()] = None) -> None:
    workspace = workspace or Path.cwd()
    try:
        record = TaskStore(workspace).confirm()
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"任务已确认：{record.fingerprint}")


@app.command()
def run(
    workspace: Annotated[Path | None, typer.Option()] = None,
    output: Annotated[Path, typer.Option()] = Path("reports"),
) -> None:
    """执行已经由用户确认的抓取与分析任务。"""
    workspace = workspace or Path.cwd()
    try:
        result = execute_confirmed(workspace, output)
    except PermissionError as exc:
        raise typer.BadParameter(
            "请先运行 onboard，查看 task-summary，并在用户明确确认后执行 task-confirm"
        ) from exc
    typer.echo(f"执行完成：抓取 {result.posts_collected} 条，报告位于 {output}")


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


@app.command()
def welcome(workspace: Annotated[Path | None, typer.Option()] = None) -> None:
    """显示初始化使用指南。"""
    workspace = workspace or Path.cwd()
    typer.echo(landing_text(Settings.load(workspace)))


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
