from datetime import UTC, datetime

from test_config_migration import payload

from opinion_tracker.config_migration import migrate_portable_config
from opinion_tracker.job_state import JobStore


def test_materializes_jobs_without_external_paths(tmp_path):
    store = JobStore(tmp_path)
    store.materialize(migrate_portable_config(payload()))
    assert [job.job_id for job in store.list()] == ["evening", "morning", "weekly"]


def test_failure_does_not_advance_checkpoint(tmp_path):
    store = JobStore(tmp_path)
    config = migrate_portable_config(payload())
    store.materialize(config)
    cutoff = datetime(2026, 8, 7, 9, tzinfo=UTC)
    assert store.window("morning", cutoff).since is None
    store.mark_success("morning", cutoff)
    assert store.window("morning", cutoff).since == cutoff
