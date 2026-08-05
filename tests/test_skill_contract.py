from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_portable_skill_contract():
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    for phrase in ["授权", "QPS", "不完整", "交易者画像", "定时任务", "MCP", "WorkBuddy"]:
        assert phrase in text
    assert (ROOT / "agents" / "openai.yaml").exists()
    assert (ROOT / "references" / "workbuddy.md").exists()
