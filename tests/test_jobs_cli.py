from datetime import UTC, datetime, timedelta

from test_config_migration import payload
from typer.testing import CliRunner

from opinion_tracker.cli import app
from opinion_tracker.config_migration import migrate_portable_config
from opinion_tracker.job_state import JobStore
from opinion_tracker.run_state import DeliveryReceipt, RunIdentity, RunStateStore
from opinion_tracker.schemas import RunResult
from opinion_tracker.sync_preflight import PreflightResult

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
    due = store.due(datetime.fromisoformat("2026-08-07T09:00:00+08:00"))
    assert [job.job_id for job in due] == ["morning"]


def test_run_due_uses_scheduled_cutoff_not_actual_start(tmp_path, monkeypatch):
    store = JobStore(tmp_path)
    store.materialize(migrate_portable_config(payload()))
    store.confirm("evening")
    captured = []
    monkeypatch.setattr(
        "opinion_tracker.cli._perform_config_preflight",
        lambda workspace: PreflightResult("run"),
    )

    def capture_run(self, job_id, output, until, collector=None):
        captured.append(until)
        return RunResult(status="complete", posts_collected=0)

    monkeypatch.setattr(JobStore, "run", capture_run)
    result = runner.invoke(
        app,
        [
            "jobs",
            "run-due",
            "--workspace",
            str(tmp_path),
            "--output-root",
            str(tmp_path / "out"),
            "--now",
            "2026-08-07T21:02:00+08:00",
        ],
    )

    assert result.exit_code == 0
    assert captured == [datetime.fromisoformat("2026-08-07T21:00:00+08:00")]


def test_jobs_deliver_uses_stable_job_and_cutoff(tmp_path, monkeypatch):
    cutoff = datetime.fromisoformat("2026-08-07T21:00:00+08:00")
    report = tmp_path / "report.md"
    report.write_text("# report", encoding="utf-8")
    verification = tmp_path / "report.json"
    verification.write_text("{}", encoding="utf-8")
    captured = []

    def fake_deliver(job_store, run_store, address, report_path, verification_path):
        captured.append((run_store.identity.run_id, address, report_path, verification_path))
        return DeliveryReceipt(
            run_id=run_store.identity.run_id,
            job_id="evening",
            cutoff=cutoff,
            address=address,
            message_id="<stable@example>",
            report_sha256="a" * 64,
        )

    monkeypatch.setattr(
        "opinion_tracker.cli.deliver_scheduled_report", fake_deliver, raising=False
    )
    result = runner.invoke(
        app,
        [
            "jobs",
            "deliver",
            "evening",
            "--workspace",
            str(tmp_path),
            "--cutoff",
            cutoff.isoformat(),
            "--address",
            "user@163.com",
            "--report",
            str(report),
            "--verification",
            str(verification),
        ],
    )

    assert result.exit_code == 0
    assert captured == [
        (
            "evening@2026-08-07T21:00:00+08:00",
            "user@163.com",
            report,
            verification,
        )
    ]


def test_scheduled_run_checks_product_before_running_due(tmp_path, monkeypatch):
    calls = []

    def fake_ensure(repository, executable, argv):
        calls.append(("preflight", repository, executable, argv))
        return "current"

    def fake_run_due(workspace, output_root, now):
        calls.append(("run", workspace, output_root, now))

    monkeypatch.setattr("opinion_tracker.cli.ensure_latest_product", fake_ensure, raising=False)
    monkeypatch.setattr("opinion_tracker.cli.jobs_run_due", fake_run_due)
    repository = tmp_path / "product"
    repository.mkdir()
    result = runner.invoke(
        app,
        [
            "scheduled-run",
            "--repository",
            str(repository),
            "--workspace",
            str(tmp_path / "data"),
            "--output-root",
            str(tmp_path / "reports"),
            "--now",
            "2026-08-07T21:02:00+08:00",
        ],
    )

    assert result.exit_code == 0
    assert calls[0][0:2] == ("preflight", repository)
    assert calls[1] == (
        "run",
        tmp_path / "data",
        tmp_path / "reports",
        "2026-08-07T21:02:00+08:00",
    )


def test_clean_runs_removes_only_old_validated_run_state(tmp_path):
    now = datetime.now(UTC)
    old = RunStateStore(tmp_path, RunIdentity(job_id="evening", cutoff=now - timedelta(days=31)))
    recent = RunStateStore(tmp_path, RunIdentity(job_id="evening", cutoff=now - timedelta(days=1)))
    old.initialize(["2292705444"])
    recent.initialize(["2292705444"])
    invalid = tmp_path / ".investor-opinion-tracker" / "runs" / "not-a-run"
    invalid.mkdir()
    (invalid / "run.json").write_text("{}", encoding="utf-8")
    report = tmp_path / "reports" / "report.md"
    report.parent.mkdir()
    report.write_text("keep", encoding="utf-8")

    result = runner.invoke(
        app,
        ["jobs", "clean-runs", "--workspace", str(tmp_path), "--older-than-days", "30"],
    )

    assert result.exit_code == 0
    assert not old.root.exists()
    assert recent.root.exists()
    assert invalid.exists()
    assert report.exists()
