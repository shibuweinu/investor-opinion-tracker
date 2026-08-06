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
.venv/bin/opinion-tracker analyze-file --input examples/posts.json --output ./reports
```

数据默认只写入调用者指定的工作目录，不写入 Skill 安装目录。

`--user-url` 是可重复参数；例如 `--user-url https://xueqiu.com/u/111 --user-url https://xueqiu.com/u/222`。

Agent 必须先用 `task-summary` 向用户展示草稿；得到明确确认后才调用 `task-confirm`。确认前不得运行 `run` 或抓取。`--no-interactive` 仅跳过终端问答，不跳过任务确认。
