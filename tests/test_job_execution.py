from datetime import UTC, datetime, timedelta

from test_config_migration import payload

from opinion_tracker.config_migration import migrate_portable_config
from opinion_tracker.job_state import JobStore
from opinion_tracker.schemas import CollectionResult, NormalizedPost


class Collector:
    def collect(self, request):
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
    result = store.run("morning", tmp_path / "out", cutoff, collector=Collector())
    assert result.posts_collected == 1
    assert store.window("morning", cutoff).since == cutoff - timedelta(hours=12)


def test_checkpoint_advances_only_after_verified_completion(tmp_path):
    store = JobStore(tmp_path)
    store.materialize(migrate_portable_config(payload()))
    store.confirm("morning")
    cutoff = datetime(2026, 8, 7, 9, tzinfo=UTC)
    store.run("morning", tmp_path / "out", cutoff, collector=Collector())
    assert store.window("morning", cutoff).since is None
    store.complete("morning", cutoff, verified=True)
    assert store.window("evening", cutoff).since == cutoff
