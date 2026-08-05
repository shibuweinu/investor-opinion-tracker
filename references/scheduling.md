# 日报和周报触发

调度属于宿主系统，不由核心服务私自创建。首次成功报告后询问用户是否启用：

- 日报：交易日 18:30，`30 18 * * 1-5`
- 周报：周六 10:00，`0 10 * * 6`
- 时区：`Asia/Shanghai`

每次任务执行“授权会话检查 → 增量抓取 → 标准化 JSON → `analyze-file` → 投递报告”。若登录失效或抓取不完整，保留游标并输出观察版报告，不给主动仓位。

宿主可使用 cron、systemd timer、GitHub Actions（仅适用于合法可用的凭据方案）、Codex Automations 或 WorkBuddy 定时器。不要把 Cookie 或 Token 写入仓库和命令行参数。

