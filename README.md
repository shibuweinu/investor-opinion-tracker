# Investor Opinion Tracker

一个可移植的 Agent Skill + Python CLI + MCP 服务，用于在用户已获授权并提供已登录会话的前提下，抓取雪球博主时间线、跟踪观点变化，并生成有证据等级和风险预算约束的交易研究日报/周报。

## 可移植性

仓库不依赖 Codex 私有路径或特定浏览器。任何 Agent 都可采用两段式工作流：

1. 使用自身已登录浏览器，按 [浏览器适配契约](references/browser-adapter.md) 抓取并标准化帖子；
2. 调用统一 CLI `analyze-file`，或通过 Python/MCP 使用相同核心模型生成报告。

已提供 Codex Agent Skill、通用 CLI、MCP stdio 服务，以及 Claude/OpenClaw/腾讯 WorkBuddy 的配置说明。

## 五分钟安装

需要 Python 3.11+：

```bash
git clone git@github.com:dingxiaolong0715/investor-opinion-tracker.git
cd investor-opinion-tracker
python3.11 -m venv .venv
.venv/bin/pip install '.[mcp]'
.venv/bin/opinion-tracker doctor
.venv/bin/opinion-tracker init --workspace ./data
```

让 Agent 读取仓库根目录 `SKILL.md`。完成授权抓取并生成标准化 JSON 后：

```bash
.venv/bin/opinion-tracker analyze-file --input examples/posts.json --output ./reports
```

输出 `report.md` 与 `report.json`。真实帖子、配置、数据库、Cookie 和报告均被 `.gitignore` 排除；切勿提交凭据。

## 默认行为

- 回溯 5 天、Asia/Shanghai、雪球 QPS=1；
- 未填写画像：混合交易风格，单笔计划亏损 0.5%；
- 数据不完整时只列观察项，不输出主动仓位；
- 首份报告后仅提示可启动定时任务，未经确认不创建；
- 日报建议交易日 18:30，周报建议周六 10:00。

## 开发与自检

```bash
.venv/bin/pip install '.[dev,mcp]'
.venv/bin/pytest --cov=opinion_tracker
.venv/bin/ruff check .
.venv/bin/mypy src/opinion_tracker
```

更多内容见 [CLI](references/cli.md)、[输入输出契约](references/contracts.md) 和 [WorkBuddy/MCP](references/workbuddy.md)。

本项目只提供研究辅助，不构成投资建议。
