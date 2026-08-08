from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

from .delivery import require_verified_result, send_report
from .job_state import JobStore
from .run_state import DeliveryReceipt, RunStateStore

ReportSender = Callable[[str, Path, str, str | None], None]


def _report_digest(report: Path) -> str:
    if not report.is_file():
        raise FileNotFoundError(f"报告不存在：{report}")
    return hashlib.sha256(report.read_bytes()).hexdigest()


def _message_id(run_id: str) -> str:
    digest = hashlib.sha256(run_id.encode()).hexdigest()
    return f"<{digest}@investor-opinion-tracker.local>"


def deliver_scheduled_report(
    job_store: JobStore,
    run_store: RunStateStore,
    address: str,
    report: Path,
    verification: Path,
    *,
    sender: ReportSender = send_report,
) -> DeliveryReceipt:
    require_verified_result(verification)
    run = run_store.load()
    if run.status != "complete":
        raise ValueError("采集运行尚未完整完成，禁止投递")
    job = job_store.get(run.job_id)
    if run.cutoff != run_store.identity.cutoff or run.job_id != run_store.identity.job_id:
        raise ValueError("报告任务与运行状态不一致")
    digest = _report_digest(report)
    existing = run_store.delivery()
    if existing is not None:
        if (
            existing.job_id != run.job_id
            or existing.cutoff != run.cutoff
            or existing.address != address
            or existing.report_sha256 != digest
        ):
            raise ValueError("现有投递回执与本次报告不一致")
        job_store.complete(run.job_id, run.cutoff, verified=True)
        return existing
    message_id = _message_id(run.run_id)
    sender(address, report, job.kind, message_id)
    receipt = DeliveryReceipt(
        run_id=run.run_id,
        job_id=run.job_id,
        cutoff=run.cutoff,
        address=address,
        message_id=message_id,
        report_sha256=digest,
    )
    run_store.record_delivery(receipt)
    job_store.complete(run.job_id, run.cutoff, verified=True)
    return receipt
