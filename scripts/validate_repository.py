#!/usr/bin/env python3
"""Validate repository documentation and SDD packages without dependencies."""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
SDD_ROOT = ROOT / "docs" / "sdd"
VALID_STATUSES = {"draft", "approved", "in-progress", "validation", "done"}
PACKAGE_PATTERN = re.compile(r"^\d{4}-[a-z0-9]+(?:-[a-z0-9]+)*$")
LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
REQUIRED_REPOSITORY_FILES = (
    ".gitignore",
    "README.md",
    "CONTRIBUTING.md",
    "AGENTS.md",
    "docs/architecture.md",
    "docs/adr/README.md",
    "docs/sdd/README.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/workflows/quality.yml",
)
STANDARD_SECTIONS = {
    "spec.md": (
        "Problema",
        "Objetivos",
        "Alcance",
        "Requisitos",
        "Restricciones",
        "Criterios de aceptación",
    ),
    "plan.md": (
        "Diseño",
        "Contratos",
        "Flujo de datos",
        "Fallos y recuperación",
        "Pruebas",
        "Despliegue",
    ),
    "tasks.md": ("Tareas",),
    "validation.md": (
        "Resultado",
        "Evidencia",
        "Criterios de aceptación",
        "Desviaciones",
    ),
}
COMPACT_SECTIONS = (
    "Problema",
    "Cambio",
    "Criterios de aceptación",
    "Tareas",
    "Validación",
)
METADATA_FIELDS = (
    "id",
    "title",
    "status",
    "owner",
    "created",
    "updated",
    "approval",
)


def parse_metadata(path: Path) -> tuple[dict[str, str], list[str]]:
    """Parse the deliberately small key/value front matter format."""
    errors: list[str] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        return {}, [f"{path}: debe comenzar con front matter delimitado por ---"]

    try:
        end = lines.index("---", 1)
    except ValueError:
        return {}, [f"{path}: el front matter no tiene delimitador de cierre ---"]

    metadata: dict[str, str] = {}
    for line_number, line in enumerate(lines[1:end], start=2):
        if ":" not in line:
            errors.append(f"{path}:{line_number}: metadata inválida; use clave: valor")
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip()
    return metadata, errors


def validate_sections(path: Path, required: tuple[str, ...]) -> list[str]:
    text = path.read_text(encoding="utf-8")
    headings = {
        match.group(1).strip()
        for match in re.finditer(r"^##\s+(.+?)\s*$", text, flags=re.MULTILINE)
    }
    return [
        f"{path}: falta la sección '## {section}'"
        for section in required
        if section not in headings
    ]


def validate_package(package: Path) -> list[str]:
    errors: list[str] = []
    if not PACKAGE_PATTERN.fullmatch(package.name):
        errors.append(
            f"{package}: el directorio debe usar cuatro dígitos y un slug kebab-case"
        )

    compact = package / "compact.md"
    if compact.exists():
        markdown_files = sorted(path.name for path in package.glob("*.md"))
        if markdown_files != ["compact.md"]:
            errors.append(
                f"{package}: un paquete compacto sólo puede contener compact.md"
            )
        metadata_path = compact
        errors.extend(validate_sections(compact, COMPACT_SECTIONS))
    else:
        for filename, sections in STANDARD_SECTIONS.items():
            path = package / filename
            if not path.exists():
                errors.append(f"{package}: falta el artefacto obligatorio {filename}")
                continue
            errors.extend(validate_sections(path, sections))
        metadata_path = package / "spec.md"

    if not metadata_path.exists():
        return errors

    metadata, metadata_errors = parse_metadata(metadata_path)
    errors.extend(metadata_errors)
    for field in METADATA_FIELDS:
        if not metadata.get(field):
            errors.append(f"{metadata_path}: falta metadata obligatoria '{field}'")
    if metadata.get("id") != package.name:
        errors.append(
            f"{metadata_path}: id '{metadata.get('id', '')}' no coincide con "
            f"{package.name}"
        )
    if metadata.get("status") not in VALID_STATUSES:
        allowed = ", ".join(sorted(VALID_STATUSES))
        errors.append(
            f"{metadata_path}: status inválido; valores permitidos: {allowed}"
        )
    for field in ("created", "updated"):
        value = metadata.get(field, "")
        if value and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            errors.append(f"{metadata_path}: '{field}' debe usar YYYY-MM-DD")
    if metadata.get("status") != "draft" and metadata.get("approval") == "pending":
        errors.append(
            f"{metadata_path}: una iniciativa fuera de draft requiere aprobación"
        )
    if metadata.get("status") == "done":
        completion_path = compact if compact.exists() else package / "tasks.md"
        if completion_path.exists() and "- [ ]" in completion_path.read_text(
            encoding="utf-8"
        ):
            errors.append(
                f"{completion_path}: una iniciativa done no puede tener tareas "
                "pendientes"
            )
    return errors


def validate_sdd(root: Path) -> list[str]:
    if not root.exists():
        return [f"{root}: no existe el directorio SDD"]
    packages = [
        path for path in root.iterdir() if path.is_dir() and path.name != "templates"
    ]
    if not packages:
        return [f"{root}: debe contener al menos una iniciativa SDD"]
    errors: list[str] = []
    for package in sorted(packages):
        errors.extend(validate_package(package))
    return errors


def validate_repository_files() -> list[str]:
    return [
        f"{ROOT / relative}: falta el archivo obligatorio"
        for relative in REQUIRED_REPOSITORY_FILES
        if not (ROOT / relative).is_file()
    ]


def validate_markdown() -> list[str]:
    errors: list[str] = []
    for path in sorted(ROOT.rglob("*.md")):
        if ".git" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if line.endswith((" ", "\t")):
                errors.append(f"{path}:{line_number}: espacio en blanco al final")

        for raw_target in LINK_PATTERN.findall(text):
            target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
            if not target or target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            relative_target = unquote(target.split("#", 1)[0])
            resolved = (path.parent / relative_target).resolve()
            try:
                resolved.relative_to(ROOT.resolve())
            except ValueError:
                errors.append(f"{path}: enlace local sale del repositorio: {target}")
                continue
            if not resolved.exists():
                errors.append(f"{path}: enlace local inexistente: {target}")
    return errors


def run_self_test() -> list[str]:
    with tempfile.TemporaryDirectory(prefix="ndevscrap-sdd-") as temporary:
        root = Path(temporary)
        package = root / "9999-incomplete-example"
        package.mkdir()
        (package / "spec.md").write_text(
            "---\nid: 9999-incomplete-example\nstatus: draft\n---\n\n# Incompleto\n",
            encoding="utf-8",
        )
        observed = validate_sdd(root)
        expected_fragment = "falta el artefacto obligatorio plan.md"
        if not any(expected_fragment in error for error in observed):
            return ["self-test: el validador no rechazó un paquete SDD incompleto"]
        print(
            "Self-test OK: un paquete incompleto fue rechazado con mensajes "
            "accionables."
        )
        return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="comprueba que un paquete SDD incompleto sea rechazado",
    )
    args = parser.parse_args()

    if args.self_test:
        errors = run_self_test()
    else:
        errors = (
            validate_repository_files() + validate_markdown() + validate_sdd(SDD_ROOT)
        )

    if errors:
        print("Validación fallida:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    if not args.self_test:
        print("Validación OK: documentación, enlaces y paquetes SDD son válidos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
