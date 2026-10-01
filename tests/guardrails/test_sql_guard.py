"""Allowlist de AST: um SELECT ou UNION passa; o resto volta com mensagem em português."""

import pytest

from cinedata.guardrails import UnsafeSQLError, validate_sql


def test_select_e_union_passam() -> None:
    select = validate_sql("SELECT titulo FROM dim_movies WHERE titulo IS NOT NULL")
    assert select.tables == ("dim_movies",)

    union = validate_sql(
        "SELECT titulo FROM dim_movies UNION SELECT nome_genero FROM dim_genres"
    )
    assert set(union.tables) == {"dim_movies", "dim_genres"}


def test_cte_nao_conta_como_tabela_desconhecida() -> None:
    validated = validate_sql(
        "WITH filmes AS (SELECT titulo FROM dim_movies) SELECT titulo FROM filmes"
    )
    assert validated.tables == ("dim_movies",)


@pytest.mark.parametrize(
    ("sql", "trecho"),
    [
        ("SELECT titulo FROM dim_movies; DROP TABLE dim_movies", "exatamente UM"),
        ("DROP TABLE dim_movies", "permitidas"),
        ("PRAGMA table_info(dim_movies)", "permitidas"),
        ("ATTACH DATABASE ':memory:' AS outro", "permitidas"),
        ("SELECT * FROM tabela_que_nao_existe", "não permitida"),
        ("SELECT load_extension('x')", "Função proibida"),
        ("   ", "vazia"),
    ],
)
def test_rejeita_com_mensagem_em_portugues(sql: str, trecho: str) -> None:
    with pytest.raises(UnsafeSQLError, match=trecho):
        validate_sql(sql)
