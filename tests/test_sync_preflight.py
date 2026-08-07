from dataclasses import dataclass

from opinion_tracker.sync_preflight import preflight_scheduled_run


@dataclass
class FakeDocument:
    trusted_auto_apply: bool


class FakeService:
    def __init__(self, changed=True):
        self.changed = changed
        self.applied = False
        self.ensured = False

    def update(self):
        return self.changed

    def document(self):
        return FakeDocument(True)

    def apply_trusted(self):
        self.applied = True

    def ensure_local(self, *, trusted: bool):
        self.ensured = True


def test_remote_flag_without_local_trust_requires_confirmation():
    service = FakeService()
    result = preflight_scheduled_run(service, locally_trusted=False)
    assert result.action == "confirmation_required"
    assert not service.applied


def test_trusted_device_auto_applies_update():
    service = FakeService()
    result = preflight_scheduled_run(service, locally_trusted=True)
    assert result.action == "run"
    assert service.applied


def test_unchanged_remote_still_initializes_missing_local_jobs():
    service = FakeService(changed=False)
    assert preflight_scheduled_run(service, locally_trusted=True).action == "run"
    assert service.ensured
