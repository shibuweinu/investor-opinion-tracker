# Private Config Repository Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add portable, private Git-backed user configuration with safe onboarding, conflict detection, device-scoped trusted auto-apply, and scheduled-run preflight.

**Architecture:** A strict Pydantic sync document is the only data allowed across the Git boundary. A focused Git adapter handles repository mechanics, while a sync service owns comparison, import/export, trust checks, and audit records; CLI and scheduled execution consume that service without learning Git internals.

**Tech Stack:** Python 3.11+, Pydantic 2, Typer, standard-library `subprocess`, macOS Keychain adapter with a portable local fallback interface, pytest, Git/GitHub CLI for real acceptance only.

## Global Constraints

- The product code repository never stores user-instance configuration.
- Synced data is allowlisted; credentials, cookies, reports, logs, databases, absolute paths, and unknown fields are rejected.
- Core synchronization uses ordinary Git; GitHub CLI is optional and used only to create/inspect GitHub repositories.
- A remote `trusted_auto_apply` preference never grants device trust by itself.
- A new device must explicitly authorize the canonical repository owner, URL, and Git identity.
- Safe mode invalidates confirmation for execution-field changes; trusted mode records an auditable `auto_applied` confirmation.
- Never force-push, auto-merge divergent histories, or upload a partial configuration.
- Scheduled sync has a finite timeout and retains the last confirmed safe configuration on transient failure.

---

### Task 1: Define the portable configuration contract

**Files:**
- Create: `src/opinion_tracker/sync_models.py`
- Modify: `src/opinion_tracker/task_state.py`
- Test: `tests/test_sync_models.py`

**Interfaces:**
- Consumes: `TaskDraft`, `TraderProfile`, and `task_fingerprint(draft)`.
- Produces: `AccountConfig`, `ReportSchedule`, `SyncPreferences`, `PortableConfig`, `SyncBinding`, `SyncAuditEntry`, `TaskStore.confirm_auto_applied(draft, revision)`.

- [ ] **Step 1: Write failing schema and confirmation tests**

```python
def test_portable_config_rejects_unknown_and_sensitive_fields():
    payload = valid_portable_payload() | {"cookie": "secret"}
    with pytest.raises(ValidationError):
        PortableConfig.model_validate(payload)

def test_auto_applied_confirmation_is_auditable(tmp_path):
    record = TaskStore(tmp_path).confirm_auto_applied(draft(), "rev-2")
    assert record.status == "confirmed"
    assert record.confirmation_source == "auto_applied"
    assert record.source_revision == "rev-2"
```

- [ ] **Step 2: Run the focused tests and observe failure**

Run: `.venv/bin/pytest tests/test_sync_models.py -v`
Expected: FAIL because `opinion_tracker.sync_models` and `confirm_auto_applied` do not exist.

- [ ] **Step 3: Implement strict models and confirmation metadata**

```python
class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class SyncPreferences(StrictModel):
    trusted_auto_apply: bool = False

class ReportSchedule(StrictModel):
    enabled: bool = True
    lookback_days_by_role: dict[Literal["research", "auxiliary_news"], int]
    weekdays: list[int]
    hour: int
    minute: int = 0
    timezone: str = "Asia/Shanghai"

class PortableConfig(StrictModel):
    schema_version: Literal[1] = 1
    tracked_accounts: list[AccountConfig]
    reports: dict[Literal["daily", "weekly"], ReportSchedule]
    trader_profile: TraderProfile
    report_preferences: ReportPreferences
    sync: SyncPreferences = SyncPreferences()
    updated_at: datetime
    revision: str
```

Extend `TaskRecord` with optional `confirmation_source: Literal["user", "auto_applied"]` and `source_revision`; make `confirm()` record `user`, and implement `confirm_auto_applied()` using the current time and recomputed fingerprint.

- [ ] **Step 4: Run focused and existing state tests**

Run: `.venv/bin/pytest tests/test_sync_models.py tests/test_task_state.py -v`
Expected: PASS.

- [ ] **Step 5: Commit the contract**

```bash
git add src/opinion_tracker/sync_models.py src/opinion_tracker/task_state.py tests/test_sync_models.py
git commit -m "feat: define portable configuration schema"
```

### Task 2: Implement bounded Git repository operations

**Files:**
- Create: `src/opinion_tracker/git_repository.py`
- Test: `tests/test_git_repository.py`

**Interfaces:**
- Consumes: repository URL, local checkout path, timeout seconds.
- Produces: `GitRepository.clone_or_open()`, `fetch()`, `head()`, `remote_head()`, `is_ancestor()`, `commit(files, message)`, `push_fast_forward()`, and `canonical_remote()`.

