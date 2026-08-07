# WorkBuddy / 通用 MCP

安装 `pip install '.[mcp]'` 后，把以下 stdio 服务加入 Agent 的 MCP 配置：

```json
{
  "mcpServers": {
    "investor-opinion-tracker": {
      "command": "/absolute/path/to/.venv/bin/opinion-tracker-mcp",
      "args": []
    }
  }
}
```

WorkBuddy、Claude Desktop 及其他兼容 MCP 的 Agent 可使用同一配置结构；字段名称若有差异，以宿主文档为准。浏览器访问仍通过宿主适配器注入，不共享登录凭据。

安装后先运行 `opinion-tracker init --no-interactive`。WorkBuddy 必须询问用户任务需求，运行 `onboard` 保存草稿，再用 `task-summary` 展示摘要。只有用户明确确认当前摘要后才能调用 `task-confirm` 和 `run`；确认前不得抓取，也不得复用历史对话中的目标。

新设备收到未绑定状态后必须询问 `restore`、`create` 或 `skip`。恢复时使用 `config-connect`（或 `init --config-repo`）连接个人私有仓库，展示摘要后再运行 `config-pull`。远端 `trusted_auto_apply` 不能替代设备级确认；WorkBuddy 不得上传 Cookie、Token、邮箱授权码、报告或本机路径。

WorkBuddy 使用 `jobs list` 查询 `morning`、`evening`、`weekly`，不得拼接本机目录。产品新功能通过 `update-check`/`update` 获取，个人配置通过 `config-preflight` 获取；产品更新不会覆盖个人配置。
