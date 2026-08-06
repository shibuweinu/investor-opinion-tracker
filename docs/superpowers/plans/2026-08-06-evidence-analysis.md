# Evidence Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox syntax.

**Goal:** Replace one-post-one-opinion reporting with an auditable evidence-pack handoff and optional position sizing.

**Architecture:** Add deterministic evidence classification and packaging, integrate it into confirmed execution, then align onboarding and Agent documentation. The host Agent performs semantic synthesis from the generated pack.

**Tech Stack:** Python 3.11, Pydantic, Typer, pytest.

## Global Constraints

- Tests must fail before implementation changes.
- Position sizing defaults off.
- Every evidence item retains its source post ID and URL.
- `run` must not label an unreviewed heuristic table as a final report.

### Task 1: Evidence classifier and pack

**Files:** Create `src/opinion_tracker/evidence.py`, `tests/test_evidence.py`; modify `schemas.py`.

- [ ] Write tests for author grouping, empty/forward/question exclusion, formal evidence reduction, and source traceability.
- [ ] Run focused tests and observe missing-module failure.
- [ ] Implement minimal classifier and pack models.
- [ ] Run focused and full tests.

### Task 2: Execution artifacts and optional position flag

**Files:** Modify `execution.py`, `task_state.py`, `cli.py`, `onboarding.py`, and related tests.

- [ ] Write failing tests requiring `evidence-pack.json`, `ANALYZE.md`, and default `include_position_sizing=false`.
- [ ] Implement artifacts and onboarding option; remove premature heuristic `report.md` generation from `run`.
- [ ] Verify confirmation invalidates when the position option changes.

### Task 3: Agent contract and real-data verification

**Files:** Modify `SKILL.md`, `README.md`, references and contract tests.

- [ ] Write failing documentation contract tests.
- [ ] Document required Agent synthesis and final-report validation.
- [ ] Run full static checks and tests.
- [ ] Reprocess the captured 235-post fixture and verify evidence reduction, author coverage, traceability and no default position advice.
- [ ] Merge to `main`, test merged tree, push, and verify remote hash.
