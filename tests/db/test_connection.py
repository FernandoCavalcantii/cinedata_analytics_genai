"""Barreiras de leitura, timeout, truncamento e abertura imutável do SQLite."""

import pytest

from cinedata.db import DatabaseError, QueryTimeoutError, ReadOnlyDatabase


def test_select_e_leitura_imutavel(db: ReadOnlyDatabase) -> None:
    assert "mode=ro" in db._uri
    assert "immutable=1" in db._uri
    assert db.ping() is True
    result = db.execute(
        "SELECT m.titulo FROM dim_movies m "
        "JOIN fact_movies_performance f ON m.sk_movie_id = f.sk_movie_id "
        "WHERE f.receita_brl > 0 ORDER BY f.receita_brl DESC LIMIT 1"
    )
    assert result.rows[0][0] == "Avatar: The Way Of Water"
    assert result.truncated is False


def test_trunca_sem_reescrever_o_sql(db: ReadOnlyDatabase) -> None:
    result = db.execute("SELECT titulo FROM dim_movies", max_rows=2)
    assert result.row_count == 2
    assert result.truncated is True


def test_timeout_interrompe_consulta_pesada(db: ReadOnlyDatabase) -> None:
    limited = ReadOnlyDatabase(db.path, timeout_seconds=0.4, max_rows=10)
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
def test_barreiras_recusam_acesso_indevido(db: ReadOnlyDatabase, sql: str) -> None:
    with pytest.raises(DatabaseError):
        db.execute(sql)
