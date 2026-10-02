"""Ciclo da ferramenta com FunctionModel: o banco roda de verdade, o modelo não."""

import asyncio
from datetime import date

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, RetryPromptPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from cinedata.agent.sql_agent import EXEMPLOS_PROMPT, AgentDeps, render_prompt, responder
from cinedata.config import Settings
from cinedata.db import ReadOnlyDatabase
from cinedata.db.catalog import BUSINESS_RULES
from cinedata.agent.retriever import InformationRetriever

HOJE = date(2026, 10, 1)
PERGUNTA_RECEITA = "Top 10 filmes com maior receita em R$"
SQL_RECEITA = """
SELECT m.titulo, f.receita_brl
FROM dim_movies m
JOIN fact_movies_performance f ON m.sk_movie_id = f.sk_movie_id
WHERE f.receita_brl > 0
ORDER BY f.receita_brl DESC
LIMIT 1
"""
SQL_ERRADO = "SELECT titulo FROM dim_movies ORDER BY titulo ASC LIMIT 1"
SQL_PROIBIDO = "DROP TABLE dim_movies"

FRASES_DAS_14 = (
    "Top 10 filmes",
    "Lucro médio por gênero",
    "margem de lucro",
    "mais populares",
    "nota TMDB",
    "últimos 5 anos",
    "Dupla ator",
)


class BancoContado(ReadOnlyDatabase):
    """Conta só o SQL da ferramenta. O retriever consulta o banco com parâmetros (`?`)."""

    def __init__(self, inner: ReadOnlyDatabase) -> None:
        self._inner = inner
        self.sqls_da_ferramenta: list[str] = []

    def execute(self, sql, params=(), *, max_rows=None):  # type: ignore[override]
        if "?" not in sql:
            self.sqls_da_ferramenta.append(sql)
        return self._inner.execute(sql, params, max_rows=max_rows)


def _settings() -> Settings:
    return Settings(
        openrouter_api_key="",
        openrouter_models=[],
        gemini_api_keys=[],
        openai_api_keys=[],
        openai_api_key="",
        max_sql_retries=2,
        max_llm_requests=6,
    )


def _ultimo_retorno(messages: list[ModelMessage]) -> str | None:
    for message in reversed(messages):
        parts = getattr(message, "parts", None)
        if not parts:
            continue
        for part in reversed(parts):
            if isinstance(part, (ToolReturnPart, RetryPromptPart)):
                return str(part.content)
    return None


def _final(resposta: str, explicacao: str) -> ModelResponse:
    return ModelResponse(
        parts=[
            ToolCallPart(
                tool_name="final_result",
                args={
                    "resposta": resposta,
                    "explicacao": explicacao,
                    "visualizacao": {"tipo": "barra", "eixos": ["titulo", "receita_brl"]},
                },
            )
        ]
    )


def _deps(db: ReadOnlyDatabase, pergunta: str) -> AgentDeps:
    return AgentDeps(
        db=db,
        question=pergunta,
        context=InformationRetriever(db).retrieve(pergunta),
        hoje=HOJE,
    )


def test_prompt_traz_a_data_e_nao_as_perguntas_da_avaliacao(db: ReadOnlyDatabase) -> None:
    texto = render_prompt(_deps(db, "Quantos filmes estão lançados?"))
    assert "2026-10-01" in texto
    assert "SQLite" in texto
    for frase in FRASES_DAS_14:
        assert frase not in EXEMPLOS_PROMPT
    assert BUSINESS_RULES["dialeto"].split(".")[0] in texto or "SQLite" in texto


