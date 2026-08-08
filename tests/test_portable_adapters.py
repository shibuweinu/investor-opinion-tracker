import json
from datetime import UTC, datetime, timedelta

import pytest

from opinion_tracker.collectors.external_chrome import (
    ExternalChromeXueqiuCollector,
    RetryPolicy,
    retry_delay,
)
from opinion_tracker.market.tdx import TdxClient
from opinion_tracker.run_state import RunIdentity, RunStateStore, UserPageState
from opinion_tracker.schemas import NormalizedPost, RunRequest


@pytest.mark.parametrize(
    ("attempt", "expected"),
    [(0, 5), (1, 10), (2, 20), (3, 40), (4, 60), (5, 120), (8, 120)],
)
def test_retry_policy_uses_bounded_exponential_backoff(attempt, expected):
    assert retry_delay(attempt, retry_after=None, remaining=600) == expected


def test_retry_policy_prefers_retry_after_but_never_exceeds_remaining_budget():
    assert retry_delay(0, retry_after=30, remaining=40) == 30
    assert retry_delay(0, retry_after=90, remaining=40) is None


def test_resumable_collector_retries_same_page_and_persists_next_page(tmp_path):
    as_of = datetime(2026, 8, 7, 13, tzinfo=UTC)
    recent = int((as_of - timedelta(hours=1)).timestamp() * 1000)
    old = int((as_of - timedelta(days=6)).timestamp() * 1000)
    responses = iter(
        [
            {"__http_status": 405, "__tracker_error": "invalid_response"},
            {"__http_status": 200, "statuses": [{"id": "1", "created_at": recent}]},
            {"__http_status": 200, "statuses": [{"id": "2", "created_at": old}]},
        ]
    )
    requested_pages = []

    def runner(args):
        if args[0] == "open":
            return ""
        requested_pages.append(1 if "page=1&" in args[1] else 2)
        return json.dumps(next(responses))

    store = RunStateStore(tmp_path, RunIdentity(job_id="evening", cutoff=as_of))
    store.initialize(["1"])
    collector = ExternalChromeXueqiuCollector(
        runner=runner, sleeper=lambda _: None, jitter=lambda: 0
    )

    result = collector.collect_resumable(
        RunRequest(user_url="https://xueqiu.com/u/1", lookback_days=5, qps=1, as_of=as_of),
        store,
        store.load_user("1"),
    )

    assert result.status == "complete"
    assert store.load_user("1").next_page == 3
    assert requested_pages == [1, 1, 2]


def test_resumable_collector_restarts_at_saved_page_without_duplicate_requests(tmp_path):
    as_of = datetime(2026, 8, 7, 13, tzinfo=UTC)
    recent = int((as_of - timedelta(hours=1)).timestamp() * 1000)
    old = int((as_of - timedelta(days=6)).timestamp() * 1000)
    requested_pages = []

    def runner(args):
        if args[0] == "open":
            return ""
        requested_pages.append(4 if "page=4&" in args[1] else -1)
        return json.dumps(
            {
                "__http_status": 200,
                "statuses": [
                    {"id": "new", "created_at": recent},
                    {"id": "old", "created_at": old},
                ],
            }
        )

    store = RunStateStore(tmp_path, RunIdentity(job_id="evening", cutoff=as_of))
    store.initialize(["1"])
    store.save_user(UserPageState(user_id="1", next_page=4, status="incomplete"))
    store.merge_posts(
        [
            NormalizedPost(
                platform="xueqiu",
                platform_post_id="saved",
                author_id="1",
                published_at=as_of - timedelta(hours=2),
                text="saved",
                url="https://xueqiu.com/1/saved",
            )
        ]
    )

    result = ExternalChromeXueqiuCollector(
        runner=runner, sleeper=lambda _: None, jitter=lambda: 0
    ).collect_resumable(
        RunRequest(user_url="https://xueqiu.com/u/1", lookback_days=5, qps=1, as_of=as_of),
        store,
        store.load_user("1"),
    )

    assert requested_pages == [4]
    assert [post.platform_post_id for post in result.posts] == ["saved", "new"]


