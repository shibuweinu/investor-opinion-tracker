from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from opinion_tracker.market import TdxDailyBar, TdxQuote
from opinion_tracker.schemas import FactEvidence, NormalizedPost, Opinion, ResearchClaim
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


def test_verification_requires_semantic_classification_for_every_formal_opinion():
    result = verify_research([opinion()], [], [], FakeQuotes())
    assert result.market_status == "verified"
    assert result.semantic_status == "unverified"
    assert result.uncovered_opinion_ids == ["op-1"]
    assert not result.ready_for_final


def test_subjective_claim_does_not_require_independent_fact_evidence():
    claim = ResearchClaim(
        claim_id="claim-1",
        text="作者主观看好公司",
        kind="subjective",
        opinion_ids=["op-1"],
        symbols=["SH600276"],
    )
    result = verify_research([opinion()], [claim], [], FakeQuotes())
    assert result.semantic_status == "verified"
    assert result.fact_status == "verified"
    assert result.ready_for_final


def test_factual_claim_requires_independent_evidence():
    claim = ResearchClaim(
        claim_id="claim-1",
        text="公司公告确认订单增长",
        kind="factual",
        opinion_ids=["op-1"],
        symbols=["SH600276"],
    )
    uncovered = verify_research([opinion()], [claim], [], FakeQuotes())
    assert uncovered.fact_status == "unverified"
    assert uncovered.uncovered_claim_ids == ["claim-1"]
    evidence = FactEvidence(
        claim_ids=["claim-1"],
        source_url="https://www.sse.com.cn/disclosure/example",
        source_type="exchange",
        verified_at=datetime.now(UTC),
    )
    result = verify_research([opinion()], [claim], [evidence], FakeQuotes())
    assert result.market_status == "verified"
    assert result.semantic_status == "verified"
    assert result.fact_status == "verified"
    assert result.ready_for_final
    assert result.market_snapshots[0].change_pct == 2.04


def test_market_verification_includes_nonformal_opinions_and_claim_symbols():
    nonformal = opinion().model_copy(update={"formal": False, "symbol": "SH600276"})
    claim = ResearchClaim(
        claim_id="claim-1",
        text="行业观点",
        kind="subjective",
        opinion_ids=["op-1"],
        symbols=["SH600276"],
    )
    result = verify_research([nonformal], [claim], [], FakeQuotes())
    assert result.market_status == "verified"
    assert result.market_snapshots[0].symbol == "SH600276"


class FakeMultiQuotes:
    def quotes(self, codes):
        assert codes == ["600276", "600519"]
        return [
            TdxQuote(
                code=code,
                price=50,
                previous_close=49,
                open=49,
                high=50,
                low=49,
                volume_hands=100,
                amount=5000,
            )
            for code in codes
        ]


def test_market_verification_scans_every_explicit_symbol_in_post_text():
    post = NormalizedPost(
        platform="xueqiu",
        platform_post_id="post-1",
        author_id="u",
        published_at=datetime.now(UTC),
        text="比较 SH600276 和 SH600519",
        url="https://xueqiu.com/u/post-1",
    )
    claim = ResearchClaim(
        claim_id="claim-1",
        text="比较两只股票",
        kind="subjective",
        opinion_ids=["op-1"],
        symbols=[],
    )
    result = verify_research([opinion()], [claim], [], FakeMultiQuotes(), posts=[post])
    assert [item.symbol for item in result.market_snapshots] == ["SH600276", "SH600519"]


class FakeHistoricalQuotes:
    def quotes(self, codes):
        raise AssertionError("有报告截止时间时不得读取实时行情")

    def daily_closes(self, codes, as_of):
        assert codes == ["600276"]
        assert as_of == datetime(2026, 8, 7, 9, tzinfo=ZoneInfo("Asia/Shanghai"))
        return [
            TdxDailyBar(
                code="600276",
                time=datetime(2026, 8, 6, 15, tzinfo=ZoneInfo("Asia/Shanghai")),
                close=52.11,
                previous_close=53.54,
                open=53.65,
                high=53.81,
                low=52.0,
                volume_hands=898631,
                amount=0,
            )
        ]


def test_market_as_of_uses_last_completed_daily_close():
    claim = ResearchClaim(
        claim_id="claim-1",
        text="作者主观看好公司",
        kind="subjective",
        opinion_ids=["op-1"],
        symbols=["SH600276"],
    )
    cutoff = datetime(2026, 8, 7, 9, tzinfo=ZoneInfo("Asia/Shanghai"))

    result = verify_research(
        [opinion()], [claim], [], FakeHistoricalQuotes(), market_as_of=cutoff
    )

    snapshot = result.market_snapshots[0]
    assert result.market_status == "verified"
    assert snapshot.price == 52.11
    assert snapshot.change_pct == -2.67
    assert snapshot.volume_hands == 898631
    assert snapshot.market_time == datetime(
        2026, 8, 6, 15, tzinfo=ZoneInfo("Asia/Shanghai")
    )
    assert snapshot.source == "TDX daily"
