"""Fixtures compartilhadas. Testes que dependem do banco são pulados se o arquivo não estiver presente."""

import pytest

from cinedata.config import get_settings
from cinedata.db import ReadOnlyDatabase


@pytest.fixture(scope="session")
def db() -> ReadOnlyDatabase:
    settings = get_settings()
    path = settings.resolve_db_path()
    if not path.is_file():
        pytest.skip(f"Banco não encontrado em {path}.")
    return ReadOnlyDatabase(path, timeout_seconds=settings.sql_timeout_seconds, max_rows=settings.sql_max_rows)
