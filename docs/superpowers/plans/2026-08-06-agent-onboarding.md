# Agent-first Onboarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a portable onboarding state machine that requires a user-confirmed task summary before any Xueqiu collection and then supports collection-to-report execution.

**Architecture:** A focused `task_state` module owns draft persistence, deterministic fingerprints, confirmation invalidation, and execution authorization. Typer commands expose the same state machine to terminal users and conversational Agents; the execution command validates confirmation before constructing a `RunRequest` or invoking the external Chrome runner.

**Tech Stack:** Python 3.11, Pydantic 2, Typer, pytest, existing external Chrome collector and reporting core.

## Global Constraints

- New workspaces never inherit a target from prior conversation or examples.
- `init --no-interactive` never waits for input and never creates a default task.
- User authorization may default to declared, but task target and task-summary confirmation never default to confirmed.
- QPS defaults to and may not exceed 1.
- Any execution-relevant draft change invalidates confirmation.
- No Cookie, Token, password, verification code, or browser credential is persisted.
- No Xueqiu browser runner call is allowed without a matching confirmation fingerprint.
- Existing personal Skills are not runtime dependencies.

---

### Task 1: Persistent task state and confirmation fingerprint

**Files:**
- Create: `src/opinion_tracker/task_state.py`
- Modify: `src/opinion_tracker/schemas.py`
- Create: `tests/test_task_state.py`

**Interfaces:**
- Produces: `TaskDraft`, `TaskRecord`, `TaskStore.load()`, `TaskStore.save_draft()`, `TaskStore.confirm()`, `TaskStore.require_confirmed()`.
- Persists: `.investor-opinion-tracker/task.json` with status, draft, fingerprint, and confirmation timestamp.

- [ ] **Step 1: Write failing tests for empty state, incomplete-draft rejection, confirmation, and invalidation**

```python
def test_new_store_requires_onboarding(tmp_path):
    assert TaskStore(tmp_path).load().status == "onboarding_required"

def test_confirmed_draft_is_invalidated_by_change(tmp_path):
    store = TaskStore(tmp_path)
    store.save_draft(complete_draft())
    confirmed = store.confirm()
    assert store.require_confirmed().fingerprint == confirmed.fingerprint
    store.save_draft(complete_draft(lookback_days=7))
    with pytest.raises(PermissionError, match="重新确认"):
        store.require_confirmed()
```

- [ ] **Step 2: Run tests and verify RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_task_state.py -q`
Expected: collection error because `opinion_tracker.task_state` does not exist.

- [ ] **Step 3: Implement the minimal state model**

Use SHA-256 over `TaskDraft.model_dump(mode="json")` serialized with sorted keys and compact separators. `save_draft` stores `draft` unless its fingerprint still matches an existing confirmation. `confirm` rejects absent or incomplete drafts. `require_confirmed` compares stored and current fingerprints.

- [ ] **Step 4: Run focused and full tests**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_task_state.py -q && PYTHONPATH=src .venv/bin/pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/opinion_tracker/task_state.py src/opinion_tracker/schemas.py tests/test_task_state.py
git commit -m "feat: add confirmed task state"
```

### Task 2: Non-interactive initialization and resumable terminal onboarding

**Files:**
- Modify: `src/opinion_tracker/cli.py`
- Modify: `src/opinion_tracker/onboarding.py`
- Modify: `tests/test_interfaces.py`

**Interfaces:**
- Changes: `init(workspace, no_interactive)` creates empty task state and landing.
- Produces commands: `onboard`, `task-status`, `task-summary`, and `task-confirm`.

- [ ] **Step 1: Write failing CLI tests**

```python
def test_noninteractive_init_never_prompts_or_creates_target(tmp_path):
    out = runner.invoke(app, ["init", "--workspace", str(tmp_path), "--no-interactive"])
    assert out.exit_code == 0
    assert "等待收集任务需求" in out.stdout
    assert TaskStore(tmp_path).load().draft is None

def test_onboard_creates_draft_then_requires_separate_confirmation(tmp_path):
    out = runner.invoke(app, ["onboard", "--workspace", str(tmp_path)], input=onboarding_answers())
    assert out.exit_code == 0
    assert "尚未执行" in out.stdout
    assert TaskStore(tmp_path).load().status == "draft"
```

Also test that default `init` starts the same questions, EOF or decline exits safely, JSON summaries are stable, and `task-confirm` rejects incomplete drafts.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_interfaces.py -q`
Expected: failures for missing options and commands.

- [ ] **Step 3: Implement minimal commands and revised landing**

Prompt one field at a time. Before accepting the default profile, print `将使用 mixed / balanced / 单笔计划亏损 0.5%` and ask for acceptance. `onboard` only saves a draft and prints a summary. `task-confirm` is the sole confirmation mutation.

- [ ] **Step 4: Run focused and full tests**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_interfaces.py -q && PYTHONPATH=src .venv/bin/pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/opinion_tracker/cli.py src/opinion_tracker/onboarding.py tests/test_interfaces.py
git commit -m "feat: add resumable onboarding commands"
```

