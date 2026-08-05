from typing import Literal

from .schemas import Opinion, TradeCandidate


def score_candidate(
    opinion: Opinion,
    momentum: float,
    liquidity: float,
    evidence_level: Literal["A", "B", "C", "D"],
    data_complete: bool = True,
) -> TradeCandidate:
    evidence = {"A": 25, "B": 18, "C": 10, "D": 0}[evidence_level]
    score = min(100.0, round(opinion.confidence * 35 + momentum * 25 + liquidity * 15 + evidence, 1))
    state: Literal["active", "watch", "avoid"] = (
        "active" if score >= 70 and data_complete and opinion.formal else "watch" if score >= 50 else "avoid"
    )
    return TradeCandidate(
        symbol=opinion.symbol,
        topic=opinion.topic,
        score=score,
        state=state,
        evidence_level=evidence_level,
        rationale=["博主观点", "市场动量", "流动性", "证据等级"],
        data_complete=data_complete,
    )
