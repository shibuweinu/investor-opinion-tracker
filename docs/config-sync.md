# 个人配置仓库同步

每位用户使用自己控制的私有 Git 仓库同步追踪账号、账号角色、日报/周报规则、交易画像和报告偏好。产品不需要中心服务，也不把个人配置提交到产品代码仓库。

```bash
opinion-tracker config-connect --workspace ./data --repo git@github.com:USER/investor-opinion-tracker-config.git
opinion-tracker config-status --workspace ./data
opinion-tracker config-pull --workspace ./data
opinion-tracker config-push --workspace ./data
opinion-tracker config-trust --workspace ./data
```

首次初始化必须选择 `restore`、`create` 或 `skip`。`init --config-repo` 只连接和预览；拉取、推送和本机信任分别确认。远端 `sync.trusted_auto_apply=true` 与本机授权同时成立后，定时任务才可自动应用合法快进更新。

配置仓库只允许 `.gitignore`、`README.md` 和 `config.json`。Cookie、浏览器登录态、SMTP 授权码、报告、日志、数据库、绝对路径及未知字段不会同步。发生分叉、身份变化、仓库不再私有或 Schema 校验失败时，自动信任失效并保留上一次已确认配置。
