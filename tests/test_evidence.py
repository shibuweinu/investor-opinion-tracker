from datetime import UTC, datetime

from opinion_tracker.evidence import build_evidence_pack, classify_post
from opinion_tracker.schemas import NormalizedPost


def post(identity, author, text):
    return NormalizedPost(
        platform="xueqiu",
        platform_post_id=identity,
        author_id=author,
        published_at=datetime.now(UTC),
        text=text,
        url=f"https://xueqiu.com/{author}/{identity}",
    )


def test_classifier_excludes_empty_forward_and_question():
    assert not classify_post(post("1", "a", "")).formal
    assert classify_post(post("2", "a", "转发")).kind == "forward"
    assert not classify_post(post("3", "a", "兄弟们，明天怎么说？")).formal


def test_pack_groups_authors_reduces_evidence_and_preserves_sources():
    posts = [
        post("1", "a", "看好创新药，行业已经筑底"),
        post("2", "a", "兄弟们，明天怎么说？"),
        post("3", "b", "今天又买了一些 $恒瑞医药(SH600276)$"),
        post("4", "b", "转发"),
    ]
    pack = build_evidence_pack(posts, complete=True, include_position_sizing=False)
    assert pack.total_posts == 4
    assert pack.author_counts == {"a": 2, "b": 2}
    assert len(pack.evidence) == 2
    assert {item.post_id for item in pack.evidence} == {"1", "3"}
    assert all(item.source_url for item in pack.evidence)
    assert pack.include_position_sizing is False
