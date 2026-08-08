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


def test_due_run_maps_2102_start_to_2100_cutoff(tmp_path):
    store = JobStore(tmp_path)
    store.materialize(migrate_portable_config(payload()))

    due = store.due_runs(datetime.fromisoformat("2026-08-07T21:02:00+08:00"))

    assert due[0].job.job_id == "evening"
    assert due[0].scheduled_cutoff == datetime.fromisoformat(
        "2026-08-07T21:00:00+08:00"
    )


def test_due_run_rejects_start_after_fifteen_minute_grace(tmp_path):
    store = JobStore(tmp_path)
    store.materialize(migrate_portable_config(payload()))

    assert store.due_runs(datetime.fromisoformat("2026-08-07T21:16:00+08:00")) == []
