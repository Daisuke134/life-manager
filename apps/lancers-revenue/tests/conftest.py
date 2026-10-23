import pytest

from skills.earn.lancers.tests.identity_fixture import write_identity


@pytest.fixture(autouse=True)
def local_user_identity(tmp_path, monkeypatch):
    home = tmp_path / "local-user"
    monkeypatch.setenv("HOME", str(home))
    write_identity(home)
