# CLI

```bash
python3.11 -m venv .venv
.venv/bin/pip install '.[dev,mcp]'
.venv/bin/opinion-tracker init --workspace ./data
.venv/bin/opinion-tracker doctor
.venv/bin/opinion-tracker schedule-hint --kind daily
.venv/bin/opinion-tracker analyze-file --input examples/posts.json --output ./reports
```

数据默认只写入调用者指定的工作目录，不写入 Skill 安装目录。
