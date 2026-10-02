"""Roda as 14 perguntas uma vez e grava o relatório. Não entra no pytest."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import get_tracer_provider, set_tracer_provider
from pydantic_evals import Dataset
from pydantic_evals.dataset import increment_eval_metric
from pydantic_evals.evaluators import MaxModelRequests

from cinedata.agent.service import ServicoAgente
from cinedata.config import get_settings
from cinedata.db.connection import ReadOnlyDatabase
from evals.avaliadores import MetadadosPergunta, ResultadoEquivalente, SaidaEval, banco_da_avaliacao

RAIZ = Path(__file__).resolve().parent
ARQUIVO_PERGUNTAS = RAIZ / "perguntas_obrigatorias.yaml"
ARQUIVO_RELATORIO = RAIZ / "relatorio.md"
ARQUIVO_RESULTADOS = RAIZ / "resultados.json"


def carregar_dataset(teto_requisicoes: int) -> Dataset[str, SaidaEval, MetadadosPergunta]:
    dataset = Dataset[str, SaidaEval, MetadadosPergunta].from_file(
        ARQUIVO_PERGUNTAS,
        custom_evaluator_types=[ResultadoEquivalente],
    )
    dataset.evaluators = [ResultadoEquivalente(), MaxModelRequests(max_requests=teto_requisicoes)]
    return dataset


def _ligar_spans() -> None:
    """O MaxModelRequests lê o span tree. Sem um TracerProvider, ele recusa a contagem."""

    if type(get_tracer_provider()).__name__ == "ProxyTracerProvider":
        set_tracer_provider(TracerProvider())


async def rodar(destino: Path = ARQUIVO_RELATORIO, somente: list[str] | None = None) -> None:
    settings = get_settings().model_copy(update={"cache_enabled": False})
    _ligar_spans()
    banco = ReadOnlyDatabase(
        settings.resolve_db_path(),
        timeout_seconds=settings.sql_timeout_seconds,
        max_rows=settings.sql_max_rows,
    )
    servico = ServicoAgente(settings=settings, db=banco)
    servico.roteador()

    async def tarefa(pergunta: str) -> SaidaEval:
        resposta = await servico.perguntar(pergunta)
        increment_eval_metric("requests", resposta.metadados.requisicoes)
        return SaidaEval(
            status=resposta.status,
            sql=resposta.sql,
            requisicoes=resposta.metadados.requisicoes,
            modelo=resposta.metadados.modelo,
        )

    dataset = carregar_dataset(settings.max_llm_requests)
    if somente:
        nomes = set(somente)
        dataset.cases = [caso for caso in dataset.cases if caso.name in nomes]
    token = banco_da_avaliacao.set(banco)
    try:
        relatorio = await dataset.evaluate(
            tarefa,
            max_concurrency=1,
            progress=True,
        )
    finally:
        banco_da_avaliacao.reset(token)

    texto = gravar(relatorio, destino, teto=settings.max_llm_requests, substituir=somente)
    print(texto)
    print(f"Relatório gravado em {destino}")


def gravar(relatorio, destino: Path, *, teto: int, substituir: list[str] | None) -> str:
    novos = [_caso_de_relatorio(caso, teto) for caso in relatorio.cases]
    novos += [_caso_de_falha(falha) for falha in relatorio.failures]
    if substituir and ARQUIVO_RESULTADOS.is_file():
        guardados = json.loads(ARQUIVO_RESULTADOS.read_text(encoding="utf-8"))
        por_nome = {item["name"]: item for item in guardados["casos"]}
        for item in novos:
            por_nome[item["name"]] = item
        ordem = [caso.name for caso in carregar_dataset(teto).cases]
        casos = [por_nome[nome] for nome in ordem if nome in por_nome]
        requisicoes = guardados.get("requisicoes_acumuladas", 0) + sum(item["requisicoes"] for item in novos)
    else:
        casos = novos
        requisicoes = sum(item["requisicoes"] for item in casos)
    payload = {
        "data": date.today().strftime("%d/%m/%Y"),
        "teto": teto,
        "requisicoes_acumuladas": requisicoes,
        "casos": casos,
    }
    ARQUIVO_RESULTADOS.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    texto = formatar_casos(casos, requisicoes=requisicoes, quando=payload["data"])
    destino.write_text(texto, encoding="utf-8")
    return texto


def formatar_casos(casos: list[dict], *, requisicoes: int, quando: str) -> str:
    por_categoria: dict[str, list[bool]] = defaultdict(list)
    detalhes: list[str] = []
    acertos = 0
    for caso in casos:
        passou = bool(caso["passou"])
        acertos += int(passou)
        por_categoria[caso["categoria"]].append(passou)
        marca = "acertou" if passou else "errou"
        detalhes.append(
            f"### {caso['name']} — {marca}\n\n"
            f"- Categoria: {caso['categoria']}\n"
            f"- Modelo: {caso['modelo']}\n"
            f"- Requisições: {caso['requisicoes']}\n"
            f"- Teto de chamadas: {'dentro' if caso['dentro_do_teto'] else 'estourou'}\n"
            f"- Comparação: {caso['motivo']}\n"
            f"- SQL:\n\n```sql\n{caso['sql']}\n```\n"
        )
    linhas = [
        f"# Avaliação das 14 perguntas — {quando}",
        "",
        f"Acerto: {acertos} de {len(casos)}. Requisições gastas: {requisicoes}.",
        "",
    ]
    soma = sum(caso["requisicoes"] for caso in casos)
    if requisicoes != soma:
        linhas.append(
            f"A soma das perguntas abaixo é {soma}. "
            f"As outras {requisicoes - soma} são da primeira passagem das perguntas que foram repetidas."
        )
        linhas.append("")
    linhas += [
        "| Categoria | Acertos | Total |",
        "| :--- | ---: | ---: |",
    ]
    for categoria, marcas in por_categoria.items():
        linhas.append(f"| {categoria} | {sum(marcas)} | {len(marcas)} |")
    linhas.append("")
    linhas.extend(detalhes)
    return "\n".join(linhas).rstrip() + "\n"


def _caso_de_relatorio(caso, teto: int) -> dict:
    meta = caso.metadata
    saida = caso.output
    resultado = _afirmacao(caso, "ResultadoEquivalente")
    gastos = saida.requisicoes if saida is not None else 0
    return {
        "name": caso.name,
        "categoria": meta.categoria if meta is not None else "Sem categoria",
        "passou": bool(resultado is not None and resultado.value),
        "modelo": saida.modelo if saida is not None else "",
        "requisicoes": gastos,
        "dentro_do_teto": gastos <= teto,
        "motivo": resultado.reason if resultado is not None and resultado.reason else "",
        "sql": (saida.sql or "").strip() if saida is not None else "",
    }


def _caso_de_falha(falha) -> dict:
    meta = falha.metadata
    return {
        "name": falha.name,
        "categoria": meta.categoria if meta is not None else "Sem categoria",
        "passou": False,
        "modelo": "",
        "requisicoes": 0,
        "dentro_do_teto": False,
        "motivo": falha.error_message,
        "sql": "",
    }


def _afirmacao(caso, nome: str):
    for afirmacao in caso.assertions.values():
        if afirmacao.name == nome:
            return afirmacao
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Avalia as 14 perguntas do edital contra o banco.")
    parser.add_argument("--relatorio", type=Path, default=ARQUIVO_RELATORIO)
    parser.add_argument("--casos", nargs="*", default=None, help="Repete só estes nomes e mantém o restante do relatório.")
    args = parser.parse_args()
    asyncio.run(rodar(args.relatorio, args.casos or None))


if __name__ == "__main__":
    main()
