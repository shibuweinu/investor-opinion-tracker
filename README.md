# Investor Opinion Tracker

一个可移植的 Agent Skill + Python CLI + MCP 服务，用于在用户已获授权并提供已登录会话的前提下，抓取雪球博主时间线、跟踪观点变化，并生成有证据等级和风险预算约束的交易研究日报/周报。

## 可移植性

仓库不依赖 Codex 私有路径或特定浏览器。任何 Agent 都可采用两段式工作流：

1. 默认使用用户已登录的外置 Chrome/CDP，按 [浏览器适配契约](references/browser-adapter.md) 抓取并标准化帖子；仅在外置浏览器不可用时回退到内置浏览器；
2. 调用统一 CLI `analyze-file`，或通过 Python/MCP 使用相同核心模型生成报告。

已提供 Codex Agent Skill、通用 CLI、MCP stdio 服务，以及 Claude/OpenClaw/腾讯 WorkBuddy 的配置说明。

## 五分钟安装

需要 Python 3.11+：

```bash
git clone git@github.com:shibuweinu/investor-opinion-tracker.git
cd investor-opinion-tracker
python3.11 -m venv .venv
.venv/bin/pip install '.[mcp]'
.venv/bin/opinion-tracker doctor
.venv/bin/opinion-tracker init --workspace ./data
```

`init` 会在 `./data/.investor-opinion-tracker/WELCOME.md` 生成初始化 landing，说明第一次任务、默认交易者画像、外置 Chrome、内置 TDX 行情、日报/周报和定时任务。随时运行 `opinion-tracker welcome --workspace ./data` 可重新查看。

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

## 数据源优先级

- 雪球：外置 Chrome/CDP + `agent-browser`，最后一条非置顶普通帖决定分页边界；
- A股行情：使用仓库内置 `TdxClient` 调用 TDX API，不需要用户安装 `tdx-api` Skill；
- ETF、基金和港股：使用 AKShare；
- 单一数据源超时后立即降级，禁止无限等待。

具体接口与单位换算见 [行情源顺序](references/market-data.md)。

## 开发与自检

```bash
.venv/bin/pip install '.[dev,mcp]'
.venv/bin/pytest --cov=opinion_tracker
.venv/bin/ruff check .
.venv/bin/mypy src/opinion_tracker
```

更多内容见 [CLI](references/cli.md)、[输入输出契约](references/contracts.md) 和 [WorkBuddy/MCP](references/workbuddy.md)。

本项目只提供研究辅助，不构成投资建议。