- [ ] **Step 1: Write failing tests with a local bare remote**

```python
def test_push_and_fetch_are_fast_forward_only(bare_remote, tmp_path):
    first = GitRepository(str(bare_remote), tmp_path / "first", timeout=5)
    first.clone_or_open()
    (first.path / "config.json").write_text("{}")
    first.commit(["config.json"], "initial config")
    first.push_fast_forward()
    assert first.remote_head() == first.head()

def test_divergence_is_reported_not_force_pushed(diverged_repositories):
    with pytest.raises(GitConflictError):
        diverged_repositories.local.push_fast_forward()
```

- [ ] **Step 2: Verify the tests fail**

Run: `.venv/bin/pytest tests/test_git_repository.py -v`
Expected: FAIL because the adapter is absent.

- [ ] **Step 3: Implement a subprocess adapter without shell execution**

```python
def _run(self, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(self.path), *args],
        check=True, capture_output=True, text=True, timeout=self.timeout,
    )
    return completed.stdout.strip()
```

Normalize SSH/HTTPS GitHub URLs to an owner/repository identity, use argument arrays, fetch explicitly, require ancestry before merge/push, and never invoke `--force`.

- [ ] **Step 4: Run adapter tests**

Run: `.venv/bin/pytest tests/test_git_repository.py -v`
Expected: PASS, including timeout and divergence cases.

- [ ] **Step 5: Commit the adapter**

```bash
git add src/opinion_tracker/git_repository.py tests/test_git_repository.py
git commit -m "feat: add safe git configuration adapter"
```

### Task 3: Build export, import, comparison, and audit service

**Files:**
- Create: `src/opinion_tracker/config_sync.py`
- Test: `tests/test_config_sync.py`

**Interfaces:**
- Consumes: `PortableConfig`, `GitRepository`, local task workspaces, `SyncBinding`.
- Produces: `ConfigSyncService.connect()`, `status()`, `prepare_push()`, `push()`, `prepare_pull()`, `apply_pull()`, plus `SyncStatus` and `ConfigDiff`.

- [ ] **Step 1: Write failing end-to-end service tests**

```python
def test_second_workspace_restores_allowlisted_configuration(sync_fixture):
    sync_fixture.first.push(sync_fixture.portable_config)
    preview = sync_fixture.second.prepare_pull()
    assert preview.diff.execution_fields_changed
    sync_fixture.second.apply_pull(preview, trusted=False)
    assert TaskStore(sync_fixture.second_workspace).load().status == "draft"

def test_export_contains_no_local_or_sensitive_material(sync_fixture):
    exported = sync_fixture.first.prepare_push().document.model_dump_json()
    forbidden = ["Cookie", "smtp", str(sync_fixture.first_workspace), "state.db", "report.md"]
    assert all(value not in exported for value in forbidden)
```

- [ ] **Step 2: Verify service tests fail**

Run: `.venv/bin/pytest tests/test_config_sync.py -v`
Expected: FAIL because the sync service is absent.

- [ ] **Step 3: Implement allowlisted conversion and four-state comparison**

```python
class SyncState(StrEnum):
    SYNCED = "synced"
    LOCAL_AHEAD = "local_ahead"
    REMOTE_AHEAD = "remote_ahead"
    CONFLICT = "conflict"

def apply_pull(self, preview: PullPreview, *, trusted: bool) -> TaskRecord:
    draft = portable_to_task_draft(preview.document, self.report_kind)
    if trusted:
        return self.task_store.confirm_auto_applied(draft, preview.document.revision)
    return self.task_store.save_draft(draft)
```

Write only `README.md`, `config.json`, and `.gitignore` to the checkout; serialize through `PortableConfig`; store binding, base commit, and audit JSONL only in the local workspace. Convert `lookback_days_by_role` into the existing daily-research, daily-auxiliary-news, and weekly task workspaces so the 5/2/7-day policy remains executable.

- [ ] **Step 4: Run sync service and state tests**

Run: `.venv/bin/pytest tests/test_config_sync.py tests/test_task_state.py -v`
Expected: PASS for synced, local-ahead, remote-ahead, conflict, sensitive-data, and restore cases.

- [ ] **Step 5: Commit the service**

```bash
git add src/opinion_tracker/config_sync.py tests/test_config_sync.py
git commit -m "feat: synchronize private user configuration"
```

### Task 4: Add device trust and scheduled preflight

**Files:**
- Create: `src/opinion_tracker/device_trust.py`
- Create: `src/opinion_tracker/sync_preflight.py`
- Modify: `src/opinion_tracker/execution.py`
- Test: `tests/test_sync_preflight.py`

