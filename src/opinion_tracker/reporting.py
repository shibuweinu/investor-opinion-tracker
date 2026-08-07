from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .schemas import RunResult, TraderProfile


def render_markdown(result: RunResult, profile: TraderProfile, generated_at: datetime) -> str:
    completeness = "完整" if result.status == "complete" else "不完整（仅供观察，不给出主动仓位）"
    candidate_cards = []
    for item in result.candidates:
        state = item.state if result.status == "complete" else "watch"
        if state == "avoid" or len(candidate_cards) >= 5:
            continue
        state_label = {"active": "候选", "watch": "观察"}[state]
        rationale = "、".join(item.rationale[:2]) or "证据不足"
        candidate_cards.append(
            f"- **[{state_label}] {item.symbol or item.topic}**：评分 {item.score:.1f}，"
            f"证据 {item.evidence_level}；{rationale}。"
        )
    candidate_text = "\n".join(candidate_cards) or "- **暂无已验证候选。**"
    verification = result.verification
    snapshot_rows = (
        "\n".join(
            f"| {item.symbol} | {item.price:.3f} | {item.change_pct:+.2f}% | "
            f"{item.volume_hands} | "
            f"{item.market_time.isoformat() if item.market_time else '-'} | {item.source} |"
            for item in verification.market_snapshots
        )
        or "| 暂无 | - | - | - | - | - |"
    )
    errors = "；".join(verification.errors) or "无"
    opinions_by_id = {item.opinion_id: item for item in result.opinions}
    excluded_rows = []
    for opinion_id in verification.excluded_opinion_ids:
        opinion = opinions_by_id.get(opinion_id)
        source = f"（[{opinion.topic}]({opinion.source_url})）" if opinion else ""
        reason = verification.exclusion_reasons.get(opinion_id, "未通过核验")
        excluded_rows.append(f"- `{opinion_id}`{source}：{reason}")
    excluded_text = "\n".join(excluded_rows) or "- 无"
    report_level = "全部验证" if verification.ready_for_final else "部分验证（失败内容已隔离）"
    active_count = sum(item.state == "active" for item in result.candidates)
    watch_count = sum(item.state == "watch" for item in result.candidates)
    decision = f"存在 {active_count} 项候选，按触发条件观察" if active_count else "暂不新增交易候选"
    return f"""# 投资者观点跟踪报告

## 今日交易结论

- **{decision}**
- 已验证候选：{active_count} 项
- 低置信度观察：{watch_count} 项
- 排除内容：{len(verification.excluded_opinion_ids)} 条，不参与共识或候选
- 报告级别：{report_level}

## 候选与观察看板

{candidate_text}

## 观点变化

暂无经过门禁核验的结构化变化记录；不得根据帖子数量推导方向变化。

## 主题共识与分歧

本节仅保留经过语义归因的内容；未映射主题不得强行映射板块或标的。

## 行情与催化验证

| 标的 | 价格 | 涨跌幅 | 成交量（手） | 行情时间 | 来源 |
|---|---:|---:|---:|---|---|
{snapshot_rows}

## 风险提示

本报告是研究辅助，不构成投资建议。仓位必须由账户规模、入场价和止损价共同决定；数据不完整时不得输出主动仓位倾向。

## 数据质量

- 生成时间：{generated_at.isoformat()}
- 数据状态：{completeness}
- 交易风格：{profile.style} / {profile.aggressiveness}
- 单笔计划亏损上限：{profile.max_loss_per_trade_pct}%
- 共抓取：{result.posts_collected} 条
- 纳入分析：{len(verification.included_opinion_ids)} 条
- 行情核验：{verification.market_status}
- 语义归类：{verification.semantic_status}
- 独立事实核验：{verification.fact_status}
- 核验错误：{errors}

## 排除内容附录

以下内容不参与观点共识、候选评分或标的结论：

{excluded_text}
"""


def write_artifacts(directory: Path, result: RunResult, profile: TraderProfile) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    now = datetime.now().astimezone()
    final_ready = result.status == "complete" and result.verification.ready_for_delivery
    markdown_name = "report.md" if final_ready else "UNVERIFIED.md"
    paths = {"markdown": directory / markdown_name, "json": directory / "report.json"}
    paths["markdown"].write_text(render_markdown(result, profile, now), encoding="utf-8")
    paths["json"].write_text(
        json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return paths