def test_resumable_slider_stops_without_retry_and_keeps_cursor(tmp_path):
    calls = 0
    sleeps = []

    def runner(args):
        nonlocal calls
        if args[0] == "open":
            return ""
        calls += 1
        return json.dumps({"__tracker_error": "risk_verification", "__http_status": 403})

    cutoff = datetime.now(UTC)
    identity = RunIdentity(job_id="evening", cutoff=cutoff)
    store = RunStateStore(tmp_path, identity)
    store.initialize(["1"])
    result = ExternalChromeXueqiuCollector(
        runner=runner, sleeper=sleeps.append, jitter=lambda: 0
    ).collect_resumable(
        RunRequest(user_url="https://xueqiu.com/u/1", as_of=cutoff),
        store,
        store.load_user("1"),
    )

    assert result.status == "failed"
    assert store.load_user("1").next_page == 1
    assert sleeps == []
    assert calls == 1


def test_resumable_page_budget_stops_endless_pagination(tmp_path):
    as_of = datetime.now(UTC)
    created_at = int((as_of - timedelta(minutes=1)).timestamp() * 1000)
    calls = 0

    def runner(args):
        nonlocal calls
        if args[0] == "open":
            return ""
        calls += 1
        return json.dumps(
            {"__http_status": 200, "statuses": [{"id": str(calls), "created_at": created_at}]}
        )

    store = RunStateStore(tmp_path, RunIdentity(job_id="evening", cutoff=as_of))
    store.initialize(["1"])
    result = ExternalChromeXueqiuCollector(
        runner=runner, sleeper=lambda _: None, jitter=lambda: 0
    ).collect_resumable(
        RunRequest(user_url="https://xueqiu.com/u/1", as_of=as_of),
        store,
        store.load_user("1"),
        policy=RetryPolicy(max_pages=2),
    )

    assert result.status == "incomplete"
    assert "2" in result.warnings[0]
    assert calls == 2


def test_resumable_retry_after_controls_transient_retry_delay(tmp_path):
    as_of = datetime.now(UTC)
    responses = iter(
        [
            {"__http_status": 429, "__tracker_error": "invalid_response", "__retry_after": "30"},
            {"__http_status": 200, "statuses": []},
        ]
    )
    sleeps = []

    def runner(args):
        return "" if args[0] == "open" else json.dumps(next(responses))

    store = RunStateStore(tmp_path, RunIdentity(job_id="evening", cutoff=as_of))
    store.initialize(["1"])
    result = ExternalChromeXueqiuCollector(
        runner=runner, sleeper=sleeps.append, jitter=lambda: 0
    ).collect_resumable(
        RunRequest(user_url="https://xueqiu.com/u/1", as_of=as_of),
        store,
        store.load_user("1"),
    )

    assert result.status == "complete"
    assert sleeps == [30, 1]


def test_external_chrome_ignores_old_pinned_and_deduplicates():
    pages = {
        1: {
            "statuses": [
                {"id": "p", "created_at": 1, "pinned": True, "description": "old"},
                {"id": "1", "created_at": 1785945600000, "description": "看好创新药"},
            ]
        },
        2: {
            "statuses": [
                {"id": "1", "created_at": 1785945600000, "description": "看好创新药"},
                {"id": "2", "created_at": 1, "description": "old boundary"},
            ]
        },
    }

    def runner(args):
        if args[0] == "open":
            return ""
        page = 1 if "page=1&" in args[1] else 2
        return json.dumps(pages[page])

    result = ExternalChromeXueqiuCollector(runner=runner, sleeper=lambda _: None).collect(
        RunRequest(user_url="https://xueqiu.com/u/2292705444", lookback_days=5, qps=1)
    )
    assert result.status == "complete"
    assert [post.platform_post_id for post in result.posts] == ["1"]


