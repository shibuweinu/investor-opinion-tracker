def schedule_hint(kind: str) -> str:
    cron = "30 18 * * 1-5" if kind == "daily" else "0 10 * * 6"
    return f"建议的 {kind} cron：{cron}（Asia/Shanghai）。不会自动创建；请用户确认后交给其 Agent/系统调度器。"
