# Resumable Xueqiu Scheduling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make scheduled Xueqiu reports tolerate launch delays and transient deep-pagination limits, resume from durable page checkpoints, and deliver email idempotently before advancing report checkpoints.

**Architecture:** Add a portable run-state store under each personal workspace and keep the existing collector API compatible by adding a separate resumable entry point. Schedule matching returns the configured cutoff within a 15-minute grace window. A single `jobs deliver` command validates the report, records an SMTP receipt, and advances the job checkpoint only after delivery.

**Tech Stack:** Python 3.11, Pydantic v2, Typer, external Chrome/CDP through `agent-browser`, JSON/JSONL state, pytest, Ruff, mypy.

## Global Constraints

- Do not read, print, or persist cookies, tokens, passwords, verification pages, or SMTP authorization codes.
- Keep remote personal configuration at Schema v2; derive per-account QPS from the existing account role.
- Research accounts remain at QPS at most 1; `auxiliary_news` defaults to QPS 0.4.
- Retry HTTP 405, 429, and temporary 5xx for at most 10 minutes per account.
- Never retry or bypass login failures, sliders, or human verification.
- Use a maximum of 300 pages per account.
- Match scheduled jobs only within 15 minutes after their configured cutoff.
- Preserve current custom collectors that only implement `collect(request)`.
- Do not advance a report checkpoint until a valid delivery receipt exists.
- Use at-least-once delivery with a stable Message-ID; do not claim strict SMTP exactly-once semantics.

---

### Task 1: Durable Run State and Exclusive Run Lock

**Files:**
- Create: `src/opinion_tracker/run_state.py`
- Create: `tests/test_run_state.py`

**Interfaces:**
- Produces: `RunIdentity(job_id: str, cutoff: datetime)` with stable `run_id` and portable directory name.
- Produces: `UserPageState`, `ScheduledRunState`, and `DeliveryReceipt` Pydantic models.
- Produces: `RunStateStore(workspace: Path, identity: RunIdentity)` with `load`, `save`, `load_user`, `save_user`, `merge_posts`, `posts`, `record_delivery`, and `delivery`.
- Produces: `RunLock(store: RunStateStore)` context manager with stale-owner recovery.

- [ ] **Step 1: Write failing state persistence tests**

```python
def test_run_state_persists_page_and_deduplicates_posts(tmp_path):
    identity = RunIdentity("evening", datetime.fromisoformat("2026-08-07T21:00:00+08:00"))
    store = RunStateStore(tmp_path, identity)
    store.save_user(UserPageState(user_id="1", next_page=2, status="running"))
    store.merge_posts([post("a"), post("a"), post("b")])
    assert store.load_user("1").next_page == 2
    assert [item.platform_post_id for item in store.posts()] == ["a", "b"]


def test_run_state_rejects_mismatched_identity(tmp_path):
    first = RunStateStore(tmp_path, RunIdentity("morning", cutoff()))
    first.initialize(["1"])
    path = first.root / "run.json"
    payload = json.loads(path.read_text())
    payload["run_id"] = "different"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="运行状态"):
        first.load()
```

- [ ] **Step 2: Run the state tests and verify RED**

Run: `PYTHONPATH=src .venv/bin/pytest -q tests/test_run_state.py`

Expected: collection error because `opinion_tracker.run_state` does not exist.

- [ ] **Step 3: Implement atomic JSON state and portable paths**

Use a helper that writes `<name>.tmp`, flushes, and calls `Path.replace`. Store normalized posts as JSON lines in `posts.jsonl`, but rewrite the deduplicated file atomically after each successful page because report windows are small enough for bounded memory use. Generate a filesystem-safe directory name from job ID, cutoff, and the first 12 characters of SHA-256 while retaining the exact run ID inside `run.json`.

```python
class RunIdentity(BaseModel):
    job_id: str
    cutoff: datetime

    @computed_field
    @property
    def run_id(self) -> str:
        return f"{self.job_id}@{self.cutoff.isoformat()}"


class UserPageState(BaseModel):
    user_id: str
    next_page: int = 1
    status: Literal["pending", "running", "complete", "incomplete"] = "pending"
    oldest_regular_at: datetime | None = None
    pages_fetched: int = 0
    request_count: int = 0
    retry_count: int = 0
    last_error: str | None = None
    last_http_status: int | None = None
```

- [ ] **Step 4: Write and verify failing lock tests**

