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
./scripts/bootstrap.sh
.venv/bin/opinion-tracker init --workspace ./data --no-interactive
```

`bootstrap.sh` 会先升级虚拟环境内的 pip/setuptools，兼容 macOS 自带的旧 pip；不会修改系统 Python。也可以设置 `PYTHON_BIN` 指定 Python 3.11+。

`init --no-interactive` 会生成初始化 landing，但不会等待输入、创建默认博主或开始抓取。Agent 接下来询问用户需求，调用 `onboard` 保存草稿，以 `task-summary` 展示完整摘要；只有用户明确确认后才调用 `task-confirm` 和 `run`。示例 URL 永远不是默认目标。

新设备会提示 `restore`（恢复已有私有配置仓库）、`create`（创建个人私有配置仓库）或 `skip`（仅本地使用）。它不会静默拉取配置。也可传入 `init --config-repo <git-url>` 只连接并预览，确认后再执行 `config-pull`。绑定命令为 `config-connect`；完整流程见 [个人配置同步](docs/config-sync.md)。远端 `trusted_auto_apply` 只有在每台设备单独授权后才生效。

```bash
.venv/bin/opinion-tracker onboard --workspace ./data --user-url https://xueqiu.com/u/USER_ID --lookback-days 5 --report-type daily --accept-default-profile
.venv/bin/opinion-tracker task-summary --workspace ./data
# 用户明确确认当前摘要后：
.venv/bin/opinion-tracker task-confirm --workspace ./data
.venv/bin/opinion-tracker run --workspace ./data --output ./reports
```

跟踪多位博主时可重复传入 `--user-url`；每位博主分别抓取，报告统一汇总。
`run` 生成 `posts.json`、`evidence-pack.json` 和 `ANALYZE.md`；宿主 Agent 必须继续完成语义分析后才能交付 `report.md`。仓位建议默认关闭，只有显式传入 `--include-position-sizing` 才开启后续询问。

随时运行 `opinion-tracker welcome --workspace ./data` 可重新查看 landing。确认前不得抓取；更改目标、回溯、报告类型或画像后必须重新确认。

让 Agent 读取仓库根目录 `SKILL.md`。对于已有标准化 JSON，也可单独分析：

```bash
.venv/bin/opinion-tracker analyze-file --input examples/posts.json --output ./reports
```

核验采用逐项隔离：缺少语义归因或独立事实证据的内容会从共识、候选评分和标的结论中排除，
并记录在报告的“排除内容”章节。其余内容完成行情核验后仍可生成部分验证报告；行情失败或
采集不完整仍会生成 `UNVERIFIED.md`，禁止发送正式邮件。

报告采用移动端优先的信息层级：第一屏只放交易结论、候选数量、主要机会与风险；随后依次是
候选与观察、观点变化、主题共识、行情验证和风险提示。采集统计、核验细节与逐条排除记录放在
末尾，确保手机邮箱和电脑端阅读时都先看到交易相关信息。

输出 `report.md` 与 `report.json`。真实帖子、配置、数据库、Cookie 和报告均被 `.gitignore` 排除；切勿提交凭据。

## 默认行为

- 回溯 5 天、Asia/Shanghai、雪球 QPS=1；
- 未填写画像：混合交易风格，单笔计划亏损 0.5%；
- 数据不完整时只列观察项，不输出主动仓位；
- 首份报告后仅提示可启动定时任务，未经确认不创建；
- 早报交易日 09:00、晚报交易日 21:00、周报周日 18:00（`Asia/Shanghai`）。

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

## 产品更新与个人配置更新

两类更新彼此独立：`opinion-tracker update-check` 检查产品仓库的新功能，`opinion-tracker update --yes` 仅以 fast-forward 方式更新产品代码，不修改个人配置；`config-preflight` 拉取个人私有配置。Schema 较新时旧版本会停止覆盖并提示先更新产品。

定时器应调用统一入口 `scheduled-run`，而不是直接调用 `jobs run-due`。它在抓取前要求产品工作树
干净、拉取 `origin/main` 并确认当前提交为最新；存在可快进更新时自动更新、重新安装并重启到新代码，
然后才执行个人配置预检。网络失败、本地改动、分叉或安装失败均会停止本轮任务，不抓取、不发信。
因此新设备首次克隆并运行 `bootstrap.sh` 后也能沿用同一更新机制；本机路径、浏览器登录态、钥匙串
和调度器仍不会进入仓库。

Schema v2 使用稳定任务 ID：`morning`（交易日 09:00）、`evening`（交易日 21:00）和 `weekly`（周日 18:00）。运行 `opinion-tracker jobs list --workspace ./data` 可在任何 Agent 中查看任务，不需要知道内部目录。

```bash
opinion-tracker jobs summary morning --workspace ./data
opinion-tracker jobs confirm morning --workspace ./data
opinion-tracker jobs run morning --workspace ./data --output ./reports/morning
opinion-tracker scheduled-run --repository "$PWD" --workspace ./data --output-root ./scheduled-reports
opinion-tracker jobs deliver morning --workspace ./data --cutoff 2026-08-07T09:00:00+08:00 \
  --address user@163.com --report ./reports/morning/report.md \
  --verification ./reports/morning/report.json
opinion-tracker jobs clean-runs --workspace ./data --older-than-days 30
```

`scheduled-run` 依次执行产品版本预检、个人远端配置预检和到期任务。09:02/21:02 等 15 分钟内的
延迟启动仍使用 09:00/21:00 计划截止时间。分页状态按稳定运行 ID 持久化，405/429/临时 5xx 在
单账号最多 10 分钟预算内重试；普通账号 QPS=1，`auxiliary_news` 默认 QPS=0.4。最终报告核验后
使用 `jobs deliver` 幂等发送，SMTP 成功回执存在后才推进检查点。失败或不完整任务不会推进。

## 网易邮箱推送

验证通过的日报或周报可以通过网易个人邮箱发送。客户端授权码只保存在 macOS 钥匙串，
不会写入仓库、配置文件或日志：

```bash
.venv/bin/opinion-tracker email-setup --address user@163.com
.venv/bin/opinion-tracker email-test --address user@163.com
.venv/bin/opinion-tracker email-send --address user@163.com --report reports/report.md \
  --verification reports/report.json --kind daily
```

支持 `163.com`、`126.com` 和 `yeah.net`，默认使用 SSL 465 端口。非 macOS 环境可通过
`IOT_SMTP_AUTH_CODE` 环境变量临时提供授权码，但不得将该变量写入版本控制文件。
`email-send` 会读取 `report.json` 并再次检查核验门禁；未达到 `ready_for_final` 的草稿禁止发送为正式报告。

本项目只提供研究辅助，不构成投资建议。
