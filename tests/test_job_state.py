from datetime import UTC, datetime

from test_config_migration import payload

from opinion_tracker.config_migration import migrate_portable_config
from opinion_tracker.job_state import JobStore


def test_materializes_jobs_without_external_paths(tmp_path):
    store = JobStore(tmp_path)
    store.materialize(migrate_portable_config(payload()))
    assert [job.job_id for job in store.list_jobs()] == ["evening", "morning", "weekly"]


def test_materialize_assigns_slow_qps_only_to_auxiliary_news(tmp_path):
    document = payload()
    document["tracked_accounts"].append(
        {"url": "https://xueqiu.com/u/2", "display_name": "快讯", "role": "auxiliary_news"}
    )
    store = JobStore(tmp_path)
    store.materialize(migrate_portable_config(document))

    draft = store.task_store("evening").load().draft
    assert draft is not None
    assert draft.user_qps["https://xueqiu.com/u/1"] == 1.0
    assert draft.user_qps["https://xueqiu.com/u/2"] == 0.4


def test_failure_does_not_advance_checkpoint(tmp_path):
    store = JobStore(tmp_path)
    config = migrate_portable_config(payload())
    store.materialize(config)
    cutoff = datetime(2026, 8, 7, 9, tzinfo=UTC)
    assert store.window("morning", cutoff).since is None
    store.mark_success("morning", cutoff)
    assert store.window("evening", cutoff).since == cutoff
