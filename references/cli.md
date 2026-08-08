# CLI

```bash
python3.11 -m venv .venv
.venv/bin/pip install '.[dev,mcp]'
.venv/bin/opinion-tracker init --workspace ./data --no-interactive
.venv/bin/opinion-tracker doctor
.venv/bin/opinion-tracker onboard --workspace ./data --user-url https://xueqiu.com/u/USER_ID --lookback-days 5 --report-type daily --accept-default-profile
.venv/bin/opinion-tracker task-summary --workspace ./data
.venv/bin/opinion-tracker task-confirm --workspace ./data
.venv/bin/opinion-tracker run --workspace ./data --output ./reports
.venv/bin/opinion-tracker schedule-hint --kind daily
.venv/bin/opinion-tracker analyze-file --workspace ./data --input examples/posts.json --claims ./claims.json --fact-evidence ./facts.json --output ./reports
.venv/bin/opinion-tracker scheduled-run --repository "$PWD" --workspace ./data --output-root ./scheduled-reports
.venv/bin/opinion-tracker jobs deliver morning --workspace ./data --cutoff 2026-08-07T09:00:00+08:00 --address user@163.com --report ./report.md --verification ./report.json
.venv/bin/opinion-tracker jobs clean-runs --workspace ./data --older-than-days 30
```

数据默认只写入调用者指定的工作目录，不写入 Skill 安装目录。

`--user-url` 是可重复参数；例如 `--user-url https://xueqiu.com/u/111 --user-url https://xueqiu.com/u/222`。

Agent 必须先用 `task-summary` 向用户展示草稿；得到明确确认后才调用 `task-confirm`。确认前不得运行 `run` 或抓取。`--no-interactive` 仅跳过终端问答，不跳过任务确认。

`analyze-file` 默认从 TDX 拉取所有帖子及研究主张中的显式 A 股代码。`--claims` 接受
`ResearchClaim` JSON 数组，每条正式观点必须归入 `subjective` 或 `factual`；只有 `factual` 主张
必须通过 `--fact-evidence` 提供独立事实证据。证据文件是 `FactEvidence` JSON 数组，每项通过
`claim_ids` 关联事实主张，来源类型只接受 `company`、`exchange`、
`regulator`、`government` 或 `filing`。行情或事实核验未完成时只生成 `UNVERIFIED.md`，不会生成
`report.md`；传入 `--workspace` 后使用当前任务画像，不再回落到默认风险参数。
门禁失败时仍会写出 `UNVERIFIED.md` 和 `report.json` 供补证，但命令以退出码 2 结束，阻止自动化
流程把草稿当作最终报告。可从 `report.json` 获取 `opinion_id`，补齐对应事实证据后重新运行。

自动化必须使用 `scheduled-run` 作为入口。它先确认产品代码为干净、可快进且已更新的
`origin/main`，更新时重新安装并重启，再由 `jobs run-due` 完成个人配置预检和任务执行。
`jobs deliver` 使用稳定 Message-ID 和本地成功回执防止已确认邮件重复发送；SMTP 成功后才推进
检查点。运行状态仅由 `jobs clean-runs` 按保留天数显式清理。
