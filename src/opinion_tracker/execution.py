from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, cast

from .collectors.external_chrome import ExternalChromeXueqiuCollector
from .evidence import build_evidence_pack
from .run_state import RunLock, RunStateStore
from .schemas import CollectionResult, NormalizedPost, RunRequest, RunResult
from .task_state import TaskStore


class Collector(Protocol):
    def collect(self, request: RunRequest) -> CollectionResult: ...


def execute_confirmed(
    workspace: Path,
    output: Path,
    collector: Collector | None = None,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    complete_state: bool = True,
    run_store: RunStateStore | None = None,
) -> RunResult:
    store = TaskStore(workspace)
    record = store.require_confirmed()
    assert record.draft is not None
    draft = record.draft
    active_collector = collector or ExternalChromeXueqiuCollector()
    user_ids = [str(url).rstrip("/").split("/")[-1] for url in draft.user_urls]

    def collect_users() -> tuple[list[NormalizedPost], list[str], bool]:
        if run_store is not None:
            run_store.initialize(user_ids)
        collected_posts: list[NormalizedPost] = []
        collected_warnings: list[str] = []
        all_complete = True
        for user_url in draft.user_urls:
            url = str(user_url).rstrip("/")
            user_id = url.split("/")[-1]
            if run_store is not None and run_store.load_user(user_id).status == "complete":
                continue
            request = RunRequest(
                user_url=user_url,
                lookback_days=draft.user_lookback_days.get(url, draft.lookback_days),
                qps=draft.user_qps.get(url, draft.qps),
                authorization_confirmed=draft.authorization_confirmed,
                as_of=until,
                since=since,
            )
            resumable = cast(Any, getattr(active_collector, "collect_resumable", None))
            if run_store is not None and callable(resumable):
                collected = cast(
                    CollectionResult,
                    resumable(request, run_store, run_store.load_user(user_id)),
                )
            else:
                collected = active_collector.collect(request)
                if run_store is not None:
                    run_store.merge_posts(collected.posts)
                    user_state = run_store.load_user(user_id)
                    user_state.status = (
                        "complete" if collected.status == "complete" else "incomplete"
                    )
                    user_state.last_error = (
                        "；".join(collected.warnings) if collected.warnings else None
                    )
                    if collected.next_cursor and collected.next_cursor.isdigit():
                        user_state.next_page = int(collected.next_cursor)
                    run_store.save_user(user_state)
            collected_posts.extend(collected.posts)
            collected_warnings.extend(collected.warnings)
            all_complete = all_complete and collected.status == "complete"
            if any(
                "雪球访问验证" in warning or "雪球登录失效" in warning
                for warning in collected.warnings
            ):
                collected_warnings.append("已停止后续账号采集，避免扩大风控或重复触发验证")
                all_complete = False
                break
        if run_store is not None:
            collected_posts = run_store.posts()
            all_complete = all(
                run_store.load_user(user_id).status == "complete" for user_id in user_ids
            )
            run_state = run_store.load()
            run_state.status = "complete" if all_complete else "incomplete"
            run_state.warnings = collected_warnings
            run_store.save(run_state)
        filtered = [
            post
            for post in collected_posts
            if (since is None or post.published_at > since)
            and (until is None or post.published_at <= until)
        ]
        return filtered, collected_warnings, all_complete

    if run_store is not None:
        with RunLock(run_store):
            posts, warnings, complete = collect_users()
    else:
        posts, warnings, complete = collect_users()
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

报告采用移动端优先结构，正文控制在约 2-3 个手机屏幕，详细证据移至附录。章节顺序必须是：
“今日交易结论”→“候选与观察看板”→“本期观点变化”→“主题共识与分歧”→“行情与催化验证”
→“风险提示”→“数据质量”→“排除内容附录”。第一屏必须直接给出是否存在候选、高/中置信度
候选数、低置信度观察数、主要机会、主要风险和相对上一期变化。不要在第一屏放采集数量、门禁
代码或长风险声明。候选和观察严格分开；每项必须回答方向、为什么现在、行情确认、等待触发条件
和失效条件，最多两句，候选最多 5 项。无满足条件项目时直接写“暂无已验证候选”。

观点按主题汇总，不按博主逐人写流水账；只突出新增、强化、弱化、反转和分歧变化。必须区分本人
观点、回复、转发和上下文；结合 TDX/AKShare 行情注明时间和来源；给出行业、股票、催化、风险、
失效条件和原文证据链接。昵称或行业映射必须标记“Agent 推导”。证据不足的候选只能进入观察项。
昵称或行业映射必须标记“Agent 推导”。证据不足的候选只能进入观察项。
先生成 `claims.json`：每条正式观点必须归入主观或事实主张，重点标的写入 `symbols`；再通过
`analyze-file --workspace ... --claims ... --fact-evidence ...` 核验门禁。只有事实主张要求公司、
交易所、监管、政府或公告等独立证据。语义归因或事实核验失败的内容必须从观点共识、候选
评分和标的结论中排除；正文只汇总排除数量和原因类别，逐条详情放在末尾附录。完成隔离后可
生成部分验证的 `report.md`。行情核验
失败或抓取不完整时仍只能保留 `UNVERIFIED.md`，不得交付正式报告。

{position_rule}

本文件不是最终报告；在 Agent 完成语义分析前不得宣称分析完成。
""",
        encoding="utf-8",
    )
    if complete_state:
        store.complete()
    return result
