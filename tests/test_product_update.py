from pathlib import Path

import pytest

from opinion_tracker.product_update import ensure_latest_product, update_status


def test_scheduled_product_preflight_does_nothing_when_current(monkeypatch, tmp_path):
    calls: list[object] = []
    monkeypatch.setattr(
        "opinion_tracker.product_update.require_clean_repository",
        lambda repository: calls.append(("clean", repository)),
        raising=False,
    )
    monkeypatch.setattr(
        "opinion_tracker.product_update.update_status", lambda repository: "current"
    )

    result = ensure_latest_product(
        tmp_path,
        Path("/venv/bin/opinion-tracker"),
        ["scheduled-run"],
        installer=lambda repository: calls.append(("install", repository)),
        reexec=lambda executable, argv: calls.append(("exec", executable, argv)),
    )

    assert result == "current"
    assert calls == [("clean", tmp_path)]


def test_scheduled_product_preflight_updates_installs_and_reexecs(monkeypatch, tmp_path):
    calls: list[object] = []
    monkeypatch.setattr(
        "opinion_tracker.product_update.require_clean_repository",
        lambda repository: calls.append(("clean", repository)),
        raising=False,
    )
    monkeypatch.setattr(
        "opinion_tracker.product_update.update_status",
        lambda repository: "update_available",
    )
    monkeypatch.setattr(
        "opinion_tracker.product_update.update_product",
        lambda repository: calls.append(("update", repository)),
    )

    result = ensure_latest_product(
        tmp_path,
        Path("/venv/bin/opinion-tracker"),
        ["scheduled-run", "--repository", str(tmp_path)],
        installer=lambda repository: calls.append(("install", repository)),
        reexec=lambda executable, argv: calls.append(("exec", executable, argv)),
    )

    assert result == "updated"
    assert calls == [
        ("clean", tmp_path),
        ("update", tmp_path),
        ("install", tmp_path),
        (
            "exec",
            "/venv/bin/opinion-tracker",
            [
                "/venv/bin/opinion-tracker",
                "scheduled-run",
                "--repository",
                str(tmp_path),
            ],
        ),
    ]


def test_scheduled_product_preflight_fails_closed_on_dirty_tree(monkeypatch, tmp_path):
    def reject_dirty(repository):
        raise RuntimeError("产品仓库存在未提交改动")

    monkeypatch.setattr(
        "opinion_tracker.product_update.require_clean_repository",
        reject_dirty,
        raising=False,
    )
    monkeypatch.setattr(
        "opinion_tracker.product_update.update_status",
        lambda repository: pytest.fail("dirty tree must fail before fetch"),
    )

    with pytest.raises(RuntimeError, match="未提交改动"):
        ensure_latest_product(
            tmp_path,
            Path("opinion-tracker"),
            ["scheduled-run"],
            installer=lambda repository: None,
            reexec=lambda executable, argv: None,
        )


def test_update_status_rejects_ahead_or_diverged_branch(monkeypatch, tmp_path):
    outputs = iter(["local\n", "remote\n"])
    monkeypatch.setattr(
        "opinion_tracker.product_update.subprocess.check_output",
        lambda *args, **kwargs: next(outputs),
    )

    class Result:
        returncode = 1

    monkeypatch.setattr(
        "opinion_tracker.product_update.subprocess.run",
        lambda *args, **kwargs: Result(),
    )

    with pytest.raises(RuntimeError, match="领先或已经分叉"):
        update_status(tmp_path)
