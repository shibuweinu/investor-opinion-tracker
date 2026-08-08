# 日报和周报触发

调度属于宿主系统，不由核心服务私自创建。首次成功报告后询问用户是否启用：

- 早报：交易日 09:00；从上一份成功晚报的检查点增量抓取
- 晚报：交易日 21:00；从当日成功早报的检查点增量抓取
- 周报：周日 18:00；从上一份成功周报的检查点增量抓取
- 时区：`Asia/Shanghai`

本机调度器只调用以下统一入口，具体计划来自 Schema v2 的 `report_jobs`：

```bash
opinion-tracker scheduled-run --repository /path/to/investor-opinion-tracker \
  --workspace /path/to/data --output-root /path/to/scheduled-reports
```

每次任务执行“产品版本预检 → 必要时 fast-forward、重新安装并重启 → 配置预检 → 授权会话检查 →
增量抓取 → 标准化 JSON → Agent 分析与核验 → `jobs deliver`”。产品仓库必须干净且与
`origin/main` 可快进；否则失败关闭。若登录失效、
访问验证或抓取不完整，不推进检查点、不发送正式报告；下一次运行从最后成功检查点补抓。

调度器晚到不超过 15 分钟仍匹配原计划时间，例如 21:02 使用 21:00 的稳定运行 ID 和行情截止时间。
分页断点保存在工作区 `.investor-opinion-tracker/runs/`；405、429、临时 5xx 在同页有界重试，每个
账号累计退避最多 10 分钟。清理只使用 `jobs clean-runs`，不会触及最终报告或个人配置。

宿主可使用 cron、systemd timer、GitHub Actions（仅适用于合法可用的凭据方案）、Codex Automations 或 WorkBuddy 定时器。不要把 Cookie 或 Token 写入仓库和命令行参数。