def test_external_chrome_uses_incremental_since_as_cutoff():
    as_of = datetime(2026, 8, 7, 1, tzinfo=UTC)
    recent = int((as_of - timedelta(hours=2)).timestamp() * 1000)
    before_checkpoint = int((as_of - timedelta(days=2)).timestamp() * 1000)
    requested_pages: list[int] = []

    def runner(args):
        if args[0] == "open":
            return ""
        page = 1 if "page=1&" in args[1] else 2
        requested_pages.append(page)
        return json.dumps(
            {
                "statuses": [
                    {"id": "recent", "created_at": recent, "description": "new"},
                    {"id": "old", "created_at": before_checkpoint, "description": "old"},
                ]
            }
        )

    result = ExternalChromeXueqiuCollector(
        runner=runner, sleeper=lambda _: None, jitter=lambda: 0
    ).collect(
        RunRequest(
            user_url="https://xueqiu.com/u/1",
            lookback_days=5,
            qps=1,
            as_of=as_of,
            since=as_of - timedelta(hours=12),
        )
    )

    assert result.status == "complete"
    assert [post.platform_post_id for post in result.posts] == ["recent"]
    assert requested_pages == [1]


def test_external_chrome_classifies_slider_and_stops_without_retrying():
    calls = 0

    def runner(args):
        nonlocal calls
        if args[0] == "open":
            return ""
        calls += 1
        return json.dumps({"__tracker_error": "risk_verification", "__http_status": 403})

    result = ExternalChromeXueqiuCollector(
        runner=runner, sleeper=lambda _: None, jitter=lambda: 0
    ).collect(RunRequest(user_url="https://xueqiu.com/u/1", lookback_days=5, qps=1))

    assert result.status == "failed"
    assert result.next_cursor == "1"
    assert result.warnings == ["雪球访问验证：需要人工完成滑块，已停止采集"]
    assert calls == 1


def test_external_chrome_paces_across_users():
    sleeps: list[float] = []

    def runner(args):
        if args[0] == "open":
            return ""
        return json.dumps({"statuses": []})

    collector = ExternalChromeXueqiuCollector(
        runner=runner, sleeper=sleeps.append, jitter=lambda: 0.5
    )
    collector.collect(RunRequest(user_url="https://xueqiu.com/u/1", qps=1))
    collector.collect(RunRequest(user_url="https://xueqiu.com/u/2", qps=1))

    assert sleeps == [1.5]


def test_tdx_client_converts_li_to_yuan():
    payload = {
        "code": 0,
        "message": "success",
        "data": [{"Code": "688235", "K": {"Last": 261960, "Close": 280600}}],
    }
    client = TdxClient(transport=lambda url, headers, timeout: payload)
    quote = client.quotes(["688235"])[0]
    assert quote.previous_close == 261.96
    assert quote.price == 280.6


def test_tdx_client_selects_daily_close_before_cutoff():
    payload = {
        "code": 0,
        "message": "success",
        "data": {
            "Count": 2,
            "List": [
                {
                    "Last": 53540,
                    "Open": 53650,
                    "High": 53810,
                    "Low": 52000,
                    "Close": 52110,
                    "Volume": 898631,
                    "Amount": 0,
                    "Time": "2026-08-06T15:00:00+08:00",
                },
                {
                    "Last": 52110,
                    "Open": 52200,
                    "High": 53000,
                    "Low": 51800,
                    "Close": 52800,
                    "Volume": 700000,
                    "Amount": 0,
                    "Time": "2026-08-07T15:00:00+08:00",
                },
            ],
        },
    }
    client = TdxClient(transport=lambda url, headers, timeout: payload)
    cutoff = datetime.fromisoformat("2026-08-07T09:00:00+08:00")

    bar = client.daily_closes(["600276"], cutoff)[0]

    assert bar.time == datetime.fromisoformat("2026-08-06T15:00:00+08:00")
    assert bar.close == 52.11
    assert bar.previous_close == 53.54
    assert bar.volume_hands == 898631
