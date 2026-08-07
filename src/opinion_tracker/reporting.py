from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .schemas import RunResult, TraderProfile


def render_markdown(result: RunResult, profile: TraderProfile, generated_at: datetime) -> str:
    completeness = "完整" if result.status == "complete" else "不完整（仅供观察，不给出主动仓位）"
    rows = []
    for item in result.candidates:
        state = item.state if result.status == "complete" else "watch"
        rows.append(f"| {item.symbol or item.topic} | {item.score:.1f} | {state} | {item.evidence_level} |")
    table = "\n".join(rows) or "| 暂无 | - | avoid | D |"
    verification = result.verification
    snapshot_rows = (
        "\n".join(
            f"| {item.symbol} | {item.price:.3f} | {item.change_pct:+.2f}% | "
            f"{item.volume_hands} | {item.source} |"
            for item in verification.market_snapshots
        )
        or "| 暂无 | - | - | - | - |"
    )
    errors = "；".join(verification.errors) or "无"
    return f"""# 投资者观点跟踪报告

- 生成时间：{generated_at.isoformat()}
- 数据状态：{completeness}
- 交易风格：{profile.style} / {profile.aggressiveness}
- 单笔计划亏损上限：{profile.max_loss_per_trade_pct}%
- 行情核验：{verification.market_status}
- 语义归类：{verification.semantic_status}
- 独立事实核验：{verification.fact_status}

## 观点摘要

共抓取 {result.posts_collected} 条，识别 {len(result.opinions)} 条观点。

## 交易候选

| 标的/主题 | 评分 | 状态 | 证据 |
|---|---:|---|---|
{table}

## 行情交叉验证

| 标的 | 最新价 | 当日涨跌 | 成交量（手） | 来源 |
|---|---:|---:|---:|---|
{snapshot_rows}

- 核验错误：{errors}

## 风险声明

本报告是研究辅助，不构成投资建议。仓位必须由账户规模、入场价和止损价共同决定；数据不完整时不得输出主动仓位倾向。
"""


def write_artifacts(directory: Path, result: RunResult, profile: TraderProfile) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    now = datetime.now().astimezone()
    final_ready = result.status == "complete" and result.verification.ready_for_final
    markdown_name = "report.md" if final_ready else "UNVERIFIED.md"
    paths = {"markdown": directory / markdown_name, "json": directory / "report.json"}
    paths["markdown"].write_text(render_markdown(result, profile, now), encoding="utf-8")
    paths["json"].write_text(
        json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return paths
