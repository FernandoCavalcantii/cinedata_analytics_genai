"""Agente Text-to-SQL: o modelo chama `executar_consulta_sql`, vê as linhas e pode consultar de novo.

O SQL não sai na resposta estruturada. Ele fica na última chamada bem-sucedida da ferramenta,
para o serviço da fase seguinte não precisar executar de novo. ADR 013.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.models import Model
from pydantic_ai.usage import UsageLimits

from cinedata.agent.models import build_router
from cinedata.agent.retriever import InformationRetriever, RetrievalContext
from cinedata.config import Settings
from cinedata.db.connection import DatabaseError, QueryResult, ReadOnlyDatabase
from cinedata.guardrails.sql_guard import UnsafeSQLError, validate_sql

EXEMPLOS_PROMPT = """\
Pergunta: Quantos filmes estão com status Lançado?
SQL: SELECT COUNT(*) AS quantidade FROM dim_movies WHERE status_filme = 'Lançado';

Pergunta: Qual a duração em minutos do filme cujo título é exatamente 'Toy Story'?
SQL: SELECT titulo, duracao_minutos FROM dim_movies WHERE titulo = 'Toy Story' LIMIT 5;
"""


class Visualizacao(BaseModel):
    """Sugestão de gráfico para um frontend futuro. O modelo preenche depois de ver as linhas."""

    tipo: Literal["tabela", "barra", "linha", "nenhum"] = "tabela"
    eixos: list[str] = Field(default_factory=list)


class RespostaDoModelo(BaseModel):
    """Texto final. Não carrega o SQL: ele vem da ferramenta."""

    resposta: str
    explicacao: str
    visualizacao: Visualizacao = Field(default_factory=Visualizacao)


@dataclass
class ConsultaExecutada:
    sql: str
    result: QueryResult


@dataclass
class TurnoAnterior:
    pergunta: str
    sql: str | None
    resposta: str


@dataclass
class AgentDeps:
    db: ReadOnlyDatabase
    question: str
    context: RetrievalContext
    hoje: date
    historico: list[TurnoAnterior] = field(default_factory=list)
    tentativas: int = 0
    consultas: list[ConsultaExecutada] = field(default_factory=list)


@dataclass
class ResultadoAgente:
    status: Literal["ok", "fora_do_escopo", "erro"]
    resposta: str
    explicacao: str
    visualizacao: Visualizacao
    sql: str | None
    dados: QueryResult | None
    requisicoes: int
    modelo: str


def _historico_prompt(turnos: list[TurnoAnterior]) -> str:
    if not turnos:
        return ""
    blocos = []
    for indice, turno in enumerate(turnos, start=1):
        sql = turno.sql or "(sem SQL)"
        blocos.append(f"{indice}. Pergunta: {turno.pergunta}\n   SQL: {sql}\n   Resposta: {turno.resposta}")
    return (
        "Conversa até aqui. Use isto quando a pergunta for continuação, como 'e o segundo colocado?'.\n"
        + "\n".join(blocos)
        + "\n\n"
    )


def render_prompt(deps: AgentDeps) -> str:
    return f"""\
Você consulta o catálogo de filmes da CineData Analytics. O banco é SQLite, somente leitura.
Hoje é {deps.hoje.isoformat()}.

{_historico_prompt(deps.historico)}
Para qualquer pergunta sobre os filmes, chame a ferramenta executar_consulta_sql.
Leia as linhas que ela devolver. Se vierem vazias, se as colunas não forem as da pergunta
ou se os valores parecerem implausíveis, chame a ferramenta de novo com outro SQL.
Se as linhas respondem à pergunta, escreva a resposta final com esses números, sem inventar outros.
A resposta final tem três campos: resposta (texto para quem não lê SQL), explicacao
(a regra de negócio que você aplicou) e visualizacao (tipo de gráfico e eixos).

Se a pergunta não for sobre o catálogo (piada, escrita, apagar dados, outro assunto),
não chame a ferramenta. Diga na resposta que você só consulta o catálogo.

Schema das tabelas relevantes:
{deps.context.schema_prompt()}

Regras de negócio:
{deps.context.rules_prompt()}

