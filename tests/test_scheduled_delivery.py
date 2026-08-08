import hashlib
import smtplib
from datetime import datetime

import pytest
from test_config_migration import payload

from opinion_tracker.config_migration import migrate_portable_config
from opinion_tracker.job_state import JobStore
from opinion_tracker.run_state import DeliveryReceipt, RunIdentity, RunStateStore
from opinion_tracker.scheduled_delivery import deliver_scheduled_report


def cutoff() -> datetime:
    return datetime.fromisoformat("2026-08-07T21:00:00+08:00")


def setup_delivery(tmp_path):
    job_store = JobStore(tmp_path)
    job_store.materialize(migrate_portable_config(payload()))
    job_store.confirm("evening")
    run_store = RunStateStore(
        tmp_path, RunIdentity(job_id="evening", cutoff=cutoff())
    )
    run_store.initialize(["1"])
    state = run_store.load()
    state.status = "complete"
    run_store.save(state)
    report = tmp_path / "report.md"
    report.write_text("# report", encoding="utf-8")
    verification = tmp_path / "report.json"
    verification.write_text(
        '{"status":"complete","verification":{"ready_for_delivery":true}}',
        encoding="utf-8",
    )
    return job_store, run_store, report, verification


def test_scheduled_delivery_sends_then_records_then_advances(tmp_path):
    job_store, run_store, report, verification = setup_delivery(tmp_path)
    events = []

    def sender(address, report_path, kind, message_id=None):
        events.append((address, kind, message_id))

    receipt = deliver_scheduled_report(
        job_store,
        run_store,
        "user@163.com",
        report,
        verification,
        sender=sender,
    )

    assert events == [("user@163.com", "evening", receipt.message_id)]
    assert run_store.delivery() == receipt
    assert (job_store.root / "evening" / "checkpoint.json").exists()


def test_scheduled_delivery_with_receipt_does_not_send_twice(tmp_path):
    job_store, run_store, report, verification = setup_delivery(tmp_path)
    digest = hashlib.sha256(report.read_bytes()).hexdigest()
    existing = DeliveryReceipt(
        run_id=run_store.identity.run_id,
        job_id="evening",
        cutoff=cutoff(),
        address="user@163.com",
        message_id="<stable@investor-opinion-tracker.local>",
        report_sha256=digest,
    )
    run_store.record_delivery(existing)
    calls = []

    receipt = deliver_scheduled_report(
        job_store,
        run_store,
        "user@163.com",
        report,
        verification,
        sender=lambda *args, **kwargs: calls.append(1),
    )

    assert receipt == existing
    assert calls == []
    assert (job_store.root / "evening" / "checkpoint.json").exists()


def test_smtp_failure_never_records_or_advances_checkpoint(tmp_path):
    job_store, run_store, report, verification = setup_delivery(tmp_path)

    def raise_smtp(*args, **kwargs):
        raise smtplib.SMTPException("failed")

    with pytest.raises(smtplib.SMTPException):
        deliver_scheduled_report(
            job_store,
            run_store,
            "user@163.com",
            report,
            verification,
            sender=raise_smtp,
        )

    assert run_store.delivery() is None
    assert not (job_store.root / "evening" / "checkpoint.json").exists()


def test_scheduled_delivery_rejects_incomplete_run(tmp_path):
    job_store, run_store, report, verification = setup_delivery(tmp_path)
    state = run_store.load()
    state.status = "incomplete"
    run_store.save(state)

    with pytest.raises(ValueError, match="完整"):
        deliver_scheduled_report(
            job_store,
            run_store,
            "user@163.com",
            report,
            verification,
            sender=lambda *args, **kwargs: None,
        )
