"""A comparação de resultados não chama modelo nenhum."""

from pathlib import Path

from pydantic_evals import Dataset

from cinedata.api.schemas import PERGUNTAS_EDITAL
from evals.avaliadores import MetadadosPergunta, SaidaEval, celulas_iguais, comparar_com_referencias
from evals.executar import ARQUIVO_PERGUNTAS, carregar_dataset

GABARITO = Path(ARQUIVO_PERGUNTAS)


def test_gabarito_repete_as_14_perguntas_na_ordem_do_edital():
    dataset = Dataset[str, SaidaEval, MetadadosPergunta].from_file(GABARITO)
    assert [caso.inputs for caso in dataset.cases] == PERGUNTAS_EDITAL
    categorias = {caso.metadata.categoria for caso in dataset.cases}
    assert categorias == {
        "Bilheteria e Finanças",
        "Popularidade e Engajamento",
        "Elenco e Equipe",
        "Gêneros e Produtoras",
        "Avaliações dos Usuários",
    }
    margem = next(caso for caso in dataset.cases if caso.name == "maior_margem")
    divergencia = next(caso for caso in dataset.cases if caso.name == "divergencia_tmdb_imdb")
    assert len(margem.metadata.referencias) == 2
    assert len(divergencia.metadata.referencias) == 4


def test_numero_nulo_e_texto():
    assert celulas_iguais(10, 10.0)
    assert celulas_iguais(1.00001, 1.0)
    assert not celulas_iguais(None, 0)
    assert celulas_iguais(None, None)
    assert celulas_iguais(" Avatar ", "Avatar")


def test_ranking_rejeita_tabela_inteira_mesmo_com_as_primeiras_linhas():
    referencia = [[["Avatar", 10], ["Duna", 9]]]
    gerada = [["Avatar", 10], ["Duna", 9], ["Barbie", 1]]
    ok, motivo = comparar_com_referencias(gerada, referencia, ranking=True)
    assert not ok
    assert "3 linhas contra 2" in motivo


def test_ranking_exige_a_mesma_ordem_e_aceita_coluna_extra():
    referencia = [[["Avatar", 10], ["Duna", 9]]]
    invertida = [["Duna", 9], ["Avatar", 10]]
    com_coluna = [["Avatar", "filme", 10], ["Duna", "filme", 9]]
    assert not comparar_com_referencias(invertida, referencia, ranking=True)[0]
    assert comparar_com_referencias(com_coluna, referencia, ranking=True)[0]


def test_sem_ranking_a_ordem_nao_importa_e_a_segunda_referencia_salva():
    referencia_a = [[["Ação", 1.0], ["Drama", 2.0]]]
    referencia_b = [[["Terror", 9.0]]]
    gerada = [["Drama", 2.0], ["Ação", 1]]
    ok, motivo = comparar_com_referencias(gerada, referencia_a, ranking=False)
    assert ok
    assert "ordem" in motivo
    ok, motivo = comparar_com_referencias([["Terror", 9]], [referencia_a[0], referencia_b[0]], ranking=True)
    assert ok
    assert "referência 2" in motivo


def test_dataset_aplica_o_teto_de_chamadas():
    dataset = carregar_dataset(6)
    nomes = [type(avaliador).__name__ for avaliador in dataset.evaluators]
    assert nomes == ["ResultadoEquivalente", "MaxModelRequests"]
