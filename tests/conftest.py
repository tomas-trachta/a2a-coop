import pytest

from a2a_coop.store import CoopStore


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def store(tmp_path):
    return CoopStore(tmp_path / "coop.db")


@pytest.fixture
def team(store):
    store.register_agent("claude", "architect")
    store.register_agent("codex", "implementer")

    return store
