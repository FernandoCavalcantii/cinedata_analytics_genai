"""Cache exato, memória da conversa e o contrato da resposta, sem chamar LLM."""

import asyncio
import json

from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from cinedata.agent.service import ServicoAgente, normalizar_pergunta, versao_catalogo
from cinedata.config import Settings
from cinedata.db import ReadOnlyDatabase
from tests.agent.test_sql_agent import SQL_RECEITA, _final

PERGUNTA = "Top 10 filmes com maior receita em R$"


def _settings(tmp_path) -> Settings:
    return Settings(
        openrouter_api_key="",
        openrouter_models=[],
        gemini_api_keys=[],
        max_sql_retries=2,
        max_llm_requests=6,
        cache_enabled=True,
        cache_path=str(tmp_path / "respostas.json"),
    )


def _modelo_receita(chamadas: dict[str, int], vistos: list[str]):
    def modelo(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        chamadas["n"] += 1
        texto = "\n".join(_texto(messages))
        vistos.append(texto)
        pergunta = _pergunta_atual(messages)
        if "piada" in pergunta.lower():
            return _final("Só consulto o catálogo.", "Fora do escopo.")
        if "Linhas devolvidas" not in texto:
            return ModelResponse(parts=[ToolCallPart(tool_name="executar_consulta_sql", args={"sql": SQL_RECEITA})])
        return _final("Avatar lidera a receita.", "Ordenei por receita_brl.")

    return modelo


def _pergunta_atual(messages: list[ModelMessage]) -> str:
    perguntas: list[str] = []
    for message in messages:
        for part in getattr(message, "parts", []):
            if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                perguntas.append(part.content)
    return perguntas[-1] if perguntas else ""


def _texto(messages: list[ModelMessage]) -> list[str]:
    partes: list[str] = []
    for message in messages:
        instrucoes = getattr(message, "instructions", None)
        if isinstance(instrucoes, str):
            partes.append(instrucoes)
        for part in getattr(message, "parts", []):
            conteudo = getattr(part, "content", None)
            if isinstance(conteudo, str):
                partes.append(conteudo)
            args = getattr(part, "args", None)
            if args:
                partes.append(str(args))
    return partes


def test_segunda_pergunta_igual_nao_chama_o_modelo(db: ReadOnlyDatabase, tmp_path) -> None:
    chamadas = {"n": 0}
    servico = ServicoAgente(
        _settings(tmp_path),
        db,
        model=FunctionModel(_modelo_receita(chamadas, []), model_name="falso"),
    )

    primeira = asyncio.run(servico.perguntar(PERGUNTA, "conversa-1"))
    feitas = chamadas["n"]
    segunda = asyncio.run(servico.perguntar("  top   10 filmes com maior receita em R$ ", "conversa-1"))

    assert primeira.status == "ok"
    assert primeira.dados is not None
    assert "Avatar" in str(primeira.dados.linhas[0])
    assert primeira.metadados.cache is False
    assert primeira.sql is not None
    assert segunda.metadados.cache is True
    assert segunda.metadados.requisicoes == 0
    assert segunda.sql == primeira.sql
    assert chamadas["n"] == feitas


def test_fora_do_escopo_nao_entra_no_cache(db: ReadOnlyDatabase, tmp_path) -> None:
    chamadas = {"n": 0}
    servico = ServicoAgente(
        _settings(tmp_path),
        db,
        model=FunctionModel(_modelo_receita(chamadas, []), model_name="falso"),
    )

    primeira = asyncio.run(servico.perguntar("Me conte uma piada", "c"))
    depois = chamadas["n"]
    segunda = asyncio.run(servico.perguntar("Me conte uma piada", "c"))

    assert primeira.status == "fora_do_escopo"
    assert primeira.sql is None
    assert primeira.dados is None
    assert segunda.metadados.cache is False
    assert chamadas["n"] == depois + 1


def test_continuacao_enxerga_a_pergunta_anterior(db: ReadOnlyDatabase, tmp_path) -> None:
    chamadas = {"n": 0}
    vistos: list[str] = []
    servico = ServicoAgente(
        _settings(tmp_path),
        db,
        model=FunctionModel(_modelo_receita(chamadas, vistos), model_name="falso"),
    )

    asyncio.run(servico.perguntar(PERGUNTA, "sessao"))
    asyncio.run(servico.perguntar("e o segundo colocado?", "sessao"))

    assert any("e o segundo colocado?" in texto and PERGUNTA in texto for texto in vistos)


def test_limpar_cache_volta_a_chamar_o_modelo(db: ReadOnlyDatabase, tmp_path) -> None:
    chamadas = {"n": 0}
    servico = ServicoAgente(
        _settings(tmp_path),
        db,
        model=FunctionModel(_modelo_receita(chamadas, []), model_name="falso"),
    )

    asyncio.run(servico.perguntar(PERGUNTA, "c"))
    feitas = chamadas["n"]
    servico.limpar_cache()
    de_novo = asyncio.run(servico.perguntar(PERGUNTA, "c"))

    assert de_novo.metadados.cache is False
    assert chamadas["n"] > feitas


def test_versao_velha_do_catalogo_nao_reaproveita(db: ReadOnlyDatabase, tmp_path) -> None:
    caminho = tmp_path / "respostas.json"
    caminho.write_text(
        json.dumps({"versao_catalogo": "antiga", "entradas": {normalizar_pergunta(PERGUNTA): {"resposta": "velha"}}}),
        encoding="utf-8",
    )
    chamadas = {"n": 0}
    servico = ServicoAgente(
        _settings(tmp_path),
        db,
        model=FunctionModel(_modelo_receita(chamadas, []), model_name="falso"),
    )

    resposta = asyncio.run(servico.perguntar(PERGUNTA, "c"))

    assert resposta.metadados.cache is False
    assert versao_catalogo() != "antiga"
    assert resposta.resposta != "velha"


def test_pergunta_vazia_nao_chama_o_modelo(db: ReadOnlyDatabase, tmp_path) -> None:
    chamadas = {"n": 0}
    servico = ServicoAgente(
        _settings(tmp_path),
        db,
        model=FunctionModel(_modelo_receita(chamadas, []), model_name="falso"),
    )

    resposta = asyncio.run(servico.perguntar("   ", "c"))

    assert resposta.status == "erro"
    assert chamadas["n"] == 0


def test_roteador_e_montado_uma_vez_com_gemini_antes_do_openrouter(db: ReadOnlyDatabase, tmp_path) -> None:
    settings = _settings(tmp_path).model_copy(
        update={
            "gemini_api_keys": ["g"],
            "gemini_model": "gemini-3.5-flash-lite",
            "openrouter_api_key": "chave-openrouter",
            "openrouter_models": ["openrouter/free"],
        }
    )
    servico = ServicoAgente(settings, db)

    roteador = servico.roteador()

    assert roteador.chain == ["google:gemini-3.5-flash-lite#1", "openrouter:openrouter/free"]
    assert servico.roteador() is roteador


def test_teto_de_chamadas_avisa_em_portugues_e_conta_as_requisicoes(db: ReadOnlyDatabase, tmp_path, monkeypatch) -> None:
    async def estoura(*_args, **_kwargs):
        raise UsageLimitExceeded("The next request would exceed the request_limit of 6")

    monkeypatch.setattr("cinedata.agent.service.responder", estoura)
    servico = ServicoAgente(
        _settings(tmp_path),
        db,
        model=FunctionModel(_modelo_receita({"n": 0}, []), model_name="falso"),
    )

    resposta = asyncio.run(servico.perguntar(PERGUNTA, "c"))

    assert resposta.status == "erro"
    assert "6 chamadas" in resposta.resposta
    assert resposta.metadados.requisicoes == 6
