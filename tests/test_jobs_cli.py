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
