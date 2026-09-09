"""A dropped connection must not surface as a 500.

The managed cluster closes idle connections; the synchronous stores are
process-lifetime singletons, so their pool hands out a dead one and psycopg2
raises "SSL connection has been closed unexpectedly". Measured twice in the
Hostman logs of 08/09/26 (GET /api/agents, GET /api/emailing/microsoft/status).

Two things to protect: the helper's defaults, and the fact that every
long-lived store actually goes through it -- a store that calls
``create_engine`` directly is exactly the hole this closes.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from apowerb.helpers.sync_engine import POOL_RECYCLE_SECONDS, create_sync_engine

# Stores whose engine lives as long as the process. Migration helpers run once
# at boot and are deliberately not here.
LONG_LIVED = [
    "agent_store/agent_manager.py",
    "agent_store/hub_manager.py",
    "agent_store/api_key_store.py",
    "skills_store/skill_manager.py",
    "tools_store/tool_config.py",
]

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "apowerb"


def test_the_helper_pings_and_recycles_by_default():
    seen = {}

    import apowerb.helpers.sync_engine as mod

    original = mod.create_engine
    mod.create_engine = lambda url, **kw: seen.update(url=url, **kw)
    try:
        create_sync_engine("postgresql://u:p@h/db")
    finally:
        mod.create_engine = original
    assert seen["pool_pre_ping"] is True
    assert seen["pool_recycle"] == POOL_RECYCLE_SECONDS


def test_an_explicit_option_still_wins():
    seen = {}

    import apowerb.helpers.sync_engine as mod

    original = mod.create_engine
    mod.create_engine = lambda url, **kw: seen.update(**kw)
    try:
        create_sync_engine("postgresql://u:p@h/db", pool_recycle=60, echo=True)
    finally:
        mod.create_engine = original
    assert (
        seen["pool_recycle"] == 60
        and seen["echo"] is True
        and seen["pool_pre_ping"] is True
    )


def test_it_really_builds_an_engine_that_pings():
    engine = create_sync_engine("sqlite://")
    assert engine.pool._pre_ping is True


@pytest.mark.parametrize("relative", LONG_LIVED)
def test_every_long_lived_store_goes_through_the_helper(relative):
    """Read the source: a store calling create_engine directly would keep
    handing out dead connections, and no unit test would notice."""
    source = (SRC / relative).read_text()
    tree = ast.parse(source)
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "create_sync_engine" in called, (
        f"{relative} must build its engine with create_sync_engine"
    )
    assert "create_engine" not in called, (
        f"{relative} still calls create_engine directly"
    )
