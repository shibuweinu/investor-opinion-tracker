import json

from opinion_tracker.collectors.external_chrome import ExternalChromeXueqiuCollector
from opinion_tracker.market.tdx import TdxClient
from opinion_tracker.schemas import RunRequest


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