**Interfaces:**
- Consumes: canonical remote, owner, Git identity, repository visibility verifier, `ConfigSyncService`.
- Produces: `DeviceTrustStore.authorize()`, `revoke()`, `is_trusted()`, `preflight_scheduled_run(workspace, timeout=15) -> PreflightResult`.

- [ ] **Step 1: Write failing trust and preflight tests**

```python
def test_remote_flag_alone_does_not_grant_trust(preflight_fixture):
    preflight_fixture.remote_config.sync.trusted_auto_apply = True
    result = preflight_fixture.run()
    assert result.action == "confirmation_required"

def test_trusted_fast_forward_auto_applies_and_runs(preflight_fixture):
    preflight_fixture.authorize_device()
    result = preflight_fixture.run()
    assert result.action == "run"
    assert result.record.confirmation_source == "auto_applied"

def test_identity_change_revokes_trust(preflight_fixture):
    preflight_fixture.authorize_device()
    preflight_fixture.git_identity = "different@example.com"
    assert preflight_fixture.run().action == "confirmation_required"
```

- [ ] **Step 2: Verify preflight tests fail**

Run: `.venv/bin/pytest tests/test_sync_preflight.py -v`
Expected: FAIL because trust and preflight modules are absent.

- [ ] **Step 3: Implement local secure trust records and bounded fallback**

```python
class TrustedRepository(BaseModel):
    canonical_remote: str
    owner: str
    git_identity: str
    authorized_at: datetime

def is_trusted(self, current: RepositoryIdentity) -> bool:
    return self.load() == TrustedRepository.model_validate(current.model_dump())
```

Use macOS Keychain when available; expose an injected test backend and a permission-0600 local backend for non-macOS. Preflight auto-applies only a private, identity-matching, fast-forward update. Transient fetch failure returns `run_last_confirmed`; validation, conflict, or identity failure returns `run_last_confirmed_with_alert`; safe-mode execution changes return `confirmation_required` and skip that run.

- [ ] **Step 4: Run preflight and execution tests**

Run: `.venv/bin/pytest tests/test_sync_preflight.py tests/test_execution.py -v`
Expected: PASS.

- [ ] **Step 5: Commit trust and preflight**

```bash
git add src/opinion_tracker/device_trust.py src/opinion_tracker/sync_preflight.py src/opinion_tracker/execution.py tests/test_sync_preflight.py
git commit -m "feat: add trusted scheduled config preflight"
```

### Task 5: Expose onboarding and sync CLI workflows

**Files:**
- Modify: `src/opinion_tracker/cli.py`
- Modify: `src/opinion_tracker/onboarding.py`
- Test: `tests/test_config_sync_cli.py`

**Interfaces:**
- Consumes: all Task 1-4 public interfaces.
- Produces: `init --config-repo`, `config-connect`, `config-status`, `config-push`, `config-pull`, `config-trust`, `config-untrust`, and `scheduled-run` commands.

- [ ] **Step 1: Write failing CLI contract tests**

```python
def test_noninteractive_init_reports_three_remote_choices(tmp_path):
    result = runner.invoke(app, ["init", "--workspace", str(tmp_path), "--no-interactive"])
    assert result.exit_code == 0
    assert all(text in result.stdout for text in ["restore", "create", "skip"])

def test_config_repo_only_previews_until_confirmed(tmp_path, remote):
    result = runner.invoke(app, ["init", "--workspace", str(tmp_path), "--no-interactive",
                                 "--config-repo", remote])
    assert "等待确认导入" in result.stdout
    assert TaskStore(tmp_path).load().status == "onboarding_required"
```

- [ ] **Step 2: Verify CLI tests fail**

Run: `.venv/bin/pytest tests/test_config_sync_cli.py -v`
Expected: FAIL because the commands and output contracts are absent.

- [ ] **Step 3: Add commands with explicit mutation confirmations**

```python
@app.command("config-trust")
def config_trust(workspace: Path = typer.Option(...), yes: bool = typer.Option(False, "--yes")) -> None:
    preview = service_for(workspace).trust_preview()
    typer.echo(preview.human_summary())
    if not yes and not typer.confirm("信任该私有仓库并自动应用后续合法更新？"):
        raise typer.Abort()
    service_for(workspace).authorize_device(preview)
```

Interactive init asks restore/create/skip; non-interactive init prints stable JSON-compatible action names. `--config-repo` fetches and previews only. Push, pull, trust, creation, and scheduler installation each retain their own confirmation boundary.

- [ ] **Step 4: Run all CLI and onboarding tests**

Run: `.venv/bin/pytest tests/test_config_sync_cli.py tests/test_interfaces.py tests/test_task_state.py -v`
Expected: PASS.

- [ ] **Step 5: Commit CLI workflows**

