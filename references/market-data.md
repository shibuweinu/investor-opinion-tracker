# 行情源顺序

## 1. 内置 TDX 客户端（A股优先）

仓库已经根据本地 `stock-trading` 项目的 `tdx-api` 契约内置 `opinion_tracker.market.TdxClient`。最终用户无需安装该 Skill，直接使用：

1. `GET http://tdx.acdzh.xyz/api/server-status`
2. A股实时行情使用 `/api/quote?code=...`
3. 日线使用 `/api/kline?code=...&type=day`；需要明确前复权时使用 `/api/kline-all/ths`
4. 请求必须带 `User-Agent: Mozilla/5.0`，超时设为 10 秒
5. quote/kline 价格单位为厘，展示时除以 1000；成交量通常为手

TDX 仅支持股票，不要把 ETF、基金或港股代码误送给它。服务不可达时在 10 秒内失败并降级。

## 2. AKShare（补充源）

ETF、基金、港股以及 TDX 失败时使用 AKShare。每个请求设置有限超时；单源失败后立即降级，不允许无限等待。

## 3. 权威网页核验

行情源均失败时，使用交易所、公司公告或基金公司页面核验。报告必须标记行情不完整，并取消 active 状态和主动仓位建议。
