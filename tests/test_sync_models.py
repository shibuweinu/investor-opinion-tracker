from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from opinion_tracker.schemas import TaskDraft
from opinion_tracker.sync_models import PortableConfig
from opinion_tracker.task_state import TaskStore


def payload() -> dict:
    return {
        "schema_version": 1,
        "tracked_accounts": [{"url": "https://xueqiu.com/u/1", "display_name": "博主", "role": "research"}],
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
        "updated_at": datetime.now(UTC).isoformat(),
        "revision": "rev-1",
    }


def test_portable_config_rejects_unknown_sensitive_fields():
    with pytest.raises(ValidationError):
        PortableConfig.model_validate(payload() | {"cookie": "secret"})


def test_auto_applied_confirmation_is_auditable(tmp_path):
    draft = TaskDraft(user_urls=["https://xueq.com/u/1"])
    record = TaskStore(tmp_path).confirm_auto_applied(draft, "rev-2")
    assert record.status == "confirmed"
    assert record.confirmation_source == "auto_applied"
    assert record.source_revision == "rev-2"
