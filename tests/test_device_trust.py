from opinion_tracker.device_trust import DeviceTrustStore, FileTrustBackend, RepositoryIdentity


def identity(user="me@example.com"):
    return RepositoryIdentity(canonical_remote="github.com/me/config", owner="me", git_identity=user)


def test_remote_preference_alone_does_not_grant_device_trust(tmp_path):
    store = DeviceTrustStore(FileTrustBackend(tmp_path / "trust.json"))
    assert not store.is_trusted(identity())


def test_explicit_authorization_matches_exact_identity(tmp_path):
    store = DeviceTrustStore(FileTrustBackend(tmp_path / "trust.json"))
    store.authorize(identity())
    assert store.is_trusted(identity())
    assert not store.is_trusted(identity("other@example.com"))
    assert oct((tmp_path / "trust.json").stat().st_mode & 0o777) == "0o600"


def test_revoke_removes_trust(tmp_path):
    store = DeviceTrustStore(FileTrustBackend(tmp_path / "trust.json"))
    store.authorize(identity()); store.revoke()
    assert not store.is_trusted(identity())