Valores identificados na pergunta:
{deps.context.hints_prompt()}

Exemplos de pergunta e SQL. Não são as perguntas que serão avaliadas; use só como formato.
{EXEMPLOS_PROMPT}
"""


def formatar_linhas(result: QueryResult) -> str:
    """Texto que volta ao modelo: contagem, aviso e uma amostra das linhas."""

    cabecalho = (
        f"Linhas devolvidas: {result.row_count}. "
        f"Truncado pelo teto de linhas: {'sim' if result.truncated else 'não'}."
    )
    if result.row_count == 0:
        aviso = (
            "Nenhuma linha. Isso pode ser um filtro errado. "
            "Se a pergunta pede dados que deveriam existir, chame executar_consulta_sql de novo. "
            "Se a ausência for a resposta certa, escreva a resposta final."
        )
    else:
        aviso = (
            "Se as colunas ou os valores não respondem à pergunta, chame executar_consulta_sql de novo. "
            "Se respondem, escreva a resposta final com estes números, sem inventar outros."
        )
    return f"{cabecalho}\n{aviso}\n\n{result.preview_markdown(max_rows=30)}"


def build_sql_agent(settings: Settings) -> Agent[AgentDeps, RespostaDoModelo]:
    agent: Agent[AgentDeps, RespostaDoModelo] = Agent(
        None,
        deps_type=AgentDeps,
        output_type=RespostaDoModelo,
        retries=settings.max_sql_retries,
        defer_model_check=True,
        name="cinedata-sql",
    )

    @agent.instructions
    def instrucoes(ctx: RunContext[AgentDeps]) -> str:
        return render_prompt(ctx.deps)

    @agent.tool(retries=settings.max_sql_retries)
    def executar_consulta_sql(ctx: RunContext[AgentDeps], sql: str) -> str:
        """Executa um único SELECT somente leitura no catálogo e devolve as linhas.

        Chame de novo se o resultado vier vazio, se as colunas não corresponderem à pergunta
        ou se os valores parecerem implausíveis. Não use para pedidos que não sejam sobre o catálogo.
        """

        ctx.deps.tentativas += 1
        try:
            validated = validate_sql(sql)
        except UnsafeSQLError as exc:
            raise ModelRetry(str(exc)) from exc
        try:
            result = ctx.deps.db.execute(validated.sql)
        except DatabaseError as exc:
            raise ModelRetry(str(exc)) from exc
        ctx.deps.consultas.append(ConsultaExecutada(sql=validated.sql, result=result))
        return formatar_linhas(result)

    return agent


async def responder(
    question: str,
    *,
    db: ReadOnlyDatabase,
    settings: Settings,
    model: Model | None = None,
    hoje: date | None = None,
    historico: list[TurnoAnterior] | None = None,
) -> ResultadoAgente:
    """Roda uma pergunta. Sem modelo explícito, usa o roteador do `.env`."""

    chosen = model if model is not None else build_router(settings).model
    deps = AgentDeps(
        db=db,
        question=question,
        context=InformationRetriever(db).retrieve(question),
        hoje=hoje or date.today(),
        historico=list(historico or []),
    )
    result = await build_sql_agent(settings).run(
        question,
        deps=deps,
        model=chosen,
        usage_limits=UsageLimits(request_limit=settings.max_llm_requests),
    )
    output = result.output
    modelo = result.response.model_name or "desconhecido"
    ultima = deps.consultas[-1] if deps.consultas else None
    if ultima is None:
        status: Literal["fora_do_escopo", "erro"] = "erro" if deps.tentativas else "fora_do_escopo"
        return ResultadoAgente(
            status=status,
            resposta=output.resposta,
            explicacao=output.explicacao,
            visualizacao=output.visualizacao,
            sql=None,
            dados=None,
            requisicoes=result.usage.requests,
            modelo=modelo,
        )
    return ResultadoAgente(
        status="ok",
        resposta=output.resposta,
        explicacao=output.explicacao,
        visualizacao=output.visualizacao,
        sql=ultima.sql,
        dados=ultima.result,
        requisicoes=result.usage.requests,
        modelo=modelo,
    )
