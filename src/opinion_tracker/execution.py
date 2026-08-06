from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from .collectors.external_chrome import ExternalChromeXueqiuCollector
from .opinions import extract_opinions
from .reporting import write_artifacts
from .schemas import CollectionResult, RunRequest, RunResult
from .scoring import score_candidate
from .task_state import TaskStore


class Collector(Protocol):
    def collect(self, request: RunRequest) -> CollectionResult: ...


def execute_confirmed(
    workspace: Path, output: Path, collector: Collector | None = None
) -> RunResult:
    store = TaskStore(workspace)
    record = store.require_confirmed()
    assert record.draft is not None
    draft = record.draft
    active_collector = collector or ExternalChromeXueqiuCollector()
    posts, warnings = [], []
    complete = True
    for user_url in draft.user_urls:
        collected = active_collector.collect(
            RunRequest(
                user_url=user_url,
                lookback_days=draft.lookback_days,
                qps=draft.qps,
                authorization_confirmed=draft.authorization_confirmed,
            )
        )
        posts.extend(collected.posts)
        warnings.extend(collected.warnings)
        complete = complete and collected.status == "complete"
    opinions = extract_opinions(posts)
    candidates = [score_candidate(item, 0.5, 0.5, "C", complete) for item in opinions]
    result = RunResult(
        status="complete" if complete else "incomplete",
        posts_collected=len(posts),
        opinions=opinions,
        candidates=candidates,
        warnings=warnings,
    )
    output.mkdir(parents=True, exist_ok=True)
    (output / "posts.json").write_text(
        json.dumps([item.model_dump(mode="json") for item in posts], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_artifacts(output, result, draft.trader_profile)
    store.complete()
    return result
