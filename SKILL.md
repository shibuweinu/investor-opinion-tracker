---
name: investor-opinion-tracker
description: 抓取已获授权的雪球博主时间线，跟踪观点变化，结合行情生成风险约束的日报或周报；支持 CLI 和 MCP，可用于 Codex、Claude/OpenClaw、WorkBuddy。
---

# Investor Opinion Tracker

仅在用户声明已获得内容访问授权，并由用户或宿主 Agent 提供已登录浏览器会话时运行。默认雪球 QPS=1，不读取、输出或持久化 Cookie、Token、密码和验证码。

## 工作流

1. 首次运行检查 `.investor-opinion-tracker/config.json`。没有交易者画像时，询问交易周期、激进度、账户风险预算；用户暂不回答则使用混合模式、平衡偏好、单笔计划亏损 0.5% 的安全默认值。
2. 接收博主主页、回溯天数（默认 5）、报告类型（日/周）与授权声明。运行 `opinion-tracker doctor`。
3. 通过宿主 Agent 的已登录浏览器实现 `BrowserPort.fetch_timeline`，调用 `XueqiuCollector`。固定帖不决定分页停止；遵守 QPS 和时间边界。
4. 保留原文链接和时间，区分本人观点、引用、转发、玩笑、事实转述与持仓披露。含糊内容不得作为正式观点或业绩统计依据。
5. 显式股票代码优先；行业映射必须注明推导。证据按 A（公告/交易所）、B（权威行情/公司资料）、C（可信媒体/研报）、D（未经核验）分级。
6. 完整数据可输出 active/watch/avoid 与仓位倾向；数据不完整时明确标记“不完整”，只给观察项，不给主动仓位建议。所有仓位以计划亏损、止损距离和行业上限计算。
7. 报告完成后提示用户可以启动定时任务，但不得未经确认自行创建。日报建议交易日 18:30，周报建议周六 10:00，时区 Asia/Shanghai。

## 调用方式

- CLI：见 `references/cli.md`
- MCP / WorkBuddy：见 `references/workbuddy.md`
- 输入输出契约：见 `references/contracts.md`
- 浏览器适配：见 `references/browser-adapter.md`
- 日报/周报触发：见 `references/scheduling.md`

输出必须注明：证据等级、数据完整性、失效条件、风险预算以及“研究辅助而非投资建议”。
