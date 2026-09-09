"""Long-lived synchronous engines, built so a dropped connection is not a 500.

The async engine has carried ``pool_pre_ping`` and ``pool_recycle`` since it
was written (``helpers/database.py``); the synchronous stores never did. They
are module-level singletons that live as long as the process, so their pooled
connections outlive anything the managed cluster is willing to keep open. The
cluster closes one, the pool hands it out anyway, and psycopg2 raises

    OperationalError: SSL connection has been closed unexpectedly

which the router turns into a 500 -- measured twice in the Hostman demo logs
of 08/09/26, on ``GET /api/agents`` and ``GET /api/emailing/microsoft/status``,
minutes apart, with nothing wrong on either side.

``pool_pre_ping`` costs one round-trip per checkout and turns that into a
transparent reconnect; ``pool_recycle`` retires a connection before the
cluster's own idle timeout can. The one-shot migration engines are left alone:
they run once at boot and hand their connection back immediately.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import create_engine

# Shorter than the idle timeout of every managed Postgres we run against
# (OVH, Hostman): a connection is retired by us rather than closed under us.
POOL_RECYCLE_SECONDS = 300


def create_sync_engine(url: str, **kwargs: Any):
    """``create_engine`` for an engine that outlives its connections."""
    kwargs.setdefault("pool_pre_ping", True)
    kwargs.setdefault("pool_recycle", POOL_RECYCLE_SECONDS)
    return create_engine(url, **kwargs)
