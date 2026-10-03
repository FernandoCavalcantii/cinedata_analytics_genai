"""Barreiras de leitura, timeout, truncamento e abertura imutável do SQLite."""

import sqlite3
from pathlib import Path

import pytest

from cinedata.db import DatabaseError, QueryTimeoutError, ReadOnlyDatabase
from cinedata.db.connection import sqlite_readonly_uri


def test_uri_preserva_o_disco_do_windows() -> None:
    uri = sqlite_readonly_uri(Path("C:/dados/cinerocket.db"))
    assert uri.startswith("file:C:/dados/cinerocket.db?")
    assert "mode=ro" in uri
    assert "immutable=1" in uri


def test_select_e_leitura_imutavel(banco_minimo: ReadOnlyDatabase) -> None:
    assert "mode=ro" in banco_minimo._uri
    assert "immutable=1" in banco_minimo._uri
    assert banco_minimo.ping() is True
    result = banco_minimo.execute("SELECT titulo FROM dim_movies ORDER BY sk_movie_id LIMIT 1")
    assert result.rows[0][0] == "Um"
    assert result.truncated is False


def test_maior_receita_no_banco_real_continua_avatar(db: ReadOnlyDatabase) -> None:
    result = db.execute(
        "SELECT m.titulo FROM dim_movies m "
        "JOIN fact_movies_performance f ON m.sk_movie_id = f.sk_movie_id "
        "WHERE f.receita_brl > 0 ORDER BY f.receita_brl DESC LIMIT 1"
    )
    assert result.rows[0][0] == "Avatar: The Way Of Water"


def test_trunca_sem_reescrever_o_sql(banco_minimo: ReadOnlyDatabase) -> None:
    result = banco_minimo.execute("SELECT titulo FROM dim_movies", max_rows=2)
    assert result.row_count == 2
    assert result.truncated is True
    assert result.sql == "SELECT titulo FROM dim_movies"


def test_timeout_interrompe_consulta_pesada(tmp_path: Path) -> None:
    path = tmp_path / "pesado.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE bridge_movie_person (sk_movie_id INTEGER, sk_person_id INTEGER)")
    connection.executemany(
        "INSERT INTO bridge_movie_person VALUES (?, ?)",
        [(i, i) for i in range(8_000)],
    )
    connection.commit()
    connection.close()
    limited = ReadOnlyDatabase(path, timeout_seconds=0.4, max_rows=10)
    with pytest.raises(QueryTimeoutError, match="0.4s"):
        limited.execute("SELECT COUNT(*) FROM bridge_movie_person a, bridge_movie_person b")


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT name FROM sqlite_master",
        "PRAGMA table_info(dim_movies)",
        "INSERT INTO dim_movies (titulo) VALUES ('x')",
        "DELETE FROM dim_movies",
        "ATTACH DATABASE ':memory:' AS outro",
        "SELECT load_extension('x')",
        "SELECT * FROM alembic_version",
    ],
)
def test_barreiras_recusam_acesso_indevido(banco_minimo: ReadOnlyDatabase, sql: str) -> None:
    with pytest.raises(DatabaseError):
        banco_minimo.execute(sql)