```python
def test_run_lock_prevents_concurrent_owner(tmp_path):
    store = RunStateStore(tmp_path, RunIdentity("evening", cutoff()))
    with RunLock(store):
        with pytest.raises(RunAlreadyActive):
            with RunLock(store):
                pass


def test_run_lock_reclaims_dead_pid(tmp_path):
    store = RunStateStore(tmp_path, RunIdentity("evening", cutoff()))
    store.root.mkdir(parents=True)
    store.lock_path.write_text('{"pid": 99999999}')
    with RunLock(store):
        assert json.loads(store.lock_path.read_text())["pid"] == os.getpid()
```

Run: `PYTHONPATH=src .venv/bin/pytest -q tests/test_run_state.py -k lock`

Expected: failures because locking is not implemented.

- [ ] **Step 5: Implement exclusive lock creation and stale PID recovery**

Create the lock with `os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)`. On an existing lock, parse its PID and use `os.kill(pid, 0)` to distinguish an active owner from a dead owner. Reclaim only a valid dead-owner lock; malformed lock files fail closed with a clear error.

- [ ] **Step 6: Run Task 1 tests and commit**

Run: `PYTHONPATH=src .venv/bin/pytest -q tests/test_run_state.py`

Expected: all Task 1 tests pass.

```bash
git add src/opinion_tracker/run_state.py tests/test_run_state.py
git commit -m "feat: add durable scheduled run state"
```

---

### Task 2: Resumable Pagination, Bounded Retry, and Request Budgets

**Files:**
- Modify: `src/opinion_tracker/collectors/external_chrome.py`
- Modify: `src/opinion_tracker/schemas.py`
- Modify: `tests/test_portable_adapters.py`

**Interfaces:**
- Consumes: `RunStateStore` and `UserPageState` from Task 1.
- Produces: `ExternalChromeXueqiuCollector.collect_resumable(request, store, user_state) -> CollectionResult`.
- Produces: `RetryPolicy(max_wait_seconds=600, max_pages=300)` and pure `retry_delay(attempt, retry_after, remaining) -> float | None`.
- Extends: `TaskDraft.user_qps: dict[str, float]` with an empty backward-compatible default.

- [ ] **Step 1: Write failing retry-policy tests**

```python
@pytest.mark.parametrize(
    ("attempt", "expected"),
    [(0, 5), (1, 10), (2, 20), (3, 40), (4, 60), (5, 120), (8, 120)],
)
def test_retry_policy_uses_bounded_exponential_backoff(attempt, expected):
    assert retry_delay(attempt, retry_after=None, remaining=600) == expected


def test_retry_policy_prefers_retry_after_but_never_exceeds_remaining_budget():
    assert retry_delay(0, retry_after=30, remaining=40) == 30
    assert retry_delay(0, retry_after=90, remaining=40) is None
```

- [ ] **Step 2: Run retry tests and verify RED**

Run: `PYTHONPATH=src .venv/bin/pytest -q tests/test_portable_adapters.py -k retry_policy`

Expected: import failure for `RetryPolicy` or `retry_delay`.

- [ ] **Step 3: Implement response metadata and retry policy**

Change the browser script to return parsed JSON plus `__http_status` and `__retry_after`, including when JSON parsing succeeds. Classify 405, 429, and 500–599 as retryable. Keep slider/login classification ahead of retry classification. The sleeper receives base delay plus existing random jitter; tests inject zero jitter.

- [ ] **Step 4: Write failing resumable-page tests**

```python
def test_resumable_collector_retries_same_page_and_persists_next_page(tmp_path):
    responses = iter([
        {"__http_status": 405, "__tracker_error": "invalid_response"},
        {"__http_status": 200, "statuses": [recent("1")]},
        {"__http_status": 200, "statuses": [old("2")]},
    ])
    collector = collector_for(responses)
    store = run_store(tmp_path)
    result = collector.collect_resumable(request(), store, UserPageState(user_id="1"))
    assert result.status == "complete"
    assert store.load_user("1").next_page == 3
    assert requested_pages == [1, 1, 2]


def test_resumable_collector_restarts_at_saved_page_without_duplicate_requests(tmp_path):
    store = run_store(tmp_path)
    store.save_user(UserPageState(user_id="1", next_page=4, status="incomplete"))
    store.merge_posts([post("saved")])
    result = collector.collect_resumable(request(), store, store.load_user("1"))
    assert requested_pages[0] == 4
    assert [post.platform_post_id for post in result.posts] == ["saved", "new"]
```

