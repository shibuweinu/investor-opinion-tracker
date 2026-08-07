from datetime import UTC, datetime

from opinion_tracker.config_sync import ConfigSyncService
from opinion_tracker.git_repository import GitRepository
from opinion_tracker.sync_models import PortableConfig
from opinion_tracker.task_state import TaskStore


def document() -> PortableConfig:
    return PortableConfig.model_validate(
        {
            "tracked_accounts": [{"url": "https://xueqiu.com/u/1", "display_name": "一", "role": "research"}],
            "reports": {
                "daily": {
                    "lookback_days_by_role": {"research": 5, "auxiliary_news": 2},
                    "weekdays": [1, 2, 3, 4, 5],
                    "hour": 21,
                },
                "weekly": {
                    "lookback_days_by_role": {"research": 7, "auxiliary_news": 7},
                    "weekdays": [0],
                    "hour": 18,
                },
            },
            "trader_profile": {"style": "mixed", "aggressiveness": "balanced", "max_loss_per_trade_pct": 3},
            "report_preferences": {"include_position_sizing": False},
            "sync": {"trusted_auto_apply": True},
            "updated_at": datetime.now(UTC),
            "revision": "r1",
        }
    )


def test_push_writes_only_allowlisted_files(tmp_path):
    remote = tmp_path / "remote.git"
    import subprocess

    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    service = ConfigSyncService(tmp_path / "work", GitRepository(str(remote), tmp_path / "checkout"))
    service.connect()
    service.push(document())
    assert {p.name for p in (tmp_path / "checkout").iterdir() if p.name != ".git"} == {
        "README.md",
        "config.json",
        ".gitignore",
    }
    assert "/Users/" not in (tmp_path / "checkout" / "config.json").read_text()


def test_safe_and_trusted_pull_have_distinct_confirmation(tmp_path):
    service = ConfigSyncService(tmp_path / "work", repository=None)
    safe = service.apply_document(document(), report_kind="daily", role="research", trusted=False)
    assert safe.status == "draft"
    trusted = service.apply_document(document(), report_kind="daily", role="research", trusted=True)
    assert trusted.confirmation_source == "auto_applied"
    assert TaskStore(tmp_path / "work").require_confirmed()


def test_trusted_apply_updates_daily_research_news_and_weekly(tmp_path):
    root = tmp_path / "data"
    service = ConfigSyncService(root, repository=None)
    payload = document().model_dump(mode="json")
    payload["tracked_accounts"] = [
        {"url": "https://xueqiu.com/u/1", "display_name": "一", "role": "research"},
        {"url": "https://xueqiu.com/u/2", "display_name": "快讯", "role": "auxiliary_news"},
    ]
    config = PortableConfig.model_validate(payload)
    service.apply_trusted_document(config)
    assert TaskStore(root).require_confirmed().draft.lookback_days == 5
    assert TaskStore(tmp_path / "data-daily-news").require_confirmed().draft.lookback_days == 2
    weekly = TaskStore(tmp_path / "data-weekly").require_confirmed().draft
    assert weekly.lookback_days == 7
    assert len(weekly.user_urls) == 2
