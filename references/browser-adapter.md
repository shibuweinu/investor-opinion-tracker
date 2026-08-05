# 已登录浏览器适配

核心不绑定任何浏览器厂商。宿主 Agent 实现：

```python
class BrowserPort:
    def fetch_timeline(self, user_id: str, page: int, count: int) -> dict: ...
```

实现可使用 Codex 内置浏览器、Playwright、Chrome DevTools 或 WorkBuddy 浏览器工具。会话凭据始终由宿主持有，返回值只包含雪球时间线响应。遇到登录、验证码或风控立即返回可恢复状态，不尝试绕过。