- [ ] **Step 5: Run resumable tests and verify RED**

Run: `PYTHONPATH=src .venv/bin/pytest -q tests/test_portable_adapters.py -k resumable`

Expected: failure because `collect_resumable` is missing.

- [ ] **Step 6: Implement page-level persistence and resume**

Refactor one-page normalization into a helper shared by `collect` and `collect_resumable`. After every successful page, merge posts and atomically save `next_page=page+1`. Mark complete only when an empty page or the last non-pinned regular post is older than the cutoff. Reopening a profile during retry must not reset the page.

- [ ] **Step 7: Write failing terminal-error and budget tests**

```python
def test_slider_stops_without_retry_and_keeps_cursor(tmp_path):
    result = collector_for([slider()]).collect_resumable(request(), store, state)
    assert result.status == "failed"
    assert sleeps == []
    assert store.load_user("1").next_page == 1


def test_page_budget_stops_at_300_pages(tmp_path):
    policy = RetryPolicy(max_pages=300)
    result = endless_collector(policy).collect_resumable(request(), store, state)
    assert result.status == "incomplete"
    assert "300" in result.warnings[0]
```

Run: `PYTHONPATH=src .venv/bin/pytest -q tests/test_portable_adapters.py -k 'slider or page_budget'`

Expected: the page-budget test fails before implementation.

- [ ] **Step 8: Implement terminal errors and hard budgets, then run Task 2 tests**

Run: `PYTHONPATH=src .venv/bin/pytest -q tests/test_portable_adapters.py`

Expected: all collector and TDX tests pass.

- [ ] **Step 9: Commit Task 2**

```bash
git add src/opinion_tracker/collectors/external_chrome.py src/opinion_tracker/schemas.py tests/test_portable_adapters.py
git commit -m "feat: resume and retry Xueqiu pagination"
```

---

### Task 3: Role-Based QPS and Resumable Multi-Account Execution

**Files:**
- Modify: `src/opinion_tracker/job_state.py`
- Modify: `src/opinion_tracker/execution.py`
- Modify: `tests/test_job_execution.py`
- Modify: `tests/test_job_state.py`

**Interfaces:**
- Consumes: `TaskDraft.user_qps`, `RunIdentity`, `RunStateStore`, `RunLock`, and `collect_resumable`.
- Extends: `execute_confirmed(workspace: Path, output: Path, collector: Collector | None = None, *, since: datetime | None = None, until: datetime | None = None, complete_state: bool = True, run_store: RunStateStore | None = None) -> RunResult`.
- Extends: `JobStore.run(job_id: str, output: Path, until: datetime, collector: Collector | None = None) -> RunResult` to initialize and resume the stable run identity.
- Preserves: fallback to `collector.collect(request)` when a custom collector has no `collect_resumable` method.

- [ ] **Step 1: Write failing role-QPS materialization test**

```python
def test_materialize_assigns_slow_qps_only_to_auxiliary_news(tmp_path):
    store = JobStore(tmp_path)
    store.materialize(config_with_research_and_news())
    draft = store.task_store("evening").load().draft
    assert draft.user_qps["https://xueqiu.com/u/1"] == 1.0
    assert draft.user_qps["https://xueqiu.com/u/2"] == 0.4
```

- [ ] **Step 2: Run role-QPS test and verify RED**

Run: `PYTHONPATH=src .venv/bin/pytest -q tests/test_job_state.py -k slow_qps`

Expected: missing key or attribute failure.

- [ ] **Step 3: Materialize user QPS from existing account roles**

In `JobStore.materialize`, build normalized URL mappings alongside `user_lookback_days`: research maps to 1.0 and auxiliary news maps to 0.4. Do not change `PortableConfigV2`.

- [ ] **Step 4: Write failing execution resume and compatibility tests**

```python
def test_execution_uses_resumable_collector_and_skips_completed_user(tmp_path):
    run_store = initialized_run_store(tmp_path, users=["1", "2"])
    run_store.save_user(UserPageState(user_id="1", status="complete", next_page=3))
    execute_confirmed(job_workspace, output, collector, run_store=run_store, complete_state=False)
    assert collector.users == ["2"]


def test_execution_keeps_legacy_custom_collector_compatible(tmp_path):
    class LegacyCollector:
        def collect(self, request):
            return CollectionResult(status="complete")
    result = execute_confirmed(job_workspace, output, LegacyCollector(), complete_state=False)
    assert result.status == "complete"
```

