# ruff: noqa: E501
from pathlib import Path

from .config import Settings


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

1. 启动已登录雪球的外置 Chrome 调试模式，并确认 `agent-browser --cdp 9222` 可连接。
2. 告诉 Agent：博主主页、回溯天数、日报或周报；默认已存在授权声明。
3. 让 Agent 读取仓库根目录 `SKILL.md` 并运行任务。

示例请求：

```text
跟踪 https://xueqiu.com/u/2292705444 最近5天发言，QPS=1，生成偏短线日报；
结合TDX行情输出行业、股票、证据等级、失效条件和条件仓位。
```

## 常用命令

```bash
opinion-tracker doctor
opinion-tracker profile
opinion-tracker schedule-hint --kind daily
opinion-tracker schedule-hint --kind weekly
opinion-tracker welcome
```

首次成功报告后可提示用户创建定时任务，但不会未经确认自行创建。凭据始终留在浏览器，不写入配置或报告。
"""


def write_landing(workspace: Path, settings: Settings) -> Path:
    directory = workspace / ".investor-opinion-tracker"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "WELCOME.md"
    path.write_text(landing_text(settings), encoding="utf-8")
    return path
