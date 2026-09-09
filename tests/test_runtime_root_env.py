"""Le nom de la variable qui déplace la racine runtime.

``test_runtime_paths_wiring`` force ``settings.runtime_root`` directement : il
prouve que les chemins suivent le réglage, jamais sous quel NOM ce réglage se
pose. C'est par ce trou qu'une docstring a pu annoncer
``TH2AGENT_RUNTIME_ROOT`` -- que rien ne lit -- jusqu'au 08/09/26, et qu'un
déploiement Kubernetes a failli monter son volume derrière une variable
inerte : les fichiers importés seraient repartis avec le pod, sans la moindre
erreur.

``Settings`` n'a pas d'``env_prefix`` : le champ ``runtime_root`` se lit donc
dans ``RUNTIME_ROOT``. Ce test l'affirme par le comportement, et garde la
contre-preuve -- l'ancien nom ne fait rien.
"""

from __future__ import annotations

import pytest

from apowerb.configs import paths
from apowerb.configs.settings import Settings


@pytest.fixture
def lecture_fraiche(monkeypatch):
    """``paths`` relit l'environnement à chaque appel, le temps du test.

    ⚠️ Surtout pas ``get_settings.cache_clear()`` : le cache tient l'instance
    que d'autres suites ont déjà configurée, et la vider les casse à distance.
    Mesuré le 08/09/26 -- ``test_s3_artifact_service`` perdait son
    ``s3_bucket_name`` et comparait ``s3:///...`` à ``s3://test-bucket/...``,
    à des centaines de lignes de là. Le remplacement reste local au module
    ``paths`` et ``monkeypatch`` le défait.
    """
    monkeypatch.setattr(paths, "get_settings", lambda: Settings())


def test_runtime_root_env_var(lecture_fraiche, monkeypatch, tmp_path):
    monkeypatch.setenv("RUNTIME_ROOT", str(tmp_path))
    assert paths.runtime_root() == tmp_path
    assert paths.bi_store_dir() == tmp_path / "bi_store"
    assert paths.uploads_dir() == tmp_path / "uploads"
    assert paths.artifacts_store_dir() == tmp_path / "artifacts_store"


def test_l_ancien_nom_ne_fait_rien(lecture_fraiche, monkeypatch, tmp_path):
    """Contre-preuve : c'est ce que la docstring promettait, et il est inerte."""
    monkeypatch.delenv("RUNTIME_ROOT", raising=False)
    monkeypatch.setenv("TH2AGENT_RUNTIME_ROOT", str(tmp_path))
    assert paths.runtime_root() != tmp_path


def test_un_chemin_absolu_ignore_la_racine(lecture_fraiche, monkeypatch, tmp_path):
    """Un chemin absolu est pris tel quel -- c'est ce qui permet de sortir un
    seul répertoire du volume commun."""
    ailleurs = tmp_path / "ailleurs"
    monkeypatch.setenv("RUNTIME_ROOT", str(tmp_path))
    monkeypatch.setenv("BI_STORE_DIR", str(ailleurs))
    assert paths.bi_store_dir() == ailleurs
    assert paths.uploads_dir() == tmp_path / "uploads"


def test_le_champ_existe_sous_ce_nom():
    """Si le champ était renommé, les trois tests ci-dessus passeraient encore
    en silence -- ils compareraient un défaut à un défaut."""
    assert "runtime_root" in Settings.model_fields
