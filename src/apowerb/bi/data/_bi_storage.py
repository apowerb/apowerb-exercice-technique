"""Unified BI file storage -- S3 when fully configured, a local directory
otherwise.

Farid, 08/09/26: « pour les uploads, il doit y avoir une option : local
directory (par défaut) avec possibilité de configurer S3 ». Until then this
module was S3-only, and a fresh open-source install died on its first CSV
upload with ``ValueError: Invalid endpoint:`` -- the empty ``S3_ENDPOINT``
handed to boto3.

The backend is chosen by the same predicate as the ADK artifact store
(``is_s3_artifact_storage_configured``): ``STORAGE_MODE=S3`` **and** every S3
credential present. Anything else -- no S3 at all, or a half-filled one --
lands in ``bi_store_dir()`` (``BI_STORE_DIR``, ``bi_store`` under the runtime
root by default). Keys keep the same shape on both backends:

    bi/data/{organization_id}/{project_id}/data/{file_id}.{ext}

so a deployment can move from local to S3 without rewriting anything but
the files themselves.
"""

from __future__ import annotations

import os
import re
from logging import getLogger
from pathlib import Path
from typing import Any

from apowerb.configs.artifact_service_config import is_s3_artifact_storage_configured
from apowerb.configs.paths import bi_store_dir
from apowerb.configs.settings import get_settings

logger = getLogger(__name__)

_S3_PREFIX = "bi/data"


def storage_backend() -> str:
    """``"s3"`` when S3 is selected and fully configured, ``"local"`` otherwise."""
    return "s3" if is_s3_artifact_storage_configured(get_settings()) else "local"


def _safe_segment(value: str) -> str:
    value = value.strip()
    value = value.replace("/", "-").replace("\\", "-")
    value = re.sub(r"\s+", "-", value)
    return value or "default"


def _get_extension(filename: str) -> str:
    ext = os.path.splitext(os.path.basename(filename))[1].lower()
    return ext if ext else ".bin"


def bi_artifact_app_name(organization_id: str) -> str:
    """Pseudo-agent folder for mirroring a BI upload into the artifact chain.

    BI has no agent concept -- uploads are scoped by organization_id/
    project_id only (see upload_router.py), unlike RAG where agent_id is a
    real, owned ``agent<digits>`` folder. The "bi-" prefix keeps this out of
    that namespace so it can never be mistaken for one (see
    apowerb.helpers.ownership / routers.rag.validators, both anchored on
    ``^agent\\d+$``).
    """
    return f"bi-{_safe_segment(organization_id)}"


def build_file_key(
    organization_id: str,
    project_id: str,
    file_id: str,
    filename: str,
) -> str:
    org = _safe_segment(organization_id)
    project = _safe_segment(project_id)
    ext = _get_extension(filename)
    return f"{_S3_PREFIX}/{org}/{project}/data/{file_id}{ext}"


# ----------------------------------------------------------------- local


def _local_path(key: str) -> Path:
    """Absolute path of *key* under ``bi_store_dir()``, or ``ValueError``.

    Containment is the guard: a key is data (it comes from the database, and
    before that from request segments), so ``..`` or an absolute path must
    never escape the store -- same rule as ``uploads_path_containment``.
    """
    if not key or key.startswith(("/", "\\")) or os.path.isabs(key):
        raise ValueError(f"BI storage key must be relative: {key!r}")
    root = bi_store_dir().resolve()
    candidate = (root / key).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"BI storage key escapes the store: {key!r}")
    return candidate


def _local_save(key: str, content: bytes) -> None:
    path = _local_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _local_read(key: str) -> bytes:
    return _local_path(key).read_bytes()


def _local_delete(key: str) -> None:
    _local_path(key).unlink()


def _local_list(prefix: str) -> list[str]:
    base = _local_path(prefix)
    if not base.is_dir():
        return []
    root = bi_store_dir().resolve()
    return sorted(
        p.relative_to(root).as_posix() for p in base.rglob("*") if p.is_file()
    )


# ----------------------------------------------------------------- public


def save_file(
    organization_id: str,
    project_id: str,
    file_id: str,
    filename: str,
    content: bytes,
    content_type: str,
) -> str:
    key = build_file_key(organization_id, project_id, file_id, filename)
    if storage_backend() == "s3":
        from apowerb.storage.s3 import upload_bytes_to_s3

        upload_bytes_to_s3(content, key, content_type)
        logger.info("[BI Storage] Saved file to S3: %s", key)
    else:
        _local_save(key, content)
        logger.info("[BI Storage] Saved file locally: %s", key)
    return key


def read_file(key: str) -> bytes | None:
    try:
        if storage_backend() == "s3":
            from apowerb.storage.s3 import download_file_from_s3

            return download_file_from_s3(key)
        return _local_read(key)
    except Exception as exc:
        logger.error("[BI Storage] Failed to read %s: %s", key, exc)
        return None


def delete_file(key: str) -> bool:
    try:
        if storage_backend() == "s3":
            from apowerb.storage.s3 import delete_file_from_s3

            delete_file_from_s3(key)
        else:
            _local_delete(key)
        logger.info("[BI Storage] Deleted file: %s", key)
        return True
    except Exception as exc:
        logger.error("[BI Storage] Failed to delete %s: %s", key, exc)
        return False


def list_files(organization_id: str, project_id: str) -> list[dict[str, Any]]:
    org = _safe_segment(organization_id)
    project = _safe_segment(project_id)
    prefix = f"{_S3_PREFIX}/{org}/{project}/data/"
    try:
        if storage_backend() == "s3":
            from apowerb.storage.s3 import list_files_in_s3

            keys = list_files_in_s3(prefix=prefix)
        else:
            keys = _local_list(prefix)
    except Exception as exc:
        logger.error("[BI Storage] Failed to list keys for %s: %s", prefix, exc)
        return []

    results: list[dict[str, Any]] = []
    for key in keys:
        fname = key.rsplit("/", 1)[-1]
        file_id, ext = os.path.splitext(fname)
        results.append(
            {
                "file_id": file_id,
                "filename": fname,
                "organization_id": org,
                "project_id": project,
                "key": key,
                "extension": ext,
            }
        )
    return results
