"""BI uploads: a local directory by default, S3 only when fully configured.

Farid, 08/09/26. Before this, a fresh open-source install died on its first
CSV upload (``ValueError: Invalid endpoint:``, the empty S3_ENDPOINT handed
to boto3). Three things to protect:

1. the backend choice follows the artifact store's predicate: S3 needs
   ``STORAGE_MODE=S3`` and every credential; anything less is local;
2. the local store is a faithful backend: same keys, same listing shape,
   read/delete round-trip, a missing file reads as ``None`` like S3;
3. a key never escapes the store (``..``, absolute paths).
"""

from __future__ import annotations

import pytest

from apowerb.bi.data import _bi_storage as bi
from apowerb.configs import paths


class _Settings:
    def __init__(self, mode="S3", **s3):
        self.storage_mode = mode
        self.s3_bucket_name = s3.get("bucket", "")
        self.s3_access_key = s3.get("key", "")
        self.s3_access_key_secret = s3.get("secret", "")
        self.s3_endpoint = s3.get("endpoint", "")
        self.s3_region = s3.get("region", "")


FULL_S3 = dict(
    bucket="b", key="k", secret="s", endpoint="https://s3.example", region="gra"
)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "bi_store_dir", lambda: tmp_path / "bi_store")
    monkeypatch.setattr(bi, "bi_store_dir", lambda: tmp_path / "bi_store")
    monkeypatch.setattr(bi, "get_settings", lambda: _Settings("local"))
    return tmp_path / "bi_store"


# ------------------------------------------------------------- selection
def test_no_s3_at_all_means_local(monkeypatch):
    monkeypatch.setattr(bi, "get_settings", lambda: _Settings("S3"))
    assert bi.storage_backend() == "local"


def test_storage_mode_local_wins_even_with_credentials(monkeypatch):
    monkeypatch.setattr(bi, "get_settings", lambda: _Settings("local", **FULL_S3))
    assert bi.storage_backend() == "local"


def test_half_configured_s3_is_local_not_an_error(monkeypatch):
    partial = dict(FULL_S3, endpoint="")
    monkeypatch.setattr(bi, "get_settings", lambda: _Settings("S3", **partial))
    assert bi.storage_backend() == "local"


def test_fully_configured_s3_is_s3(monkeypatch):
    monkeypatch.setattr(bi, "get_settings", lambda: _Settings("S3", **FULL_S3))
    assert bi.storage_backend() == "s3"


# ------------------------------------------------------------- local store
def test_round_trip_keeps_the_s3_key_shape(store):
    key = bi.save_file(
        "thaink2.com", "proj 1", "abc123", "ventes.CSV", b"a;b\n1;2\n", "text/csv"
    )
    assert key == "bi/data/thaink2.com/proj-1/data/abc123.csv"
    assert (store / key).read_bytes() == b"a;b\n1;2\n"
    assert bi.read_file(key) == b"a;b\n1;2\n"


def test_listing_has_the_same_shape_as_s3(store):
    bi.save_file("org", "p", "f1", "a.csv", b"1", "text/csv")
    bi.save_file("org", "p", "f2", "b.xlsx", b"2", "application/octet-stream")
    bi.save_file("org", "other", "f3", "c.csv", b"3", "text/csv")
    rows = bi.list_files("org", "p")
    assert [r["file_id"] for r in rows] == ["f1", "f2"]
    assert rows[0] == {
        "file_id": "f1",
        "filename": "f1.csv",
        "organization_id": "org",
        "project_id": "p",
        "key": "bi/data/org/p/data/f1.csv",
        "extension": ".csv",
    }
    assert bi.list_files("org", "nothing-here") == []


def test_delete_then_read_is_none_like_s3(store):
    key = bi.save_file("org", "p", "f1", "a.csv", b"1", "text/csv")
    assert bi.delete_file(key) is True
    assert bi.read_file(key) is None
    assert bi.delete_file(key) is False


def test_a_missing_file_reads_as_none(store):
    assert bi.read_file("bi/data/org/p/data/ghost.csv") is None


# ------------------------------------------------------------- containment
@pytest.mark.parametrize(
    "key",
    ["../outside.csv", "bi/data/../../../etc/passwd", "/etc/passwd"],
)
def test_a_key_never_escapes_the_store(store, key):
    with pytest.raises(ValueError):
        bi._local_path(key)
    # and the public surface swallows it into the same "not there" answers
    assert bi.read_file(key) is None
    assert bi.delete_file(key) is False


def test_s3_backend_is_used_when_configured(monkeypatch):
    monkeypatch.setattr(bi, "get_settings", lambda: _Settings("S3", **FULL_S3))
    seen = {}
    import apowerb.storage.s3 as s3

    monkeypatch.setattr(
        s3, "upload_bytes_to_s3", lambda content, key, ct: seen.update(key=key, ct=ct)
    )
    key = bi.save_file("org", "p", "f1", "a.csv", b"1", "text/csv")
    assert seen == {"key": key, "ct": "text/csv"}
