import json
import os
from datetime import datetime

import pytest

from opinion_tracker.run_state import (
    RunAlreadyActive,
    RunIdentity,
    RunLock,
    RunStateStore,
    UserPageState,
)
from opinion_tracker.schemas import NormalizedPost


def cutoff() -> datetime:
    return datetime.fromisoformat("2026-08-07T21:00:00+08:00")


def post(identity: str) -> NormalizedPost:
    return NormalizedPost(
        platform="xueqiu",
        platform_post_id=identity,
        author_id="1",
        published_at=cutoff(),
        text=identity,
        url=f"https://xueqiu.com/1/{identity}",
    )


def test_run_state_persists_page_and_deduplicates_posts(tmp_path):
    identity = RunIdentity(job_id="evening", cutoff=cutoff())
    store = RunStateStore(tmp_path, identity)
    store.initialize(["1"])
    store.save_user(UserPageState(user_id="1", next_page=2, status="running"))
    store.merge_posts([post("a"), post("a"), post("b")])

    assert store.load_user("1").next_page == 2
    assert [item.platform_post_id for item in store.posts()] == ["a", "b"]


def test_run_state_rejects_mismatched_identity(tmp_path):
    store = RunStateStore(tmp_path, RunIdentity(job_id="morning", cutoff=cutoff()))
    store.initialize(["1"])
    payload = json.loads(store.state_path.read_text())
    payload["run_id"] = "different"
    store.state_path.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="运行状态"):
        store.load()


def test_run_lock_prevents_concurrent_owner(tmp_path):
    store = RunStateStore(tmp_path, RunIdentity(job_id="evening", cutoff=cutoff()))
    store.initialize(["1"])

    with RunLock(store):
        with pytest.raises(RunAlreadyActive):
            with RunLock(store):
                pass


def test_run_lock_reclaims_dead_pid(tmp_path):
    store = RunStateStore(tmp_path, RunIdentity(job_id="evening", cutoff=cutoff()))
    store.initialize(["1"])
    store.lock_path.write_text('{"pid": 99999999}')

    with RunLock(store):
        assert json.loads(store.lock_path.read_text())["pid"] == os.getpid()

    assert not store.lock_path.exists()
