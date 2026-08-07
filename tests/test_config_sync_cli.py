import subprocess

from typer.testing import CliRunner

from opinion_tracker.cli import app
from opinion_tracker.task_state import TaskStore

runner = CliRunner()


def test_noninteractive_init_reports_remote_choices(tmp_path):
    result = runner.invoke(app, ["init", "--workspace", str(tmp_path), "--no-interactive"])
    assert result.exit_code == 0
    assert all(word in result.stdout for word in ["restore", "create", "skip"])


def test_config_repo_previews_without_import(tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    workspace = tmp_path / "work"
    result = runner.invoke(app, ["init", "--workspace", str(workspace), "--no-interactive",
                                 "--config-repo", str(remote)])
    assert result.exit_code == 0
    assert "等待确认导入" in result.stdout
    assert TaskStore(workspace).load().status == "onboarding_required"
