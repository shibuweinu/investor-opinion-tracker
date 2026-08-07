# 输入输出契约

输入使用 `RunRequest`：`user_url`、`lookback_days`、`qps<=1`、`authorization_confirmed`、可选
`as_of` 和 `since`。存在成功检查点时必须把增量起点传入 `since`，让采集器在翻页阶段停止；
不能先抓完整历史窗口再在结果中做增量过滤。

输出使用 `RunResult`：运行状态、抓取数、结构化观点、交易候选和告警。`incomplete` 或 `failed` 不得输出 active 候选。

定时报告的 `MarketSnapshot` 必须同时记录 `market_time` 与 `verified_at`：前者是行情所属交易时间，
后者是核验执行时间。报告截止时间之后的行情不得进入该期报告。

持久化内容仅包含标准化帖子、观点、运行游标和配置；严禁 Cookie、Token、密码、验证码。
