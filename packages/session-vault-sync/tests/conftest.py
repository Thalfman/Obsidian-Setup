"""Synthetic fixtures only; never inspect real assistant histories."""
import pytest

@pytest.fixture
def fake_claude(tmp_path):
    from test_sync import _make_fake_claude
    def make(vault_path, uuid="abcd1234-0000-0000-0000-000000000000", *, root=None):
        return _make_fake_claude(root or tmp_path / "claude", vault_path, uuid)
    return make
