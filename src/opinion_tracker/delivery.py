from __future__ import annotations

import getpass
import json
import os
import smtplib
import subprocess
import sys
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path

KEYCHAIN_SERVICE = "investor-opinion-tracker.smtp"
AUTH_CODE_ENV = "IOT_SMTP_AUTH_CODE"


@dataclass(frozen=True)
class SmtpSettings:
    host: str
    port: int = 465


def smtp_settings_for(address: str) -> SmtpSettings:
    domain = address.rsplit("@", 1)[-1].lower()
    hosts = {
        "163.com": "smtp.163.com",
        "126.com": "smtp.126.com",
        "yeah.net": "smtp.yeah.net",
    }
    try:
        return SmtpSettings(host=hosts[domain])
    except KeyError as exc:
        raise ValueError("仅支持 163.com、126.com 和 yeah.net 网易个人邮箱") from exc


def store_auth_code_in_keychain(address: str, auth_code: str) -> None:
    if sys.platform != "darwin":
        raise RuntimeError(f"当前系统不支持 macOS 钥匙串，请改用环境变量 {AUTH_CODE_ENV}")
    if not auth_code.strip():
        raise ValueError("客户端授权码不能为空")
    command = [
        "security",
        "add-generic-password",
        "-a",
        address,
        "-s",
        KEYCHAIN_SERVICE,
        "-U",
        "-w",
    ]
    completed = subprocess.run(
        command,
        input=f"{auth_code.strip()}\n",
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("写入 macOS 钥匙串失败，请确认钥匙串已解锁")


def prompt_and_store_auth_code(address: str) -> None:
    auth_code = getpass.getpass("网易邮箱客户端授权码（输入不会显示）：")
    store_auth_code_in_keychain(address, auth_code)


def load_auth_code(address: str) -> str:
    from_environment = os.environ.get(AUTH_CODE_ENV)
    if from_environment:
        return from_environment
    if sys.platform != "darwin":
        raise RuntimeError(f"未找到 SMTP 凭据，请设置环境变量 {AUTH_CODE_ENV}")
    completed = subprocess.run(
        [
            "security",
            "find-generic-password",
            "-a",
            address,
            "-s",
            KEYCHAIN_SERVICE,
            "-w",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        raise RuntimeError("未找到网易邮箱授权码，请先运行 email-setup")
    return completed.stdout.strip()


def build_report_message(address: str, report_path: Path, report_kind: str) -> EmailMessage:
    if report_kind not in {"daily", "weekly", "test"}:
        raise ValueError("邮件类型必须是 daily、weekly 或 test")
    labels = {"daily": "日报", "weekly": "周报", "test": "测试邮件"}
    message = EmailMessage()
    message["From"] = address
    message["To"] = address
    message["Subject"] = f"[投资者观点跟踪] {labels[report_kind]}"
    if report_kind == "test":
        message.set_content("网易邮箱推送通道配置成功。后续验证通过的日报和周报将发送到此邮箱。")
        return message

    content = report_path.read_text(encoding="utf-8")
    message.set_content(content)
    message.add_attachment(
        content.encode("utf-8"),
        maintype="text",
        subtype="markdown",
        filename=report_path.name,
    )
    return message


def send_message(address: str, message: EmailMessage, timeout_seconds: float = 20.0) -> None:
    settings = smtp_settings_for(address)
    auth_code = load_auth_code(address)
    with smtplib.SMTP_SSL(settings.host, settings.port, timeout=timeout_seconds) as smtp:
        smtp.login(address, auth_code)
        smtp.send_message(message)


def send_report(address: str, report_path: Path, report_kind: str) -> None:
    if not report_path.is_file():
        raise FileNotFoundError(f"报告不存在：{report_path}")
    send_message(address, build_report_message(address, report_path, report_kind))


def require_verified_result(verification_path: Path) -> None:
    try:
        payload = json.loads(verification_path.read_text(encoding="utf-8"))
        verification = payload["verification"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError("无法读取有效的报告核验结果") from exc
    if payload.get("status") != "complete" or verification.get("ready_for_final") is not True:
        raise ValueError("核验门禁未通过，禁止发送正式日报或周报")


def send_test(address: str) -> None:
    smtp_settings_for(address)
    send_message(address, build_report_message(address, Path(), "test"))
