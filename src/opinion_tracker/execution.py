from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from .collectors.external_chrome import ExternalChromeXueqiuCollector
from .evidence import build_evidence_pack
from .schemas import CollectionResult, RunRequest, RunResult
from .task_state import TaskStore


class Collector(Protocol):
    def collect(self, request: RunRequest) -> CollectionResult: ...


def execute_confirmed(
    workspace: Path, output: Path, collector: Collector | None = None
) -> RunResult:
    store = TaskStore(workspace)
    record = store.require_confirmed()
    assert record.draft is not None
    draft = record.draft
    active_collector = collector or ExternalChromeXueqiuCollector()
    posts, warnings = [], []
    complete = True
    for user_url in draft.user_urls:
        collected = active_collector.collect(
            RunRequest(
                user_url=user_url,
                lookback_days=draft.lookback_days,
                qps=draft.qps,
                authorization_confirmed=draft.authorization_confirmed,
            )
        )
        posts.extend(collected.posts)
        warnings.extend(collected.warnings)
        complete = complete and collected.status == "complete"
    result = RunResult(
        status="complete" if complete else "incomplete",
        posts_collected=len(posts),
        warnings=warnings,
    )
    output.mkdir(parents=True, exist_ok=True)
    (output / "posts.json").write_text(
        json.dumps([item.model_dump(mode="json") for item in posts], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    pack = build_evidence_pack(posts, complete, draft.include_position_sizing)
    (output / "evidence-pack.json").write_text(pack.model_dump_json(indent=2), encoding="utf-8")
    position_rule = (
        "仓位建议已开启；仅在账户规模、入场价和止损条件齐全时计算，否则只给公式。"
        if draft.include_position_sizing
        else "仓位建议未开启：不得输出仓位比例、金额或股数。"
    )
    (output / "ANALYZE.md").write_text(
        f"""# Agent 分析任务

读取同目录 `posts.json` 与 `evidence-pack.json`，完成语义分析后写入 `report.md`。

必须：按博主分别总结；区分本人观点、回复、转发和上下文；比较一致与分歧；
结合 TDX/AKShare 行情注明时间和来源；给出行业、股票、催化、风险、失效条件和原文证据链接。
昵称或行业映射必须标记“Agent 推导”。证据不足的候选只能进入观察项。

{position_rule}

本文件不是最终报告；在 Agent 完成语义分析前不得宣称分析完成。
""",
        encoding="utf-8",
    )
    store.complete()
    return result
