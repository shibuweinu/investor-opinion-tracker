---
name: investor-opinion-tracker
description: 抓取已获授权的雪球博主时间线，跟踪观点变化，结合行情生成风险约束的日报或周报；支持 CLI 和 MCP，可用于 Codex、Claude/OpenClaw、WorkBuddy。
---

# Investor Opinion Tracker

仅在用户声明已获得内容访问授权，并由用户或宿主 Agent 提供已登录浏览器会话时运行。默认雪球 QPS=1，不读取、输出或持久化 Cookie、Token、密码和验证码。

## 工作流

1. Agent 安装时运行 `opinion-tracker init --no-interactive`。新工作区不得复用历史对话中的博主或示例 URL，也不得把“继续”或安装许可当成任务确认。
2. 逐项询问博主主页、回溯天数（默认 5）、报告类型（日/周）和交易者画像。用户暂不填写画像时，明确告知混合模式、平衡偏好、单笔计划亏损 0.5% 的默认值并取得接受。
3. 运行 `onboard` 保存草稿，再运行 `task-summary` 把完整摘要展示给用户。确认前不得抓取；只有用户明确确认当前摘要后才能运行 `task-confirm`。
4. 运行 `run`。它先验证确认指纹，再通过已登录的外置 Chrome 抓取并生成 `posts.json`、`evidence-pack.json` 和 `ANALYZE.md`。固定帖不决定分页停止；必须用最后一条非置顶普通帖判断边界并按帖子 ID 去重。
5. Agent 必须继续读取 `ANALYZE.md` 和证据包完成语义分析，按博主总结并比较一致与分歧，再写最终 `report.md`。程序初筛不是最终报告；昵称或行业映射必须标记“Agent 推导”。
6. 保留原文链接和时间，区分本人观点、引用、转发、玩笑、事实转述与持仓披露。含糊内容不得作为正式观点或业绩统计依据。
7. 显式股票代码优先；行业映射必须注明推导。A股行情使用内置 `TdxClient`，无需安装 `tdx-api` Skill；AKShare 用于 ETF、港股及回退。证据按 A/B/C/D 分级。
8. 仓位建议默认关闭。只有任务明确开启且账户规模、入场价、止损条件齐全时才计算；数据不完整时只给观察项。
9. 报告完成后提示用户可以启动定时任务，但不得未经另一次确认自行创建。

## 调用方式

- CLI：见 `references/cli.md`
- MCP / WorkBuddy：见 `references/workbuddy.md`
- 输入输出契约：见 `references/contracts.md`
- 浏览器适配：见 `references/browser-adapter.md`
- 日报/周报触发：见 `references/scheduling.md`
- 行情源顺序：见 `references/market-data.md`

输出必须注明：证据等级、数据完整性、失效条件、风险预算以及“研究辅助而非投资建议”。
