from __future__ import annotations

from pathlib import Path

import pytest

from opinion_tracker.delivery import build_report_message, require_verified_result, smtp_settings_for


@pytest.mark.parametrize(
    ("address", "host"),
    [
        ("user@163.com", "smtp.163.com"),
        ("user@126.com", "smtp.126.com"),
        ("user@yeah.net", "smtp.yeah.net"),
    ],
)
def test_smtp_settings_for_netease(address: str, host: str) -> None:
    settings = smtp_settings_for(address)
    assert settings.host == host
    assert settings.port == 465


def test_smtp_settings_rejects_other_domains() -> None:
    with pytest.raises(ValueError, match="仅支持"):
        smtp_settings_for("user@example.com")


def test_build_report_message_attaches_markdown(tmp_path: Path) -> None:
    report = tmp_path / "daily.md"
    report.write_text("# 验证日报\n\n内容", encoding="utf-8")

    message = build_report_message("user@163.com", report, "daily")

    assert message["To"] == "user@163.com"
    assert "日报" in str(message["Subject"])
    assert message.is_multipart()
    assert message.get_body(preferencelist=("plain",)).get_content().startswith("# 验证日报")
    attachments = list(message.iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_filename() == "daily.md"


def test_build_test_message_does_not_read_path() -> None:
    message = build_report_message("user@163.com", Path(), "test")
    assert "配置成功" in message.get_content()


@pytest.mark.parametrize(("kind", "label"), [("morning", "早报"), ("evening", "晚报")])
def test_build_report_message_distinguishes_morning_evening(tmp_path: Path, kind: str, label: str):
    report = tmp_path / "report.md"
    report.write_text("# report", encoding="utf-8")
    assert label in str(build_report_message("user@163.com", report, kind)["Subject"])


def test_require_verified_result_accepts_ready_report(tmp_path: Path) -> None:
    verification = tmp_path / "report.json"
    verification.write_text('{"status":"complete","verification":{"ready_for_final":true}}', encoding="utf-8")
    require_verified_result(verification)


def test_require_verified_result_accepts_safe_partial_report(tmp_path: Path) -> None:
    verification = tmp_path / "report.json"
    verification.write_text(
        '{"status":"complete","verification":'
        '{"ready_for_final":false,"ready_for_delivery":true}}',
        encoding="utf-8",
    )
    require_verified_result(verification)


@pytest.mark.parametrize(
    "payload",
    [
        '{"status":"incomplete","verification":{"ready_for_final":true}}',
        '{"status":"complete","verification":'
        '{"ready_for_final":false,"ready_for_delivery":false}}',
        "{}",
    ],
)
def test_require_verified_result_rejects_unverified_report(tmp_path: Path, payload: str) -> None:
    verification = tmp_path / "report.json"
    verification.write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError, match="核验|有效"):
        require_verified_result(verification)


def test_report_message_accepts_stable_message_id(tmp_path: Path) -> None:
    report = tmp_path / "report.md"
    report.write_text("# report", encoding="utf-8")

    message = build_report_message(
        "user@163.com", report, "evening", message_id="<run@example>"
    )

    assert message["Message-ID"] == "<run@example>"
