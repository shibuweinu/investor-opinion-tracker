from __future__ import annotations

from pathlib import Path

from .collectors.base import Collector
from .config import Settings
from .opinions import extract_opinions
from .reporting import write_artifacts
from .schemas import RunRequest, RunResult
from .scoring import score_candidate
from .storage import Repository


class OpinionTrackerService:
    def __init__(self, workspace: Path, collector: Collector):
        self.workspace, self.collector = workspace, collector
        self.settings = Settings.load(workspace)
        self.repository = Repository(workspace / ".investor-opinion-tracker" / "state.db")

    def run(self, request: RunRequest) -> RunResult:
        collected = self.collector.collect(request)
        self.repository.upsert_posts(collected.posts)
        opinions = extract_opinions(collected.posts)
        candidates = [
            score_candidate(item, 0.5, 0.5, "C", collected.status == "complete") for item in opinions
        ]
        result = RunResult(
            status=collected.status,
            posts_collected=len(collected.posts),
            opinions=opinions,
            candidates=candidates,
            warnings=collected.warnings,
        )
        write_artifacts(
            self.workspace / ".investor-opinion-tracker" / "reports", result, self.settings.trader_profile
        )
        return result
