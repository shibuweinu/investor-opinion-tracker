from datetime import UTC, datetime

from opinion_tracker.market import TdxQuote
from opinion_tracker.schemas import FactEvidence, Opinion
from opinion_tracker.verification import verify_research


def opinion() -> Opinion:
    return Opinion(
        opinion_id="op-1",
        post_id="post-1",
        symbol="SH600276",
        topic="SH600276",
        stance="bullish",
        confidence=0.8,
        source_url="https://xueqiu.com/u/1",
        published_at=datetime.now(UTC),
        formal=True,
    )


class FakeQuotes:
    def quotes(self, codes):
        assert codes == ["600276"]
        return [
            TdxQuote(
                code="600276",
                price=50.0,
                previous_close=49.0,
                open=49.5,
                high=50.5,
                low=49.0,
                volume_hands=100,
                amount=5000,
            )
        ]


def test_verification_requires_independent_evidence_for_every_formal_opinion():
    result = verify_research([opinion()], [], FakeQuotes())
    assert result.market_status == "verified"
    assert result.fact_status == "unverified"
    assert result.uncovered_opinion_ids == ["op-1"]
    assert not result.ready_for_final


def test_verification_is_ready_only_when_market_and_facts_are_covered():
    evidence = FactEvidence(
        claim="公司公告支持该观点",
        opinion_ids=["op-1"],
        source_url="https://www.sse.com.cn/disclosure/example",
        source_type="exchange",
        verified_at=datetime.now(UTC),
    )
    result = verify_research([opinion()], [evidence], FakeQuotes())
    assert result.market_status == "verified"
    assert result.fact_status == "verified"
    assert result.ready_for_final
    assert result.market_snapshots[0].change_pct == 2.04
