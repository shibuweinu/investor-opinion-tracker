from datetime import UTC, datetime

from opinion_tracker.reporting import render_markdown
from opinion_tracker.schemas import RunResult, TradeCandidate, TraderProfile, VerificationSummary


def test_report_is_mobile_first_and_moves_diagnostics_to_end():
    result = RunResult(
        status="complete",
        posts_collected=100,
        verification=VerificationSummary(
            market_status="not_required",
            semantic_status="partially_verified",
            fact_status="verified",
            excluded_opinion_ids=["op-1"],
            exclusion_reasons={"op-1": "缺少归因"},
        ),
    )

    report = render_markdown(result, TraderProfile(), datetime.now(UTC))

    headings = [
        "## 今日交易结论",
        "## 候选与观察看板",
        "## 观点变化",
        "## 主题共识与分歧",
        "## 行情与催化验证",
        "## 风险提示",
        "## 数据质量",
        "## 排除内容附录",
    ]
    assert all(
        report.index(current) < report.index(next_)
        for current, next_ in zip(headings, headings[1:], strict=False)
    )
    first_screen = report[: report.index("## 候选与观察看板")]
    assert "暂不新增交易候选" in first_screen
    assert "共抓取" not in first_screen
    assert "op-1" not in first_screen
    assert "op-1" in report[report.index("## 排除内容附录") :]


def test_report_hides_avoid_candidates_from_trade_dashboard():
    result = RunResult(
        status="complete",
        posts_collected=1,
        candidates=[
            TradeCandidate(
                symbol=None,
                topic="未映射主题",
                score=45,
                state="avoid",
                evidence_level="C",
                rationale=["证据不足"],
            ),
            TradeCandidate(
                symbol="SH601058",
                topic="赛轮轮胎",
                score=58,
                state="watch",
                evidence_level="C",
                rationale=["单一博主观点"],
            ),
        ],
        verification=VerificationSummary(
            market_status="not_required", semantic_status="verified", fact_status="verified"
        ),
    )

    report = render_markdown(result, TraderProfile(), datetime.now(UTC))
    dashboard = report[
        report.index("## 候选与观察看板") : report.index("## 观点变化")
    ]
    assert "SH601058" in dashboard
    assert "未映射主题" not in dashboard