```bash
git add src/opinion_tracker/cli.py src/opinion_tracker/onboarding.py tests/test_config_sync_cli.py
git commit -m "feat: add personal config onboarding commands"
```

### Task 6: Document portability and complete real acceptance

**Files:**
- Modify: `README.md`
- Modify: `SKILL.md`
- Modify: `references/workbuddy.md`
- Create: `docs/config-sync.md`
- Modify: `.gitignore`
- Test: `tests/test_skill_contract.py`
- Test: `tests/test_portable_adapters.py`

**Interfaces:**
- Consumes: stable CLI commands from Task 5.
- Produces: consistent installation, restore, trust, schedule, recovery, and privacy instructions for humans and Agents.

- [ ] **Step 1: Write failing documentation contract tests**

```python
@pytest.mark.parametrize("path", ["README.md", "SKILL.md", "references/workbuddy.md"])
def test_docs_explain_remote_config_choices_and_trust(path):
    text = Path(path).read_text()
    for phrase in ["config-connect", "restore", "create", "skip", "trusted_auto_apply"]:
        assert phrase in text
```

- [ ] **Step 2: Verify documentation tests fail**

Run: `.venv/bin/pytest tests/test_skill_contract.py tests/test_portable_adapters.py -v`
Expected: FAIL for missing sync workflow terms.

- [ ] **Step 3: Update all Agent contracts and operator documentation**

Document exact commands, the three onboarding choices, local-only secrets, device trust, scheduled preflight, failure behavior, and migration from existing workspaces. Add local sync checkout, binding, audit, and trust fallback files to `.gitignore` without ignoring the public schema or docs.

- [ ] **Step 4: Run full static and automated verification**

Run: `.venv/bin/ruff check . && .venv/bin/mypy src && .venv/bin/pytest -q`
Expected: all commands exit 0.

- [ ] **Step 5: Create and verify the real private repository**

Run:

```bash
gh auth status
gh repo create shibuweinu/investor-opinion-tracker-config --private --disable-issues --disable-wiki
.venv/bin/opinion-tracker config-connect --workspace /Users/summerchen/Documents/Codex/2026-08-05/ni/acceptance-new-user-agent-onboarding/data --repo git@github.com:shibuweinu/investor-opinion-tracker-config.git
.venv/bin/opinion-tracker config-push --workspace /Users/summerchen/Documents/Codex/2026-08-05/ni/acceptance-new-user-agent-onboarding/data --yes
gh repo view shibuweinu/investor-opinion-tracker-config --json visibility,nameWithOwner
```

Expected: visibility is `PRIVATE`; remote history contains only `.gitignore`, `README.md`, and `config.json`; `config.json` contains ten accounts, daily 5-day research plus 2-day auxiliary-news behavior, weekly 7-day behavior, Asia/Shanghai schedules, balanced mixed profile, 3% risk, optional position sizing, and `trusted_auto_apply: true`.

- [ ] **Step 6: Restore into a temporary clean workspace and authorize this device**

Run:

```bash
tmp_dir=$(mktemp -d)
.venv/bin/opinion-tracker init --workspace "$tmp_dir" --no-interactive --config-repo git@github.com:shibuweinu/investor-opinion-tracker-config.git
.venv/bin/opinion-tracker config-pull --workspace "$tmp_dir" --yes
.venv/bin/opinion-tracker config-trust --workspace /Users/summerchen/Documents/Codex/2026-08-05/ni/acceptance-new-user-agent-onboarding/data --yes
```

Expected: preview precedes import; the temporary workspace restores all allowed settings but no credentials, reports, logs, launchd files, or absolute paths; current device trust succeeds only after explicit authorization.

- [ ] **Step 7: Inspect remote history for forbidden material**

Run:

```bash
git -C /Users/summerchen/Documents/Codex/2026-08-05/ni/acceptance-new-user-agent-onboarding/data/.investor-opinion-tracker/config-repo log --all -p -- . ':!README.md' | rg -i 'cookie|smtp|authorization.?code|/Users/|state\.db|report\.md'
```

Expected: no matches and exit code 1 from `rg`.

- [ ] **Step 8: Commit documentation and push the product repository**

```bash
git add README.md SKILL.md references/workbuddy.md docs/config-sync.md .gitignore tests/test_skill_contract.py tests/test_portable_adapters.py
git commit -m "docs: explain private config synchronization"
git push origin main
```

- [ ] **Step 9: Verify clean final state**

Run: `git status --short && git log -8 --oneline && gh repo view shibuweinu/investor-opinion-tracker-config --json visibility,nameWithOwner`
Expected: clean product worktree, implementation commits visible on `origin/main`, and private personal configuration repository verified.
