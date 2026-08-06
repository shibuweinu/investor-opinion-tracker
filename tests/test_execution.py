from datetime import UTC, datetime

import pytest

from opinion_tracker.execution import execute_confirmed
from opinion_tracker.schemas import CollectionResult, NormalizedPost, TaskDraft
from opinion_tracker.task_state import TaskStore


class FakeCollector:
    def __init__(self):
        self.calls = 0

    def collect(self, request):
        self.calls += 1
        return CollectionResult(
            status="complete",
            posts=[
                NormalizedPost(
                    platform="xueqiu",
                    platform_post_id="1",
                    author_id=request.user_id,
                    published_at=datetime.now(UTC),
                    text="看好 SH600276",
                    url="https://xueqiu.com/u/1",
                )
            ],
        )


def save_draft(workspace, confirm=False):
    store = TaskStore(workspace)
    store.save_draft(TaskDraft(user_urls=["https://xueqiu.com/u/2292705444"]))
    if confirm:
        store.confirm()


def test_unconfirmed_execution_never_calls_collector(tmp_path):
    save_draft(tmp_path)
    collector = FakeCollector()
    with pytest.raises(PermissionError, match="确认"):
        execute_confirmed(tmp_path, tmp_path / "reports", collector)
    assert collector.calls == 0


def test_confirmed_execution_collects_and_writes_report(tmp_path):
    save_draft(tmp_path, confirm=True)
    result = execute_confirmed(tmp_path, tmp_path / "reports", FakeCollector())
    assert result.posts_collected == 1
    assert (tmp_path / "reports" / "posts.json").exists()
    assert (tmp_path / "reports" / "evidence-pack.json").exists()
    instructions = (tmp_path / "reports" / "ANALYZE.md").read_text(encoding="utf-8")
    assert "按博主" in instructions and "失效条件" in instructions
    assert "不得输出仓位" in instructions
    assert not (tmp_path / "reports" / "report.md").exists()
    assert TaskStore(tmp_path).load().status == "completed"