- [ ] **Step 5: Run execution tests and verify RED**

Run: `PYTHONPATH=src .venv/bin/pytest -q tests/test_job_execution.py -k 'resumable or legacy'`

Expected: failure because `run_store` is unsupported.

- [ ] **Step 6: Integrate run state, locking, and per-user QPS**

Initialize the run with the configured normalized user IDs. Under `RunLock`, skip completed users, build `RunRequest.qps` from `user_qps`, and call `collect_resumable` only when the collector exposes it. Aggregate final posts from the run store so a resumed process includes earlier pages. Persist warnings and final status in `run.json`.

- [ ] **Step 7: Run Task 3 tests and commit**

Run: `PYTHONPATH=src .venv/bin/pytest -q tests/test_job_state.py tests/test_job_execution.py tests/test_execution.py`

Expected: all selected tests pass.

```bash
git add src/opinion_tracker/job_state.py src/opinion_tracker/execution.py tests/test_job_state.py tests/test_job_execution.py
git commit -m "feat: resume scheduled multi-account collection"
```

---

### Task 4: Fifteen-Minute Schedule Grace and Stable Cutoff

**Files:**
- Modify: `src/opinion_tracker/job_state.py`
- Modify: `src/opinion_tracker/cli.py`
- Modify: `tests/test_job_state.py`
- Modify: `tests/test_jobs_cli.py`

**Interfaces:**
- Produces: `DueJob(job: ReportJob, scheduled_cutoff: datetime)`.
- Replaces internal use of `JobStore.due(now)` with `JobStore.due_runs(now, grace_minutes=15)`.
- Keeps `jobs list`, `jobs summary`, and direct `jobs run` unchanged.
- Changes `jobs run-due` JSON output to include `job_id`, `run_id`, `scheduled_cutoff`, `output`, and `status`.

- [ ] **Step 1: Write failing grace-window tests**

```python
def test_due_run_maps_2102_start_to_2100_cutoff(tmp_path):
    store = materialized_store(tmp_path)
    now = datetime.fromisoformat("2026-08-07T21:02:00+08:00")
    due = store.due_runs(now)
    assert due[0].job.job_id == "evening"
    assert due[0].scheduled_cutoff == datetime.fromisoformat("2026-08-07T21:00:00+08:00")


def test_due_run_rejects_start_after_fifteen_minute_grace(tmp_path):
    store = materialized_store(tmp_path)
    assert store.due_runs(datetime.fromisoformat("2026-08-07T21:16:00+08:00")) == []
```

- [ ] **Step 2: Run schedule tests and verify RED**

Run: `PYTHONPATH=src .venv/bin/pytest -q tests/test_job_state.py -k due_run`

Expected: attribute error because `due_runs` is missing.

- [ ] **Step 3: Implement timezone-aware schedule matching**

Use `ZoneInfo(job.timezone)`, construct that date's configured cutoff, and accept only `0 <= now_local - cutoff <= timedelta(minutes=15)`. Convert an aware input to job timezone; reject naive `now` with a clear error. Return each matched job with its scheduled cutoff.

- [ ] **Step 4: Write failing CLI cutoff propagation test**

```python
def test_run_due_uses_scheduled_cutoff_not_actual_start(tmp_path, monkeypatch):
    captured = []
    monkeypatch.setattr(JobStore, "run", lambda self, job_id, output, until: captured.append(until) or complete())
    result = runner.invoke(app, ["jobs", "run-due", "--workspace", str(tmp_path),
                                 "--output-root", str(tmp_path / "out"),
                                 "--now", "2026-08-07T21:02:00+08:00"])
    assert result.exit_code == 0
    assert captured == [datetime.fromisoformat("2026-08-07T21:00:00+08:00")]
```

- [ ] **Step 5: Run CLI test and verify RED**

Run: `PYTHONPATH=src .venv/bin/pytest -q tests/test_jobs_cli.py -k scheduled_cutoff`

Expected: captured value is 21:02 before the fix.

- [ ] **Step 6: Update `jobs run-due` and run Task 4 tests**

Use the scheduled date and job ID for output directories. Emit structured JSON for both completed and already-running outcomes so launchd agents can make deterministic decisions.

Run: `PYTHONPATH=src .venv/bin/pytest -q tests/test_job_state.py tests/test_jobs_cli.py`

Expected: all selected tests pass.