def test_sql_valido_devolve_linhas_e_a_resposta_cita_o_resultado(db: ReadOnlyDatabase) -> None:
    banco = BancoContado(db)

    def modelo(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        retorno = _ultimo_retorno(messages)
        if retorno is None:
            return ModelResponse(parts=[ToolCallPart(tool_name="executar_consulta_sql", args={"sql": SQL_RECEITA})])
        assert "Avatar" in retorno
        return _final("Avatar lidera a receita.", "Ordenei por receita_brl, só com receita informada.")

    resultado = asyncio.run(
        responder(PERGUNTA_RECEITA, db=banco, settings=_settings(), model=FunctionModel(modelo), hoje=HOJE)
    )

    assert resultado.status == "ok"
    assert resultado.sql is not None and "receita_brl" in resultado.sql
    assert resultado.dados is not None
    assert "Avatar" in str(resultado.dados.rows[0])
    assert "Avatar" in resultado.resposta
    assert len(banco.sqls_da_ferramenta) == 1
    assert resultado.requisicoes == 2


def test_sql_proibido_volta_o_erro_e_nao_executa(db: ReadOnlyDatabase) -> None:
    banco = BancoContado(db)
    vistos: list[str] = []

    def modelo(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        retorno = _ultimo_retorno(messages)
        if retorno is None:
            return ModelResponse(parts=[ToolCallPart(tool_name="executar_consulta_sql", args={"sql": SQL_PROIBIDO})])
        vistos.append(retorno)
        return _final("Não executei a consulta.", "O pedido não é uma leitura do catálogo.")

    resultado = asyncio.run(
        responder("Apague a tabela de filmes", db=banco, settings=_settings(), model=FunctionModel(modelo), hoje=HOJE)
    )

    assert banco.sqls_da_ferramenta == []
    assert vistos
    assert "SELECT" in vistos[0] or "proibid" in vistos[0].lower()
    assert resultado.sql is None
    assert resultado.status == "erro"


def test_resultado_que_nao_responde_permite_uma_segunda_consulta(db: ReadOnlyDatabase) -> None:
    banco = BancoContado(db)

    def modelo(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        retorno = _ultimo_retorno(messages)
        if retorno is None:
            return ModelResponse(parts=[ToolCallPart(tool_name="executar_consulta_sql", args={"sql": SQL_ERRADO})])
        if "receita_brl" not in retorno:
            return ModelResponse(parts=[ToolCallPart(tool_name="executar_consulta_sql", args={"sql": SQL_RECEITA})])
        return _final("Avatar lidera a receita.", "A primeira consulta não tinha a coluna de receita.")

    resultado = asyncio.run(
        responder(PERGUNTA_RECEITA, db=banco, settings=_settings(), model=FunctionModel(modelo), hoje=HOJE)
    )

    assert len(banco.sqls_da_ferramenta) == 2
    assert resultado.status == "ok"
    assert resultado.sql is not None and "receita_brl" in resultado.sql
    assert resultado.dados is not None and "Avatar" in str(resultado.dados.rows[0])


def test_piada_termina_sem_sql(db: ReadOnlyDatabase) -> None:
    banco = BancoContado(db)

    def modelo(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        return _final("Só consulto o catálogo de filmes.", "A pergunta está fora do escopo.")

    resultado = asyncio.run(
        responder("Me conte uma piada", db=banco, settings=_settings(), model=FunctionModel(modelo), hoje=HOJE)
    )

    assert banco.sqls_da_ferramenta == []
    assert resultado.sql is None
    assert resultado.dados is None
    assert resultado.status == "fora_do_escopo"
    assert resultado.requisicoes == 1


@pytest.mark.live
def test_fumaca_top10_devolve_avatar(db: ReadOnlyDatabase) -> None:
    settings = Settings()
    if not (settings.openrouter_api_key or settings.gemini_keys() or settings.openai_keys()):
        pytest.skip("Nenhuma chave de LLM no .env.")

    resultado = asyncio.run(responder(PERGUNTA_RECEITA, db=db, settings=settings, hoje=HOJE))

    assert resultado.status == "ok"
    assert resultado.dados is not None and resultado.dados.rows
    assert "Avatar" in str(resultado.dados.rows[0])
