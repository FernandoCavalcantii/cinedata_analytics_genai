"""Schema Selector determinístico: as 14 perguntas do edital e o caso Warner Bros."""

import pytest

from cinedata.agent.retriever import InformationRetriever, _entity_candidates
from cinedata.db import ReadOnlyDatabase
from cinedata.db.catalog import TABLES

DIM = "dim_movies"
FACT = "fact_movies_performance"
GENRES = {"dim_genres", "bridge_movie_genre"}
PEOPLE = {"dim_people", "bridge_movie_person"}
COMPANIES = {"dim_companies", "bridge_movie_company"}
REVIEWS = {"dim_reviews"}

PERGUNTAS = [
    ("Top 10 filmes com maior receita em R$", {DIM, FACT}),
    ("Lucro médio por gênero, considerando apenas filmes com receita informada", {DIM, FACT, *GENRES}),
    ("Filmes com maior margem de lucro, entre os que possuem receita e orçamento informados", {DIM, FACT}),
    ("Os 5 filmes mais populares", {DIM, FACT}),
    ("Filmes com maior divergência entre a nota TMDB e a nota IMDb", {DIM, FACT}),
    ("Nota média IMDb por ano de lançamento", {DIM, FACT}),
    ("Ator com mais participações em filmes lançados nos últimos 5 anos", {DIM, *PEOPLE}),
    ("Diretores com maior nota média (mínimo de 5 filmes)", {DIM, FACT, *PEOPLE}),
    ("Dupla ator-diretor que mais trabalhou junta", {DIM, *PEOPLE}),
    ("Quantidade de filmes por gênero", {DIM, *GENRES}),
    ("Produtora com maior lucro total", {DIM, FACT, *COMPANIES}),
    ("Gênero com maior margem de lucro média", {DIM, FACT, *GENRES}),
    ("Filmes mais avaliados pelos usuários", {DIM, *REVIEWS}),
    ("Filmes em que a nota média dos usuários mais diverge da nota IMDb", {DIM, FACT, *REVIEWS}),
]


def test_frase_inicial_nao_esconde_a_produtora() -> None:
    candidates = _entity_candidates("Filmes da Warner Bros. Pictures em 2023")
    assert "Warner Bros. Pictures" in candidates


def test_warner_em_2023_acha_a_produtora_e_o_periodo(db: ReadOnlyDatabase) -> None:
    context = InformationRetriever(db).retrieve("Filmes da Warner Bros. Pictures em 2023")
    assert "periodo" in context.concepts
    assert set(COMPANIES).issubset(context.tables)
    assert any("Warner Bros. Pictures" in hint for hint in context.hints)
    assert len(context.tables) < 10


def test_terror_vira_horror(db: ReadOnlyDatabase) -> None:
    context = InformationRetriever(db).retrieve("Quais filmes de terror tiveram maior receita?")
    assert any("Horror" in hint for hint in context.hints)
    assert set(GENRES).issubset(context.tables)


@pytest.mark.parametrize(("question", "tables"), PERGUNTAS)
def test_perguntas_do_edital(db: ReadOnlyDatabase, question: str, tables: set[str]) -> None:
    context = InformationRetriever(db).retrieve(question)
    assert set(context.tables) == tables


def test_sem_seletor_entrega_todas_as_tabelas() -> None:
    context = InformationRetriever().retrieve("Top 10 filmes com maior receita em R$", selecionar_schema=False)
    assert context.tables == [table.name for table in TABLES]
