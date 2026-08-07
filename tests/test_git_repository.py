import subprocess

import pytest

from opinion_tracker.git_repository import GitConflictError, GitRepository, canonicalize_remote


def git(*args, cwd=None):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def test_canonicalizes_github_ssh_and_https():
    assert canonicalize_remote("git@github.com:me/config.git") == "github.com/me/config"
    assert canonicalize_remote("https://github.com/me/config.git") == "github.com/me/config"


def test_push_is_fast_forward_only(tmp_path):
    remote = tmp_path / "remote.git"
    git("init", "--bare", str(remote))
    repo = GitRepository(str(remote), tmp_path / "one")
    repo.clone_or_open()
    repo.write("config.json", "{}")
    repo.commit(["config.json"], "initial")
    repo.push_fast_forward()
    assert repo.remote_head() == repo.head()


def test_rejects_push_when_remote_advanced(tmp_path):
    remote = tmp_path / "remote.git"
    git("init", "--bare", str(remote))
    first = GitRepository(str(remote), tmp_path / "one")
    first.clone_or_open(); first.write("config.json", "{}"); first.commit(["config.json"], "one"); first.push_fast_forward()
    second = GitRepository(str(remote), tmp_path / "two"); second.clone_or_open()
    first.write("config.json", '{"v":2}'); first.commit(["config.json"], "two"); first.push_fast_forward()
    second.write("README.md", "local"); second.commit(["README.md"], "local")
    with pytest.raises(GitConflictError):
        second.push_fast_forward()


def test_update_fast_forward_adopts_remote_commit(tmp_path):
    remote = tmp_path / "remote.git"; git("init", "--bare", str(remote))
    first = GitRepository(str(remote), tmp_path / "one"); first.clone_or_open()
    first.write("config.json", "{}"); first.commit(["config.json"], "one"); first.push_fast_forward()
    second = GitRepository(str(remote), tmp_path / "two"); second.clone_or_open()
    first.write("config.json", '{"v":2}'); first.commit(["config.json"], "two"); first.push_fast_forward()
    assert second.update_fast_forward() is True
    assert second.head() == first.head()
