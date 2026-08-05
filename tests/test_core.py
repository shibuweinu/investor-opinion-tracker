from datetime import UTC, datetime

from opinion_tracker.collectors.base import PaginationState
from opinion_tracker.opinions import extract_opinions, transition
from opinion_tracker.risk import size_position
from opinion_tracker.schemas import NormalizedPost, Opinion, TraderProfile
from opinion_tracker.scoring import score_candidate
from opinion_tracker.storage import Repository


def post(text: str, post_id: str = "1") -> NormalizedPost:
    return NormalizedPost(
        platform="xueqiu",
        platform_post_id=post_id,
        author_id="2292705444",
        author_name="药神",
        published_at=datetime(2026, 8, 5, tzinfo=UTC),
        text=text,
        url=f"https://xueqiu.com/2292705444/{post_id}",
    )


def test_safe_profile_and_repository_idempotency(tmp_path):
    assert TraderProfile().max_loss_per_trade_pct == 0.5
    repo = Repository(tmp_path / "state.db")
    repo.upsert_posts([post("看好创新药 $恒瑞医药(SH600276)$"), post("看好创新药 $恒瑞医药(SH600276)$")])
    assert repo.count_posts() == 1


def test_pinned_old_post_does_not_stop_current_page():
    items = [
        {"published_at": "2026-07-01T00:00:00+00:00", "pinned": True},
        {"published_at": "2026-08-05T00:00:00+00:00", "pinned": False},
    ]
    assert PaginationState.should_continue(items, datetime(2026, 8, 1, tzinfo=UTC))


def test_extract_transition_score_and_risk():
    opinions = extract_opinions([post("继续看好创新药，增持 $恒瑞医药(SH600276)$")])
    assert opinions[0].symbol == "SH600276"
    assert opinions[0].stance == "bullish"
    previous = Opinion(**{**opinions[0].model_dump(), "stance": "bearish"})
    assert transition(previous, opinions[0]).change_type == "reversed"
    candidate = score_candidate(opinions[0], momentum=0.8, liquidity=0.9, evidence_level="A")
    assert candidate.score >= 70 and candidate.state == "active"
    sizing = size_position(100_000, 1.0, entry=100, stop=95, sector_used_pct=0)
    assert sizing.shares == 200 and sizing.position_value == 20_000
