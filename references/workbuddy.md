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
