from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_portable_skill_contract():
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    for phrase in [
        "授权",
        "QPS",
        "不完整",
        "交易者画像",
        "定时任务",
        "MCP",
        "WorkBuddy",
        "外置 Chrome",
        "tdx-api",
    ]:
        assert phrase in text
    assert (ROOT / "agents" / "openai.yaml").exists()
    assert (ROOT / "references" / "workbuddy.md").exists()


def test_all_agent_guides_require_confirmed_onboarding():
    files = ["README.md", "SKILL.md", "references/cli.md", "references/workbuddy.md"]
    for name in files:
        text = (ROOT / name).read_text(encoding="utf-8")
        for phrase in ["--no-interactive", "task-summary", "task-confirm", "确认"]:
            assert phrase in text, f"{name} missing {phrase}"
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert "不得复用历史" in skill
    assert "确认前不得抓取" in skill
    for phrase in ["evidence-pack.json", "ANALYZE.md", "Agent 推导", "仓位建议默认关闭"]:
        assert phrase in skill
