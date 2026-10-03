"""Fixtures compartilhadas. Testes que dependem do banco são pulados se o arquivo não estiver presente."""

import sqlite3
from pathlib import Path

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


@pytest.fixture
def banco_minimo(tmp_path: Path) -> ReadOnlyDatabase:
    """SQLite pequeno para as barreiras rodarem no CI, sem o arquivo de 581 MB."""

    path = tmp_path / "minimo.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE dim_movies (sk_movie_id INTEGER PRIMARY KEY, titulo TEXT)")
    connection.executemany(
        "INSERT INTO dim_movies (sk_movie_id, titulo) VALUES (?, ?)",
        [(1, "Um"), (2, "Dois"), (3, "Tres")],
    )
    connection.commit()
    connection.close()
    return ReadOnlyDatabase(path, timeout_seconds=10.0, max_rows=200)
