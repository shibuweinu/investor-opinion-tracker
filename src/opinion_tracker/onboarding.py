# ruff: noqa: E501
from pathlib import Path

from .config import Settings
from .schemas import TaskDraft


def landing_text(settings: Settings) -> str:
    profile = settings.trader_profile
    return f"""# Investor Opinion Tracker 已就绪

## 产品用途

使用用户已授权、已登录的外置 Chrome 抓取雪球博主时间线，跟踪观点变化，并结合行情生成带证据等级、失效条件和风险预算的日报或周报。

## 当前默认配置

- 时区：{settings.timezone}
- 回溯：{settings.default_lookback_days} 天
- 雪球 QPS：{settings.xueqiu_qps}
- 交易风格：{profile.style} / {profile.aggressiveness}
- 单笔计划亏损 {profile.max_loss_per_trade_pct}%
- A股行情：内置 TDX HTTP 客户端，无需安装 tdx-api Skill

## 第一次任务

1. Agent 安装使用 `opinion-tracker init --no-interactive`，然后询问博主主页、回溯天数、日报或周报及交易者画像。
2. Agent 运行 `onboard` 保存草稿并展示任务摘要；示例目标绝不会成为默认目标。
3. 用户明确确认摘要后，Agent 才运行 `task-confirm` 和 `run`。

示例请求：

```text
跟踪 https://xueqiu.com/u/2292705444 最近5天发言，QPS=1，生成偏短线日报；
结合TDX行情输出行业、股票、证据等级、失效条件和条件仓位。
```

## 常用命令

```bash
opinion-tracker doctor
opinion-tracker profile
opinion-tracker task-status
opinion-tracker task-summary
opinion-tracker schedule-hint --kind daily
opinion-tracker schedule-hint --kind weekly
opinion-tracker welcome
```

首次成功报告后可提示用户创建定时任务，但不会未经确认自行创建。凭据始终留在浏览器，不写入配置或报告。
任务确认之前不会连接雪球或开始抓取。
"""


def write_landing(workspace: Path, settings: Settings) -> Path:
    directory = workspace / ".investor-opinion-tracker"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "WELCOME.md"
    path.write_text(landing_text(settings), encoding="utf-8")
    return path


def task_summary(draft: TaskDraft) -> str:
    profile = draft.trader_profile
    targets = "、".join(str(item) for item in draft.user_urls)
    return f"""任务摘要（尚未执行）
- 博主：{targets}
- 回溯：{draft.lookback_days} 天
- QPS：{draft.qps}
- 报告：{draft.report_type}
- 画像：{profile.style} / {profile.aggressiveness} / 单笔计划亏损 {profile.max_loss_per_trade_pct}%
- 授权声明：{"已声明" if draft.authorization_confirmed else "未声明"}
- 仓位建议：{"开启" if draft.include_position_sizing else "关闭"}
确认内容无误后，再运行 opinion-tracker task-confirm。
"""
