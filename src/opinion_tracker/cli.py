from __future__ import annotations

import json
import smtplib
from pathlib import Path
from typing import Annotated, Literal

import typer

from .config import Settings
from .config_sync import ConfigSyncService
from .delivery import (
    prompt_and_store_auth_code,
    require_verified_result,
    send_report,
    send_test,
    smtp_settings_for,
)
from .device_trust import DeviceTrustStore, KeychainTrustBackend, RepositoryIdentity
from .execution import execute_confirmed
from .git_repository import GitRepository
from .onboarding import landing_text, task_summary, write_landing
from .opinions import extract_opinions
from .reporting import write_artifacts
from .scheduling import schedule_hint
from .schemas import FactEvidence, NormalizedPost, ResearchClaim, RunResult, TaskDraft, TraderProfile
from .scoring import score_candidate
from .sync_models import PortableConfig
from .sync_preflight import preflight_scheduled_run
from .task_state import TaskStore
from .verification import verify_research

app = typer.Typer(help="可移植的投资者观点跟踪与交易研究工具")


@app.command()
def init(
    workspace: Annotated[Path | None, typer.Option(help="数据工作目录")] = None,
    no_interactive: Annotated[bool, typer.Option("--no-interactive")] = False,
    config_repo: Annotated[str | None, typer.Option("--config-repo")] = None,
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
    if config_repo:
        repository = GitRepository(config_repo, workspace / ".investor-opinion-tracker" / "config-repo")
        ConfigSyncService(workspace, repository).connect()
        typer.echo(f"已连接并预览配置仓库：{repository.canonical_remote()}；等待确认导入。")
    if no_interactive:
        typer.echo("等待收集任务需求：Agent 应先询问用户，再运行 onboard。")
        if not config_repo:
            typer.echo("远端配置未绑定；可选动作：restore（恢复）、create（创建）、skip（跳过）。")
    else:
        typer.echo("即将进入 onboarding；确认任务摘要之前不会抓取。")
        if typer.confirm("现在开始填写第一次任务？", default=True):
            _onboard_interactive(workspace)


def _save_onboarding(
    workspace: Path,
    user_urls: list[str],
    lookback_days: int,
    report_type: str,
    accept_default_profile: bool,
    style: str | None = None,
    aggressiveness: str | None = None,
    max_loss_per_trade_pct: float | None = None,
    include_position_sizing: bool = False,
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
            "user_urls": user_urls,
            "lookback_days": lookback_days,
            "qps": 1,
            "report_type": report_type,
            "trader_profile": profile.model_dump(),
            "include_position_sizing": include_position_sizing,
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
    _save_onboarding(workspace, [user_url], lookback_days, report_type, accepted)


@app.command()
def onboard(
    workspace: Annotated[Path | None, typer.Option()] = None,
    user_urls: Annotated[list[str] | None, typer.Option("--user-url")] = None,
    lookback_days: Annotated[int, typer.Option()] = 5,
    report_type: Annotated[str, typer.Option()] = "daily",
    accept_default_profile: Annotated[bool, typer.Option("--accept-default-profile")] = False,
    style: Annotated[str | None, typer.Option()] = None,
    aggressiveness: Annotated[str | None, typer.Option()] = None,
    max_loss_per_trade_pct: Annotated[float | None, typer.Option()] = None,
    include_position_sizing: Annotated[bool, typer.Option("--include-position-sizing")] = False,
) -> None:
    """收集需求并保存未确认任务草稿。"""
    workspace = workspace or Path.cwd()
    if not user_urls:
        _onboard_interactive(workspace)
        return
    _save_onboarding(
        workspace,
        user_urls,
        lookback_days,
        report_type,
        accept_default_profile,
        style,
        aggressiveness,
        max_loss_per_trade_pct,
        include_position_sizing,
    )


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
    typer.echo(f"证据准备完成：抓取 {result.posts_collected} 条；Agent 请读取 {output / 'ANALYZE.md'}")


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


@app.command("email-setup")
def email_setup(address: Annotated[str, typer.Option("--address")]) -> None:
    """将网易邮箱客户端授权码安全保存到 macOS 钥匙串。"""
    smtp_settings_for(address)
    prompt_and_store_auth_code(address)
    typer.echo(f"已保存 {address} 的 SMTP 授权码；授权码未写入仓库或日志。")


@app.command("email-test")
def email_test(address: Annotated[str, typer.Option("--address")]) -> None:
    """发送一封网易邮箱通道测试邮件。"""
    try:
        send_test(address)
    except (OSError, RuntimeError, smtplib.SMTPException) as exc:
        raise typer.BadParameter(f"测试邮件发送失败：{exc}") from exc
    typer.echo(f"测试邮件已发送至 {address}")


@app.command("email-send")
def email_send(
    address: Annotated[str, typer.Option("--address")],
    report: Annotated[Path, typer.Option("--report", exists=True, readable=True)],
    verification: Annotated[Path, typer.Option("--verification", exists=True, readable=True)],
    kind: Annotated[Literal["daily", "weekly"], typer.Option("--kind")],
) -> None:
    """将验证完成的日报或周报发送到网易邮箱。"""
    try:
        require_verified_result(verification)
        send_report(address, report, kind)
    except (OSError, RuntimeError, ValueError, smtplib.SMTPException) as exc:
        raise typer.BadParameter(f"报告邮件发送失败：{exc}") from exc
    typer.echo(f"{kind} 报告已发送至 {address}")


@app.command()
def welcome(workspace: Annotated[Path | None, typer.Option()] = None) -> None:
    """显示初始化使用指南。"""
    workspace = workspace or Path.cwd()
    typer.echo(landing_text(Settings.load(workspace)))


def _sync_service(workspace: Path) -> ConfigSyncService:
    binding_path = workspace / ".investor-opinion-tracker" / "sync-binding.json"
    if not binding_path.exists():
        raise typer.BadParameter("尚未绑定配置仓库，请先运行 config-connect")
    remote = json.loads(binding_path.read_text())["remote_url"]
    return ConfigSyncService(
        workspace, GitRepository(remote, workspace / ".investor-opinion-tracker" / "config-repo")
    )


@app.command("config-connect")
def config_connect(
    workspace: Annotated[Path, typer.Option("--workspace")],
    repo: Annotated[str, typer.Option("--repo")],
) -> None:
    binding = ConfigSyncService(
        workspace, GitRepository(repo, workspace / ".investor-opinion-tracker" / "config-repo")
    ).connect()
    typer.echo(f"已绑定：{binding.canonical_remote}")


@app.command("config-status")
def config_status(workspace: Annotated[Path, typer.Option("--workspace")]) -> None:
    path = workspace / ".investor-opinion-tracker" / "sync-binding.json"
    typer.echo(path.read_text() if path.exists() else '{"status":"unbound"}')


@app.command("config-push")
def config_push(
    workspace: Annotated[Path, typer.Option("--workspace")],
    config_file: Annotated[Path | None, typer.Option("--config-file")] = None,
    yes: Annotated[bool, typer.Option("--yes")] = False,
) -> None:
    path = config_file or workspace / ".investor-opinion-tracker" / "portable-config.json"
    document = PortableConfig.model_validate_json(path.read_text())
    if not yes and not typer.confirm("推送以上白名单个人配置？"):
        raise typer.Abort()
    commit = _sync_service(workspace).push(document)
    typer.echo(f"配置已推送：{commit}")


@app.command("config-pull")
def config_pull(
    workspace: Annotated[Path, typer.Option("--workspace")],
    yes: Annotated[bool, typer.Option("--yes")] = False,
) -> None:
    service = _sync_service(workspace)
    document = service.load_remote()
    typer.echo(document.model_dump_json(indent=2))
    if not yes and not typer.confirm("导入以上配置为待确认任务？"):
        raise typer.Abort()
    target = workspace / ".investor-opinion-tracker" / "portable-config.json"
    target.write_text(document.model_dump_json(indent=2), encoding="utf-8")
    service.apply_document(document, report_kind="daily", role="research", trusted=False)
    typer.echo("配置已导入；执行前请确认任务摘要。")


@app.command("config-trust")
def config_trust(
    workspace: Annotated[Path, typer.Option("--workspace")],
    yes: Annotated[bool, typer.Option("--yes")] = False,
) -> None:
    service = _sync_service(workspace)
    assert service.repository is not None
    canonical = service.repository.canonical_remote()
    owner = canonical.split("/")[-2]
    identity = service.repository._run("config", "user.email")
    preview = RepositoryIdentity(canonical_remote=canonical, owner=owner, git_identity=identity)
    typer.echo(preview.model_dump_json(indent=2))
    if not yes and not typer.confirm("信任该仓库并自动应用后续合法更新？"):
        raise typer.Abort()
    DeviceTrustStore(KeychainTrustBackend(canonical)).authorize(preview)
    typer.echo("本设备已授权 trusted-auto-apply。")


@app.command("config-preflight")
def config_preflight(workspace: Annotated[Path, typer.Option("--workspace")]) -> None:
    """定时任务运行前拉取并校验个人配置。"""
    service = _sync_service(workspace)
    assert service.repository is not None
    service.repository.clone_or_open()
    canonical = service.repository.canonical_remote()
    identity = RepositoryIdentity(
        canonical_remote=canonical,
        owner=canonical.split("/")[-2],
        git_identity=service.repository._run("config", "user.email"),
    )
    trusted = DeviceTrustStore(KeychainTrustBackend(canonical)).is_trusted(identity)
    result = preflight_scheduled_run(service, locally_trusted=trusted)
    typer.echo(json.dumps({"action": result.action, "message": result.message}, ensure_ascii=False))
    if result.action == "confirmation_required":
        raise typer.Exit(code=2)


@app.command("analyze-file")
def analyze_file(
    input_path: Annotated[Path, typer.Option("--input", exists=True, readable=True)],
    output: Annotated[Path, typer.Option("--output")],
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
    claims_path: Annotated[Path | None, typer.Option("--claims", exists=True, readable=True)] = None,
    fact_evidence_path: Annotated[
        Path | None, typer.Option("--fact-evidence", exists=True, readable=True)
    ] = None,
    complete: Annotated[bool, typer.Option(help="抓取数据是否完整")] = True,
) -> None:
    """分析帖子并强制执行行情与独立事实核验门禁。"""
    posts = [
        NormalizedPost.model_validate(item) for item in json.loads(input_path.read_text(encoding="utf-8"))
    ]
    opinions = extract_opinions(posts)
    research_claims = (
        [ResearchClaim.model_validate(item) for item in json.loads(claims_path.read_text())]
        if claims_path
        else []
    )
    fact_evidence = (
        [FactEvidence.model_validate(item) for item in json.loads(fact_evidence_path.read_text())]
        if fact_evidence_path
        else []
    )
    verification = verify_research(opinions, research_claims, fact_evidence, posts=posts)
    data_complete = complete and verification.ready_for_final
    candidates = [score_candidate(item, 0.5, 0.5, "C", data_complete) for item in opinions]
    status: Literal["complete", "incomplete", "failed"] = "complete" if data_complete else "incomplete"
    warnings = [] if verification.ready_for_final else ["行情或独立事实核验未完成，仅生成未验证草稿"]
    result = RunResult(
        status=status,
        posts_collected=len(posts),
        opinions=opinions,
        candidates=candidates,
        warnings=warnings,
        verification=verification,
    )
    profile = Settings.load(workspace).trader_profile if workspace else Settings().trader_profile
    if workspace:
        record = TaskStore(workspace).load()
        if record.draft is not None:
            profile = record.draft.trader_profile
    paths = write_artifacts(output, result, profile)
    typer.echo(json.dumps({key: str(value) for key, value in paths.items()}, ensure_ascii=False))
    if not verification.ready_for_final:
        typer.echo("核验门禁未通过：已生成 UNVERIFIED.md，禁止作为最终报告交付。", err=True)
        raise typer.Exit(code=2)


def main() -> None:
    app()