- [ ] **Step 7: Commit Task 4**

```bash
git add src/opinion_tracker/job_state.py src/opinion_tracker/cli.py tests/test_job_state.py tests/test_jobs_cli.py
git commit -m "fix: tolerate delayed scheduled task starts"
```

---

### Task 5: Idempotent Scheduled Email Delivery

**Files:**
- Create: `src/opinion_tracker/scheduled_delivery.py`
- Create: `tests/test_scheduled_delivery.py`
- Modify: `src/opinion_tracker/delivery.py`
- Modify: `src/opinion_tracker/cli.py`
- Modify: `tests/test_delivery.py`
- Modify: `tests/test_jobs_cli.py`

**Interfaces:**
- Extends: `build_report_message(address: str, report_path: Path, report_kind: str, message_id: str | None = None) -> EmailMessage` and `send_report(address: str, report_path: Path, report_kind: str, message_id: str | None = None) -> None`.
- Produces: `deliver_scheduled_report(job_store, run_store, address, report, verification, sender=send_report) -> DeliveryReceipt`.
- Produces CLI: `jobs deliver JOB_ID --workspace PATH --cutoff ISO --address EMAIL --report PATH --verification PATH`.

- [ ] **Step 1: Write failing stable Message-ID test**

```python
def test_report_message_accepts_stable_message_id(tmp_path):
    message = build_report_message("u@163.com", report(tmp_path), "evening", message_id="<run@example>")
    assert message["Message-ID"] == "<run@example>"
```

- [ ] **Step 2: Run message test and verify RED**

Run: `PYTHONPATH=src .venv/bin/pytest -q tests/test_delivery.py -k stable_message_id`

Expected: unexpected keyword argument `message_id`.

- [ ] **Step 3: Add optional Message-ID plumbing**

Only set the header when an explicit ID is provided. Preserve existing `email-send` behavior and tests.

- [ ] **Step 4: Write failing delivery ordering and idempotency tests**

```python
def test_scheduled_delivery_sends_then_records_then_advances(tmp_path):
    events = []
    job_store = FakeJobStore(events)
    receipt = deliver_scheduled_report(
        job_store, run_store, "u@163.com", report, verification,
        sender=lambda *args, **kwargs: events.append("sent"),
    )
    assert events == ["sent", "checkpoint"]
    assert run_store.delivery().message_id == receipt.message_id


def test_scheduled_delivery_with_receipt_does_not_send_twice(tmp_path):
    run_store.record_delivery(existing_receipt())
    calls = []
    deliver_scheduled_report(job_store, run_store, "u@163.com", report, verification,
                             sender=lambda *args, **kwargs: calls.append(1))
    assert calls == []


def test_smtp_failure_never_advances_checkpoint(tmp_path):
    with pytest.raises(smtplib.SMTPException):
        deliver_scheduled_report(
            job_store,
            run_store,
            "u@163.com",
            report,
            verification,
            sender=raise_smtp,
        )
    assert run_store.delivery() is None
    assert job_store.window("evening", cutoff).since is None
```

- [ ] **Step 5: Run scheduled delivery tests and verify RED**

Run: `PYTHONPATH=src .venv/bin/pytest -q tests/test_scheduled_delivery.py`

Expected: import failure for `scheduled_delivery`.

- [ ] **Step 6: Implement guarded delivery and receipt recovery**

Call `require_verified_result` before sending. Verify the report SHA-256, job ID, cutoff, and run status. Derive a stable Message-ID from SHA-256 of the exact run ID under the local domain `investor-opinion-tracker.local`. After SMTP success, atomically save a `DeliveryReceipt` whose status is `sent`, then call `JobStore.complete`. On an existing matching receipt, skip SMTP and ensure the checkpoint is advanced. Reject a receipt whose report hash differs.

- [ ] **Step 7: Add and test `jobs deliver` CLI**

```python
def test_jobs_deliver_requires_matching_complete_run(tmp_path):
    result = runner.invoke(app, ["jobs", "deliver", "evening", "--workspace", str(tmp_path),
                                 "--cutoff", cutoff.isoformat(), "--address", "u@163.com",
                                 "--report", str(report), "--verification", str(verification)])
    assert result.exit_code != 0
    assert "运行" in result.stdout
```

Run: `PYTHONPATH=src .venv/bin/pytest -q tests/test_scheduled_delivery.py tests/test_delivery.py tests/test_jobs_cli.py`

Expected: all selected tests pass after implementation.

