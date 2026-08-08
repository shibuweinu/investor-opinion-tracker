import pytest

from opinion_tracker.schemas import TaskDraft
from opinion_tracker.task_state import TaskStore


def draft(**changes):
    values = {
        "user_urls": ["https://xueqiu.com/u/2292705444"],
        "lookback_days": 5,
        "qps": 1,
        "report_type": "daily",
    }
    values.update(changes)
    return TaskDraft(**values)


def test_new_store_requires_onboarding(tmp_path):
    assert TaskStore(tmp_path).load().status == "onboarding_required"


def test_confirmed_draft_is_invalidated_by_change(tmp_path):
    store = TaskStore(tmp_path)
    store.save_draft(draft())
    confirmed = store.confirm()
    assert store.require_confirmed().fingerprint == confirmed.fingerprint
    store.save_draft(draft(lookback_days=7))
    with pytest.raises(PermissionError, match="重新确认"):
        store.require_confirmed()


def test_absent_draft_cannot_be_confirmed(tmp_path):
    with pytest.raises(ValueError, match="任务草稿"):
        TaskStore(tmp_path).confirm()


def test_position_option_defaults_off_and_invalidates_confirmation(tmp_path):
    store = TaskStore(tmp_path)
    original = draft()
    assert original.include_position_sizing is False
    store.save_draft(original)
    store.confirm()
    store.save_draft(draft(include_position_sizing=True))
    with pytest.raises(PermissionError, match="重新确认"):
        store.require_confirmed()


def test_execution_qps_tuning_updates_confirmed_task_without_reconfirmation(tmp_path):
    store = TaskStore(tmp_path)
    store.save_draft(draft())
    store.confirm()

    updated = store.save_draft(
        draft(user_qps={"https://xueqiu.com/u/2292705444": 0.4})
    )

    assert updated.status == "confirmed"
    assert store.require_confirmed().draft.user_qps == {
        "https://xueqiu.com/u/2292705444": 0.4
    }
