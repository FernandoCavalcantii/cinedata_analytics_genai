"""Terminal do agente. A mesma resposta que a API vai servir na fase seguinte."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from cinedata.agent.service import RespostaServico, ServicoAgente
from cinedata.config import Settings, get_settings
from cinedata.db.connection import ReadOnlyDatabase

SAIR = {"sair", "exit", "quit"}
INSTRUCOES = {"instrucoes", "instruções", "ajuda", "help", "?"}


def imprimir_resposta(resposta: RespostaServico, console: Console) -> None:
    console.print(Panel(resposta.resposta, title=resposta.status))
    if resposta.explicacao:
        console.print(resposta.explicacao)
    if resposta.sql:
        console.print(Panel(resposta.sql, title="SQL"))
    else:
        console.print("[dim]Sem SQL[/]")
    dados = resposta.dados
    if dados is not None and dados.colunas:
        tabela = Table(show_lines=False)
        for coluna in dados.colunas:
            tabela.add_column(coluna)
        for linha in dados.linhas:
            tabela.add_row(*["" if valor is None else str(valor) for valor in linha])
        console.print(tabela)
        if dados.truncado:
            console.print("[dim]Resultado truncado pelo teto de linhas.[/]")
    cache = "sim" if resposta.metadados.cache else "não"
    console.print(
        f"[dim]modelo: {resposta.metadados.modelo} | "
        f"requisições: {resposta.metadados.requisicoes} | "
        f"tempo: {resposta.metadados.tempo_ms:.0f} ms | "
        f"cache: {cache} | "
        f"conversa: {resposta.conversa_id}[/]"
    )


def descrever_modelos(settings: Settings) -> str:
    return f"Gemini ({settings.gemini_model}). Se falhar, OpenRouter."


def imprimir_boas_vindas(settings: Settings, console: Console) -> None:
    console.print("CineData. Pergunte em português sobre o catálogo de filmes.")
    console.print(f"Modelos: {descrever_modelos(settings)}")
    console.print("Comandos: [bold]instrucoes[/], [bold]limpar[/], [bold]csv[/], [bold]sair[/].")


def imprimir_instrucoes(settings: Settings, console: Console) -> None:
    console.print(
        "\n".join(
            [
                "Escreva a pergunta e pressione Enter. Exemplo: qual os 3 filmes com maior lucro em dólares?",
                "",
                f"A pergunta vai primeiro para o {descrever_modelos(settings)}",
                "",
                "Comandos (escreva só o comando e pressione Enter):",
                "",
                "  instrucoes",
                "    Mostra este texto. ajuda, help e ? fazem o mesmo.",
                "",
                "  limpar",
                "    Apaga as respostas guardadas. A mesma pergunta volta a consultar o modelo.",
                "",
                "  csv",
                "    Grava a última tabela em resultado.csv, na pasta de onde você iniciou o comando.",
                "",
                "  sair",
                "    Encerra. As perguntas anteriores desta sessão não ficam guardadas para a próxima.",
            ]
        )
    )


def exportar_csv(resposta: RespostaServico, destino: Path) -> Path:
    if resposta.dados is None or not resposta.dados.colunas:
        raise ValueError("Não há tabela para exportar.")
    import csv

    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.writer(arquivo)
        escritor.writerow(resposta.dados.colunas)
        escritor.writerows(resposta.dados.linhas)
    return destino


def loop(servico: ServicoAgente, console: Console, conversa_id: str | None = None) -> None:
    imprimir_boas_vindas(servico.settings, console)
    ultima: RespostaServico | None = None
    # Um único loop: o cliente HTTP do roteador fica preso nele. asyncio.run() fecharia o loop a cada pergunta.
    event_loop = asyncio.new_event_loop()
    try:
        _loop(servico, console, conversa_id, ultima, event_loop)
    finally:
        event_loop.close()


def _loop(
    servico: ServicoAgente,
    console: Console,
    conversa_id: str | None,
    ultima: RespostaServico | None,
    event_loop: asyncio.AbstractEventLoop,
) -> None:
    while True:
        linha = console.input("[bold]Pergunta[/]: ").strip()
        if not linha:
            continue
        comando = linha.lower()
        if comando in SAIR:
            return
        if comando in INSTRUCOES:
            imprimir_instrucoes(servico.settings, console)
            continue
        if comando == "limpar":
            servico.limpar_cache()
            console.print("Cache limpo.")
            continue
        if comando == "csv":
            if ultima is None:
                console.print("Ainda não há resultado para exportar.")
                continue
            try:
                caminho = exportar_csv(ultima, Path("resultado.csv"))
            except ValueError as exc:
                console.print(str(exc))
                continue
            console.print(f"CSV salvo em {caminho.resolve()}")
            continue
        ultima = event_loop.run_until_complete(servico.perguntar(linha, conversa_id))
        conversa_id = ultima.conversa_id
        imprimir_resposta(ultima, console)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="cinedata", description="Pergunte ao catálogo de filmes da CineData.")
    parser.add_argument("--limpar-cache", action="store_true", help="Apaga .cache/respostas.json e sai.")
    parser.add_argument("--conversa", default=None, help="Identificador para continuar uma conversa nesta sessão.")
    args = parser.parse_args(argv)

    settings = get_settings()
    db = ReadOnlyDatabase(
        settings.resolve_db_path(),
        timeout_seconds=settings.sql_timeout_seconds,
        max_rows=settings.sql_max_rows,
    )
    servico = ServicoAgente(settings, db)
    console = Console()
    if args.limpar_cache:
        servico.limpar_cache()
        console.print("Cache limpo.")
        return
    try:
        loop(servico, console, args.conversa)
    except (KeyboardInterrupt, EOFError):
        console.print()
        sys.exit(0)