- [ ] **Step 8: Commit Task 5**

```bash
git add src/opinion_tracker/scheduled_delivery.py src/opinion_tracker/delivery.py src/opinion_tracker/cli.py tests/test_scheduled_delivery.py tests/test_delivery.py tests/test_jobs_cli.py
git commit -m "feat: deliver scheduled reports idempotently"
```

---

### Task 6: Documentation, Cleanup Command, and End-to-End Verification

**Files:**
- Modify: `README.md`
- Modify: `SKILL.md`
- Modify: `references/browser-adapter.md`
- Modify: `references/scheduling.md`
- Modify: `references/cli.md`
- Modify: `src/opinion_tracker/cli.py`
- Modify: `tests/test_jobs_cli.py`

**Interfaces:**
- Produces CLI: `jobs clean-runs --workspace PATH --older-than-days N` with `N >= 1`.
- Documents: run-state paths, 15-minute grace, retry budgets, resume semantics, `jobs deliver`, and the distinction between transient limits and human verification.

- [ ] **Step 1: Write failing safe cleanup test**

```python
def test_clean_runs_removes_only_old_run_state(tmp_path):
    old_run = run_store(tmp_path, age_days=31)
    recent_run = run_store(tmp_path, age_days=1)
    report = tmp_path / "reports" / "report.md"
    report.parent.mkdir()
    report.write_text("keep")
    result = runner.invoke(app, ["jobs", "clean-runs", "--workspace", str(tmp_path),
                                 "--older-than-days", "30"])
    assert result.exit_code == 0
    assert not old_run.root.exists()
    assert recent_run.root.exists()
    assert report.exists()
```

- [ ] **Step 2: Run cleanup test and verify RED**

Run: `PYTHONPATH=src .venv/bin/pytest -q tests/test_jobs_cli.py -k clean_runs`

Expected: command does not exist.

- [ ] **Step 3: Implement explicit run-state cleanup**

Enumerate only validated child directories beneath `.investor-opinion-tracker/runs`; read each `run.json`, compare its cutoff, and delete only matching old run-state directories. Refuse `older-than-days < 1`. Never traverse report roots, config repositories, task state, or keychain data.

- [ ] **Step 4: Update portable documentation and launchd contract**

Document that schedulers call `scheduled-run`, which fails closed unless product code is clean and current, fast-forward updates and re-execs when needed, then invokes `jobs run-due`. The Agent produces verified artifacts and calls `jobs deliver` rather than separate `email-send` and `jobs complete`. Explain that a launch at 09:02 or 21:02 uses the configured 09:00 or 21:00 cutoff. Document the 10-minute per-account retry budget and high-frequency QPS.

- [ ] **Step 5: Run focused and full quality gates**

Run:

```bash
.venv/bin/ruff check .
.venv/bin/mypy src
PYTHONPATH=src .venv/bin/pytest -q
git diff --check
```

Expected: Ruff and mypy report no issues, all pytest tests pass, and `git diff --check` prints nothing.

- [ ] **Step 6: Perform clean-workspace CLI acceptance**

Create a temporary workspace with `mktemp -d`, materialize a Schema v2 config containing one research and one auxiliary account, confirm the jobs, and verify:

```bash
opinion-tracker jobs run-due \
  --workspace "$acceptance_workspace" \
  --output-root "$acceptance_workspace/reports" \
  --now 2026-08-07T21:02:00+08:00
```

uses cutoff `2026-08-07T21:00:00+08:00`; a controlled fake collector resumes at its saved page; a controlled fake SMTP sender creates one receipt and one checkpoint. Do not use real credentials in the acceptance fixture.

- [ ] **Step 7: Update local launchd prompts and validate them**

Replace the current separate `email-send` and `jobs complete` instructions in the daily and weekly launchd prompts with `jobs deliver`. Keep weekdays at 09:00 and 21:00 and weekly Sunday at 18:00. Run `plutil -lint` on both files, reload them with `launchctl bootout/bootstrap`, and inspect each registered job.

- [ ] **Step 8: Commit documentation and cleanup**

```bash
git add README.md SKILL.md references src/opinion_tracker/cli.py tests/test_jobs_cli.py
git commit -m "docs: document resilient scheduled reporting"
```

- [ ] **Step 9: Push and verify remote main**

Run:

```bash
git push origin main
git fetch origin main
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
git status --porcelain
```

Expected: local and remote commits match and the worktree is clean.
