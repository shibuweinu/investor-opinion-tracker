from typer.testing import CliRunner

from opinion_tracker.cli import app
from opinion_tracker.collectors.xueqiu import XueqiuCollector
from opinion_tracker.config import Settings
from opinion_tracker.mcp_server import build_server
from opinion_tracker.scheduling import schedule_hint
from opinion_tracker.schemas import RunRequest, VerificationSummary
from opinion_tracker.task_state import TaskStore


class FakeBrowser:
    def __init__(self):
        self.calls = 0

    def fetch_timeline(self, user_id, page, count):
        self.calls += 1
        return {
            "list": [
                {
                    "id": 9,
                    "created_at": 1785945600000,
                    "text": "看好 $恒瑞医药(SH600276)$",
                    "user": {"id": user_id, "screen_name": "药神"},
                }
            ],
            "next_max_id": None,
        }


def test_xueqiu_collection_and_cli(tmp_path):
    req = RunRequest(user_url="https://xueqiu.com/u/2292705444", lookback_days=5, qps=1)
    result = XueqiuCollector(FakeBrowser()).collect(req)
    assert result.status == "complete" and len(result.posts) == 1
    runner = CliRunner()
    out = runner.invoke(app, ["init", "--workspace", str(tmp_path), "--no-interactive"])
    assert out.exit_code == 0
    assert (tmp_path / ".investor-opinion-tracker" / "config.json").exists()
    landing = tmp_path / ".investor-opinion-tracker" / "WELCOME.md"
    assert landing.exists()
    text = landing.read_text(encoding="utf-8")
    assert "第一次任务" in text
    assert "外置 Chrome" in text
    assert "TDX" in text
    assert "单笔计划亏损 0.5%" in text
    assert "schedule-hint" in text
    assert TaskStore(tmp_path).load().draft is None


def test_noninteractive_init_waits_for_requirements(tmp_path):
    out = CliRunner().invoke(app, ["init", "--workspace", str(tmp_path), "--no-interactive"])
    assert out.exit_code == 0
    assert "等待收集任务需求" in out.stdout
    assert TaskStore(tmp_path).load().status == "onboarding_required"


def test_onboard_saves_unconfirmed_draft_and_summary(tmp_path):
    out = CliRunner().invoke(
        app,
        [
            "onboard",
            "--workspace",
            str(tmp_path),
            "--user-url",
            "https://xueqiu.com/u/2292705444",
            "--lookback-days",
            "5",
            "--report-type",
            "daily",
            "--accept-default-profile",
        ],
    )
    assert out.exit_code == 0
    assert "尚未执行" in out.stdout
    assert "2292705444" in out.stdout
    assert TaskStore(tmp_path).load().status == "draft"


def test_task_confirm_requires_draft(tmp_path):
    out = CliRunner().invoke(app, ["task-confirm", "--workspace", str(tmp_path)])
    assert out.exit_code != 0


def test_task_summary_supports_json_and_custom_profile(tmp_path):
    runner = CliRunner()
    created = runner.invoke(
        app,
        [
            "onboard",
            "--workspace",
            str(tmp_path),
            "--user-url",
            "https://xueqiu.com/u/2292705444",
            "--style",
            "short_term",
            "--aggressiveness",
            "aggressive",
            "--max-loss-per-trade-pct",
            "0.8",
        ],
    )
    assert created.exit_code == 0
    summary = runner.invoke(app, ["task-summary", "--workspace", str(tmp_path), "--json"])
    assert summary.exit_code == 0
    payload = __import__("json").loads(summary.stdout)
    assert payload["trader_profile"]["style"] == "short_term"
    assert payload["trader_profile"]["max_loss_per_trade_pct"] == 0.8


def test_interactive_init_can_exit_without_creating_target(tmp_path):
    out = CliRunner().invoke(app, ["init", "--workspace", str(tmp_path)], input="n\n")
    assert out.exit_code == 0
    assert TaskStore(tmp_path).load().draft is None


def test_repeated_init_preserves_existing_profile(tmp_path):
    settings = Settings()
    settings.trader_profile.style = "short_term"
    settings.save(tmp_path)
    out = CliRunner().invoke(app, ["init", "--workspace", str(tmp_path), "--no-interactive"])
    assert out.exit_code == 0
    assert Settings.load(tmp_path).trader_profile.style == "short_term"


def test_onboard_accepts_multiple_user_urls(tmp_path):
    out = CliRunner().invoke(
        app,
        [
            "onboard",
            "--workspace",
            str(tmp_path),
            "--user-url",
            "https://xueqiu.com/u/111",
            "--user-url",
            "https://xueqiu.com/u/222",
            "--accept-default-profile",
        ],
    )
    assert out.exit_code == 0
    draft = TaskStore(tmp_path).load().draft
    assert draft is not None
    assert [str(url).rstrip("/").split("/")[-1] for url in draft.user_urls] == ["111", "222"]


