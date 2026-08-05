# 输入输出契约

输入使用 `RunRequest`：`user_url`、`lookback_days`、`qps<=1`、`authorization_confirmed`、可选 `as_of`。

输出使用 `RunResult`：运行状态、抓取数、结构化观点、交易候选和告警。`incomplete` 或 `failed` 不得输出 active 候选。

持久化内容仅包含标准化帖子、观点、运行游标和配置；严禁 Cookie、Token、密码、验证码。