### Task 3: Confirmed collection and report execution gate

**Files:**
- Create: `src/opinion_tracker/execution.py`
- Modify: `src/opinion_tracker/cli.py`
- Create: `tests/test_execution.py`

**Interfaces:**
- Produces: `execute_confirmed(workspace: Path, output: Path, collector: Collector | None = None) -> RunResult`.
- Produces CLI command: `opinion-tracker run --workspace <path> --output <path>`.
- Consumes: `TaskStore.require_confirmed()` before constructing `RunRequest`.

- [ ] **Step 1: Write failing tests proving the collector is untouched before confirmation**

```python
def test_unconfirmed_execution_never_calls_collector(tmp_path):
    collector = SpyCollector()
    with pytest.raises(PermissionError, match="确认"):
        execute_confirmed(tmp_path, tmp_path / "reports", collector)
    assert collector.calls == 0

def test_confirmed_execution_collects_and_writes_report(tmp_path):
    store_confirmed_task(tmp_path)
    result = execute_confirmed(tmp_path, tmp_path / "reports", FakeCollector())
    assert result.posts_collected == 1
    assert (tmp_path / "reports" / "report.md").exists()
    assert (tmp_path / "reports" / "posts.json").exists()
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_execution.py -q`
Expected: import failure for `opinion_tracker.execution`.

- [ ] **Step 3: Implement guarded execution**

Validate the confirmed task first, then construct `RunRequest`, collect, persist normalized posts, extract opinions, score candidates, and write report artifacts. Failed or incomplete collection preserves warnings and cannot produce active candidates. Mark completed only after artifacts are written.

- [ ] **Step 4: Add CLI error handling and verify tests**

Permission failures return non-zero with `请先运行 onboard，查看摘要并执行 task-confirm`. Browser or login failures remain recoverable and do not erase the draft.

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_execution.py tests/test_interfaces.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/opinion_tracker/execution.py src/opinion_tracker/cli.py tests/test_execution.py
git commit -m "feat: gate collection on confirmed task"
```

### Task 4: Portable Agent contract and consistent documentation

**Files:**
- Modify: `SKILL.md`
- Modify: `README.md`
- Modify: `references/cli.md`
- Modify: `references/workbuddy.md`
- Modify: `src/opinion_tracker/onboarding.py`
- Modify: `tests/test_skill_contract.py`

**Interfaces:**
- Documents: `init --no-interactive → Agent questions → task-summary → user confirmation → task-confirm → run → analysis → schedule offer`.

- [ ] **Step 1: Write failing contract assertions**

Require relevant documents to mention `--no-interactive`, `task-summary`, `task-confirm`, no historical target inheritance, and no collection before confirmation.

- [ ] **Step 2: Run tests and verify RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_skill_contract.py -q`
Expected: assertions fail on the old documents.

- [ ] **Step 3: Update all user and Agent guidance**

Remove wording that says to run immediately after init. State that examples never become default targets. Explain terminal and Agent paths separately with identical command names.

- [ ] **Step 4: Run contract and full tests**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_skill_contract.py -q && PYTHONPATH=src .venv/bin/pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add SKILL.md README.md references/cli.md references/workbuddy.md src/opinion_tracker/onboarding.py tests/test_skill_contract.py
git commit -m "docs: align agents on confirmed onboarding"
```

### Task 5: Verification, clean-user rehearsal, and publication

**Files:**
- Modify only if verification reveals a defect, following a new RED/GREEN cycle.

**Interfaces:**
- Validates the complete repository and remote installation path.

- [ ] **Step 1: Run static and automated verification**

```bash
.venv/bin/ruff check .
.venv/bin/mypy src
PYTHONPATH=src .venv/bin/pytest -q
.venv/bin/python /Users/summerchen/.codex/skills/.system/skill-creator/scripts/quick_validate.py .
git diff --check
```

- [ ] **Step 2: Rehearse a clean install without collection**

Clone into a new explicit temporary directory, create a Python 3.11 venv, install `.[mcp]`, and run `init --no-interactive`. Verify no browser request occurs, no target exists, and landing requests onboarding.

- [ ] **Step 3: Rehearse the confirmation gate**

Create a controlled draft, show the summary, prove `run` fails before confirmation, confirm it, then run a fake-collector integration test. Do not perform a real Xueqiu crawl merely to validate installation.

- [ ] **Step 4: Push and verify remote commit**

```bash
git push origin main
git status --short --branch
git rev-parse HEAD
git ls-remote origin refs/heads/main
```

Expected: clean tracking branch and matching local and remote hashes.
