from datetime import UTC, datetime, timedelta

from test_config_migration import payload

from opinion_tracker.config_migration import migrate_portable_config
from opinion_tracker.execution import execute_confirmed
from opinion_tracker.job_state import JobStore
from opinion_tracker.run_state import RunIdentity, RunStateStore, UserPageState
from opinion_tracker.schemas import CollectionResult, NormalizedPost, TaskDraft
from opinion_tracker.task_state import TaskStore


class Collector:
    def __init__(self):
        self.requests = []

    def collect(self, request):
        self.requests.append(request)
        now = request.as_of or datetime.now(UTC)
        return CollectionResult(
            status="complete",
            posts=[
                NormalizedPost(
                    platform="xueqiu",
                    platform_post_id="new",
                    author_id=request.user_id,
                    published_at=now - timedelta(hours=1),
                    text="new",
                    url="https://x/new",
                ),
                NormalizedPost(
                    platform="xueqiu",
                    platform_post_id="old",
                    author_id=request.user_id,
                    published_at=now - timedelta(days=3),
                    text="old",
                    url="https://x/old",
                ),
            ],
        )


def test_jobs_materialize_confirm_and_filter_incremental_window(tmp_path):
    store = JobStore(tmp_path)
    store.materialize(migrate_portable_config(payload()))
    assert store.task_store("morning").load().status == "draft"
    store.confirm("morning")
    cutoff = datetime(2026, 8, 7, 9, tzinfo=UTC)
    store.mark_success("evening", cutoff - timedelta(hours=12))
    collector = Collector()
    result = store.run("morning", tmp_path / "out", cutoff, collector=collector)
    assert result.posts_collected == 1
    assert store.window("morning", cutoff).since == cutoff - timedelta(hours=12)
    assert {request.since for request in collector.requests} == {cutoff - timedelta(hours=12)}
    analyze = (tmp_path / "out" / "ANALYZE.md").read_text(encoding="utf-8")
    assert "--market-as-of 2026-08-07T09:00:00+00:00" in analyze


def test_checkpoint_advances_only_after_verified_completion(tmp_path):
    store = JobStore(tmp_path)
    store.materialize(migrate_portable_config(payload()))
    store.confirm("morning")
    cutoff = datetime(2026, 8, 7, 9, tzinfo=UTC)
    store.run("morning", tmp_path / "out", cutoff, collector=Collector())
    assert store.window("morning", cutoff).since is None
    store.complete("morning", cutoff, verified=True)
    assert store.window("evening", cutoff).since == cutoff


def test_execution_uses_resumable_collector_and_skips_completed_user(tmp_path):
    job_workspace = tmp_path / "job"
    task_store = TaskStore(job_workspace)
    task_store.save_draft(
        TaskDraft(user_urls=["https://xueq.com/u/1", "https://xueq.com/u/2"])
    )
    task_store.confirm()
    cutoff = datetime(2026, 8, 7, 9, tzinfo=UTC)
    run_store = RunStateStore(tmp_path, RunIdentity(job_id="morning", cutoff=cutoff))
    run_store.initialize(["1", "2"])
    run_store.save_user(UserPageState(user_id="1", status="complete", next_page=3))
    run_store.merge_posts(
        [
            NormalizedPost(
                platform="xueqiu",
                platform_post_id="saved",
                author_id="1",
                published_at=cutoff - timedelta(hours=2),
                text="saved",
                url="https://xueq.com/1/saved",
            )
        ]
    )

    class ResumableCollector:
        def __init__(self):
            self.users = []

        def collect(self, request):
            raise AssertionError("应使用可恢复入口")

        def collect_resumable(self, request, state_store, user_state):
            self.users.append(request.user_id)
            created = NormalizedPost(
                platform="xueqiu",
                platform_post_id="new",
                author_id=request.user_id,
                published_at=cutoff - timedelta(hours=1),
                text="new",
                url="https://xueq.com/2/new",
            )
            state_store.merge_posts([created])
            user_state.status = "complete"
            state_store.save_user(user_state)
            return CollectionResult(status="complete", posts=[created])

    collector = ResumableCollector()
    result = execute_confirmed(
        job_workspace,
        tmp_path / "out",
        collector,
        until=cutoff,
        complete_state=False,
        run_store=run_store,
    )

    assert collector.users == ["2"]
    assert result.status == "complete"
    assert result.posts_collected == 2


def test_execution_keeps_legacy_custom_collector_compatible_with_run_state(tmp_path):
    job_workspace = tmp_path / "job"
    task_store = TaskStore(job_workspace)
    task_store.save_draft(TaskDraft(user_urls=["https://xueq.com/u/1"]))
    task_store.confirm()
    cutoff = datetime(2026, 8, 7, 9, tzinfo=UTC)
    run_store = RunStateStore(tmp_path, RunIdentity(job_id="morning", cutoff=cutoff))
    collector = Collector()

    result = execute_confirmed(
        job_workspace,
        tmp_path / "out",
        collector,
        until=cutoff,
        complete_state=False,
        run_store=run_store,
    )

    assert result.status == "complete"
    assert run_store.load_user("1").status == "complete"
