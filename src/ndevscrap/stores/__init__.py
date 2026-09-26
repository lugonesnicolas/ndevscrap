"""Registry of store definitions; the composition root with the CLI."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from ..contracts import StoreDefinition
from .dia import DiaStore

StoreFactory = Callable[[Mapping[str, str]], StoreDefinition]

REGISTRY: Mapping[str, StoreFactory] = {"dia": DiaStore.from_environment}
