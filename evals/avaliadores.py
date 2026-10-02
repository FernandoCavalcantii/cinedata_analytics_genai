"""Compara o resultado do SQL gerado com uma ou mais consultas de referência.

O texto do SQL não precisa coincidir. A linha gerada pode trazer colunas a mais
e em outra ordem. Em ranking, a quantidade de linhas e a ordem têm de ser as mesmas:
um Top 10 que esqueceu o LIMIT e devolveu a tabela inteira não passa.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext

from cinedata.db.connection import DatabaseError, ReadOnlyDatabase

banco_da_avaliacao: ContextVar[ReadOnlyDatabase | None] = ContextVar("banco_da_avaliacao", default=None)

TOLERANCIA_ABSOLUTA = 1e-2
TOLERANCIA_RELATIVA = 1e-4


class SaidaEval(BaseModel):
    status: str
    sql: str | None
    requisicoes: int
    modelo: str


class MetadadosPergunta(BaseModel):
    categoria: str
    ranking: bool
    referencias: list[str]


def celulas_iguais(esquerda: Any, direita: Any) -> bool:
    if esquerda is None or direita is None:
        return esquerda is None and direita is None
    if _numero(esquerda) and _numero(direita):
        a = float(esquerda)
        b = float(direita)
        diferenca = abs(a - b)
        escala = max(abs(a), abs(b), 1.0)
        return diferenca <= TOLERANCIA_ABSOLUTA or diferenca / escala <= TOLERANCIA_RELATIVA
    return str(esquerda).strip() == str(direita).strip()


def linha_contem(gerada: list[Any], referencia: list[Any]) -> bool:
    """A linha gerada contém os valores da referência, com colunas extras permitidas."""

    def busca(indice: int, usados: set[int]) -> bool:
        if indice == len(referencia):
            return True
        for posicao, celula in enumerate(gerada):
            if posicao in usados or not celulas_iguais(referencia[indice], celula):
                continue
            usados.add(posicao)
            if busca(indice + 1, usados):
                return True
            usados.remove(posicao)
        return False

    return busca(0, set())


def tabelas_equivalentes(gerada: list[list[Any]], referencia: list[list[Any]], *, ranking: bool) -> tuple[bool, str]:
    if len(gerada) != len(referencia):
        return False, f"{len(gerada)} linhas contra {len(referencia)} da referência"
    if ranking:
        for indice, (linha_gerada, linha_referencia) in enumerate(zip(gerada, referencia), start=1):
            if not linha_contem(linha_gerada, linha_referencia):
                return False, f"a linha {indice} do ranking difere da referência"
        return True, "ranking equivalente"
    restantes = list(range(len(gerada)))

    def casa(indice: int) -> bool:
        if indice == len(referencia):
            return True
        for posicao, linha in enumerate(restantes):
            if not linha_contem(gerada[linha], referencia[indice]):
                continue
            restantes.pop(posicao)
            if casa(indice + 1):
                return True
            restantes.insert(posicao, linha)
        return False

    if casa(0):
        return True, "linhas equivalentes, sem exigir a ordem"
    return False, "as linhas diferem, mesmo sem exigir a ordem"


def comparar_com_referencias(
    gerada: list[list[Any]],
    referencias: list[list[list[Any]]],
    *,
    ranking: bool,
) -> tuple[bool, str]:
    motivos: list[str] = []
    for numero, referencia in enumerate(referencias, start=1):
        ok, motivo = tabelas_equivalentes(gerada, referencia, ranking=ranking)
        if ok:
            if len(referencias) == 1:
                return True, motivo
            return True, f"coincidiu com a referência {numero}"
        motivos.append(f"referência {numero}: {motivo}")
    return False, "; ".join(motivos)


def executar_referencias(banco: ReadOnlyDatabase, sqls: list[str]) -> list[list[list[Any]]]:
    return [banco.execute(sql).rows for sql in sqls]


@dataclass
class ResultadoEquivalente(Evaluator[str, SaidaEval, MetadadosPergunta]):
    """Executa o SQL gerado e as referências no mesmo banco e compara as tabelas."""

    def evaluate(self, ctx: EvaluatorContext[str, SaidaEval, MetadadosPergunta]) -> EvaluationReason:
        saida = ctx.output
        meta = ctx.metadata
        if meta is None:
            return EvaluationReason(value=False, reason="A pergunta não tem gabarito.")
        if saida.status != "ok" or not saida.sql:
            return EvaluationReason(value=False, reason=f"O agente respondeu {saida.status} sem SQL executado.")
        banco = banco_da_avaliacao.get()
        if banco is None:
            return EvaluationReason(value=False, reason="O banco da avaliação não está disponível.")
        try:
            gerada = banco.execute(saida.sql).rows
            referencias = executar_referencias(banco, meta.referencias)
        except DatabaseError as exc:
            return EvaluationReason(value=False, reason=str(exc))
        ok, motivo = comparar_com_referencias(gerada, referencias, ranking=meta.ranking)
        return EvaluationReason(value=ok, reason=motivo)


def _numero(valor: Any) -> bool:
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)
