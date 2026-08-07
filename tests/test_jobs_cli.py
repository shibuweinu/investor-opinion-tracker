from datetime import UTC, datetime

from test_config_migration import payload
from typer.testing import CliRunner

from opinion_tracker.cli import app
from opinion_tracker.config_migration import migrate_portable_config
from opinion_tracker.job_state import JobStore

runner = CliRunner()


def test_jobs_list_uses_stable_ids(tmp_path):
    JobStore(tmp_path).materialize(migrate_portable_config(payload()))
    result = runner.invoke(app, ["jobs", "list", "--workspace", str(tmp_path)])
    assert result.exit_code == 0
    assert all(name in result.stdout for name in ["morning", "evening", "weekly"])


def test_update_check_command_is_exposed():
    assert "update-check" in runner.invoke(app, ["--help"]).stdout


def test_job_summary_and_confirmation(tmp_path):
    JobStore(tmp_path).materialize(migrate_portable_config(payload()))
    summary = runner.invoke(app, ["jobs", "summary", "morning", "--workspace", str(tmp_path)])
    assert summary.exit_code == 0 and '"hour": 9' in summary.stdout
    confirmed = runner.invoke(app, ["jobs", "confirm", "morning", "--workspace", str(tmp_path)])
    assert confirmed.exit_code == 0
    assert JobStore(tmp_path).task_store("morning").require_confirmed()


def test_due_jobs_use_portable_schedule(tmp_path):
    store = JobStore(tmp_path)
    store.materialize(migrate_portable_config(payload()))
    due = store.due(datetime(2026, 8, 7, 9, tzinfo=UTC))
    assert [job.job_id for job in due] == ["morning"]
