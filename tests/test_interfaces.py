from typer.testing import CliRunner

from opinion_tracker.cli import app
from opinion_tracker.collectors.xueqiu import XueqiuCollector
from opinion_tracker.mcp_server import build_server
from opinion_tracker.scheduling import schedule_hint
from opinion_tracker.schemas import RunRequest


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
    out = runner.invoke(app, ["init", "--workspace", str(tmp_path)])
    assert out.exit_code == 0
    assert (tmp_path / ".investor-opinion-tracker" / "config.json").exists()


def test_schedule_hint_is_offer_only():
    hint = schedule_hint("daily")
    assert "cron" in hint and "不会自动创建" in hint


def test_cli_analyze_file(tmp_path):
    source = tmp_path / "posts.json"
    source.write_text(
        '[{"platform":"xueqiu","platform_post_id":"1","author_id":"u",'
        '"published_at":"2026-08-05T00:00:00Z","text":"看好 SH600276",'
        '"url":"https://xueqiu.com/u/1"}]',
        encoding="utf-8",
    )
    out = CliRunner().invoke(
        app, ["analyze-file", "--input", str(source), "--output", str(tmp_path / "reports")]
    )
    assert out.exit_code == 0
    assert (tmp_path / "reports" / "report.md").exists()


def test_mcp_server_builds_with_installed_extra():
    assert type(build_server()).__name__ == "MCPServer"
