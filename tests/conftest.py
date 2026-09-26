from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest

from ndevscrap.observability import remove_json_logging


@pytest.fixture(autouse=True)
def _reset_json_logging() -> Iterator[None]:
    """Keep the CLI's JSON handler from leaking into later tests."""
    root_level = logging.getLogger().level
    yield
    remove_json_logging()
    logging.getLogger().setLevel(root_level)