def test_schedule_hint_is_offer_only():
    hint = schedule_hint("daily")
    assert "cron" in hint and "不会自动创建" in hint


def test_cli_analyze_file_fails_closed_when_market_verification_fails(tmp_path, monkeypatch):
    source = tmp_path / "posts.json"
    source.write_text(
        '[{"platform":"xueqiu","platform_post_id":"1","author_id":"u",'
        '"published_at":"2026-08-05T00:00:00Z","text":"看好 SH600276",'
        '"url":"https://xueqiu.com/u/1"}]',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "opinion_tracker.cli.verify_research",
        lambda opinions, research_claims, fact_evidence, **kwargs: VerificationSummary(
            market_status="failed", fact_status="unverified"
        ),
    )
    out = CliRunner().invoke(
        app, ["analyze-file", "--input", str(source), "--output", str(tmp_path / "reports")]
    )
    assert out.exit_code == 2
    assert (tmp_path / "reports" / "UNVERIFIED.md").exists()
    assert not (tmp_path / "reports" / "report.md").exists()


def test_cli_analyze_file_delivers_partial_report_and_excludes_failed_content(tmp_path, monkeypatch):
    source = tmp_path / "posts.json"
    source.write_text(
        '[{"platform":"xueqiu","platform_post_id":"1","author_id":"u",'
        '"published_at":"2026-08-05T00:00:00Z","text":"看好 SH600276",'
        '"url":"https://xueqiu.com/u/1"}]',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "opinion_tracker.cli.verify_research",
        lambda opinions, research_claims, fact_evidence, **kwargs: VerificationSummary(
            market_status="not_required",
            semantic_status="unverified",
            fact_status="verified",
            excluded_opinion_ids=[opinions[0].opinion_id],
            exclusion_reasons={opinions[0].opinion_id: "缺少语义归因，已排除"},
        ),
    )

    out = CliRunner().invoke(
        app, ["analyze-file", "--input", str(source), "--output", str(tmp_path / "reports")]
    )

    assert out.exit_code == 0
    assert (tmp_path / "reports" / "report.md").exists()
    assert not (tmp_path / "reports" / "UNVERIFIED.md").exists()
    payload = __import__("json").loads(
        (tmp_path / "reports" / "report.json").read_text(encoding="utf-8")
    )
    assert payload["candidates"] == []
    assert payload["verification"]["ready_for_delivery"] is True


def test_scheduled_analyze_requires_market_cutoff(tmp_path):
    source = tmp_path / "posts.json"
    source.write_text(
        '[{"platform":"xueqiu","platform_post_id":"1","author_id":"u",'
        '"published_at":"2026-08-05T00:00:00Z","text":"看好 SH600276",'
        '"url":"https://xueqiu.com/u/1"}]',
        encoding="utf-8",
    )
    job_workspace = tmp_path / "morning"
    job_workspace.mkdir()
    (job_workspace / "job.json").write_text("{}", encoding="utf-8")

    out = CliRunner().invoke(
        app,
        [
            "analyze-file",
            "--workspace",
            str(job_workspace),
            "--input",
            str(source),
            "--output",
            str(tmp_path / "reports"),
        ],
    )

    assert out.exit_code != 0
    assert "必须传入 --market-as-of" in out.output


def test_cli_analyze_file_uses_workspace_profile_when_verified(tmp_path, monkeypatch):
    source = tmp_path / "posts.json"
    source.write_text(
        '[{"platform":"xueqiu","platform_post_id":"1","author_id":"u",'
        '"published_at":"2026-08-05T00:00:00Z","text":"看好 SH600276",'
        '"url":"https://xueqiu.com/u/1"}]',
        encoding="utf-8",
    )
    TaskStore(tmp_path).save_draft(
        __import__("opinion_tracker.schemas", fromlist=["TaskDraft"]).TaskDraft(
            user_urls=["https://xueqiu.com/u/1"],
            trader_profile={"style": "mixed", "max_loss_per_trade_pct": 3},
        )
    )
    monkeypatch.setattr(
        "opinion_tracker.cli.verify_research",
        lambda opinions, research_claims, fact_evidence, **kwargs: VerificationSummary(
            market_status="verified", semantic_status="verified", fact_status="verified"
        ),
    )
    out = CliRunner().invoke(
        app,
        [
            "analyze-file",
            "--workspace",
            str(tmp_path),
            "--input",
            str(source),
            "--output",
            str(tmp_path / "reports"),
        ],
    )
    assert out.exit_code == 0
    report = (tmp_path / "reports" / "report.md").read_text(encoding="utf-8")
    assert "3.0%" in report


def test_mcp_server_builds_with_installed_extra():
    assert type(build_server()).__name__ == "MCPServer"
