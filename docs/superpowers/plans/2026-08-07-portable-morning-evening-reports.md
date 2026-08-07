# Portable Morning and Evening Reports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace fixed daily workspaces with portable report jobs, incremental morning/evening windows, Schema v2 migration, and safe product update discovery.

**Architecture:** Schema v2 stores report jobs independently of local paths. A job store materializes each job under one workspace, a checkpoint service calculates successful incremental windows, and CLI commands expose the same lifecycle to every Agent; product-code updates remain separate from private-config synchronization.

**Tech Stack:** Python 3.11+, Pydantic 2, Typer, Git subprocess adapter, pytest, launchd adapter/docs.

## Global Constraints

- New users and existing users use the same job CLI and confirmation gates.
- Morning runs weekdays at 09:00, evening weekdays at 21:00, weekly Sunday at 18:00 in Asia/Shanghai.
- Research history is 5 days; auxiliary news history is 2 days; weekly history is 7 days.
- Failed or incomplete reports never advance checkpoints.
- `7X24快讯` remains auxiliary-only; `7977283243` is a research account.
- Product updates never overwrite personal configuration or credentials.
- Unknown higher schema versions fail closed and instruct users to update the product.

---

### Task 1: Schema v2 and migration

**Files:**
- Modify: `src/opinion_tracker/sync_models.py`
- Create: `src/opinion_tracker/config_migration.py`
- Test: `tests/test_config_migration.py`

**Interfaces:**
- Produces: `ReportJob`, `PortableConfigV2`, `migrate_portable_config(payload) -> PortableConfigV2`.

- [ ] Write failing tests proving v1 daily becomes evening plus morning, weekly remains weekly, and schema 3 is rejected.
- [ ] Run `PYTHONPATH=src .venv/bin/pytest tests/test_config_migration.py -q`; expect failures for missing migration.
- [ ] Implement strict v2 jobs with stable IDs, schedules, role lookbacks, incremental source, and migration.
- [ ] Run the focused tests; expect PASS.
- [ ] Commit with `git commit -m "feat: migrate personal config to report jobs"`.

### Task 2: Portable job state and incremental checkpoints

**Files:**
- Create: `src/opinion_tracker/job_state.py`
- Test: `tests/test_job_state.py`

**Interfaces:**
- Produces: `JobStore.list()`, `materialize(config)`, `window(job_id, now)`, `mark_success(job_id, cutoff)`, and `JobWindow`.

- [ ] Write failing tests for three materialized jobs, morning/evening boundaries, weekend carryover, and failure without checkpoint mutation.
- [ ] Run focused tests and observe missing module failures.
- [ ] Implement job directories under `.investor-opinion-tracker/jobs/<job-id>` and checkpoint JSON written only by `mark_success`.
- [ ] Run focused tests; expect PASS.
- [ ] Commit with `git commit -m "feat: add portable report job state"`.

### Task 3: Atomic config sync and new tracked account

**Files:**
- Modify: `src/opinion_tracker/config_sync.py`
- Modify: `src/opinion_tracker/sync_preflight.py`
- Test: `tests/test_config_sync_v2.py`

**Interfaces:**
- Consumes: `PortableConfigV2`, `JobStore`.
- Produces: atomic `apply_config(config, trusted)` and v2 remote push/pull.

- [ ] Write failing tests proving all jobs validate before replacement, failed validation preserves old jobs, and account `7977283243` is research.
- [ ] Run tests and observe failure.
- [ ] Implement temporary-directory staging followed by atomic replacement and auditable auto-applied confirmations.
- [ ] Run sync, migration, and preflight tests; expect PASS.
- [ ] Commit with `git commit -m "feat: atomically sync portable report jobs"`.

### Task 4: Unified job and update CLI

**Files:**
- Modify: `src/opinion_tracker/cli.py`
- Modify: `src/opinion_tracker/onboarding.py`
- Create: `src/opinion_tracker/product_update.py`
- Test: `tests/test_jobs_cli.py`
- Test: `tests/test_product_update.py`

**Interfaces:**
- Produces: `jobs list`, `jobs summary`, `jobs confirm`, `jobs run`, `jobs run-due`, `update-check`, and `update`.

- [ ] Write failing CLI tests for job discovery without path knowledge and product updates that use `git pull --ff-only` without touching the configured workspace.
- [ ] Run focused tests and observe missing commands.
- [ ] Implement commands; `update-check` fetches and compares commits, while `update` requires a clean product tree, fast-forward pulls, and prints the dependency reinstall command.
- [ ] Run CLI and onboarding tests; expect PASS.
- [ ] Commit with `git commit -m "feat: add portable jobs and safe product updates"`.

### Task 5: Documentation, private configuration, and schedules

**Files:**
- Modify: `README.md`
- Modify: `SKILL.md`
- Modify: `references/workbuddy.md`
- Modify: `docs/config-sync.md`
- Test: `tests/test_skill_contract.py`

**Interfaces:**
- Documents one workflow for Codex, Claude, WorkBuddy, and humans.

- [ ] Write failing documentation tests for morning/evening jobs, `update-check`, and the separation of product/config updates.
- [ ] Update landing and all Agent guides.
- [ ] Run Ruff, mypy, and full pytest; expect zero failures.
- [ ] Migrate and push `shibuweinu/investor-opinion-tracker-config` to Schema v2 with 11 accounts and trusted auto-apply.
- [ ] Verify a fresh temporary clone restores morning/evening/weekly jobs without credentials or paths.
- [ ] Replace the current local schedule with weekday 09:00 and 21:00 plus Sunday 18:00, validate and reload it.
- [ ] Merge to `main`, rerun full verification, push product `main`, and verify both remote heads.
