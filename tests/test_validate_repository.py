"""Tests for the repository documentation validator."""

from __future__ import annotations

import importlib.util
from pathlib import Path


VALIDATOR_PATH = Path(__file__).parents[1] / "scripts" / "validate_repository.py"
SPEC = importlib.util.spec_from_file_location("validate_repository", VALIDATOR_PATH)
assert SPEC and SPEC.loader
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


def _write_platform(root: Path) -> None:
    platform = root / "example-platform"
    versions = platform / "versions"
    versions.mkdir(parents=True)
    (platform / "README.md").write_text(
        """---
id: example-platform
status: draft
created: 2026-09-20
updated: 2026-09-20
last_verified: pending
---

# Plataforma: Example

## Estado y vigencia
## Acceso autorizado
## Capacidades
## Límites y operación
## Versiones de API
## Iniciativas SDD relacionadas
## Mantenimiento
## Fuentes
## Hallazgos pendientes
""",
        encoding="utf-8",
    )
    (versions / "v1.md").write_text(
        """---
platform: example-platform
version: v1
status: draft
created: 2026-09-20
updated: 2026-09-20
last_verified: pending
---

# API: Example v1

## Estado y vigencia
## Endpoints
## Paginación
## Errores y reintentos
## Mapeo al contrato
## Diferencias y compatibilidad
## Fuentes
## Hallazgos pendientes
""",
        encoding="utf-8",
    )


def test_validate_platforms_accepts_complete_draft_profile(tmp_path: Path) -> None:
    _write_platform(tmp_path)

    assert validator.validate_platforms(tmp_path) == []


def test_validate_platforms_reports_missing_overview(tmp_path: Path) -> None:
    platform = tmp_path / "example-platform"
    platform.mkdir()

    errors = validator.validate_platforms(tmp_path)

    assert any("falta la ficha principal README.md" in error for error in errors)
    assert any("falta el directorio versions" in error for error in errors)
