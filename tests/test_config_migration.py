from datetime import UTC, datetime

import pytest

from opinion_tracker.config_migration import migrate_portable_config


def payload():
    return {
        "schema_version": 1,
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
        "trader_profile": {},
        "updated_at": datetime.now(UTC).isoformat(),
        "revision": "r1",
    }


def test_v1_migrates_to_morning_evening_weekly():
    config = migrate_portable_config(payload())
    assert set(config.report_jobs) == {"morning", "evening", "weekly"}
    assert config.report_jobs["morning"].hour == 9
    assert config.report_jobs["evening"].hour == 21


def test_higher_schema_fails_closed():
    with pytest.raises(ValueError, match="升级"):
        migrate_portable_config({"schema_version": 3})
