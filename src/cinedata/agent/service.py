"""Contrato único da resposta, cache exato e memória curta da conversa.

A CLI e, na fase seguinte, a API consomem o mesmo objeto. O cache só guarda
consulta que a ferramenta executou. A memória da conversa vive no processo.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.models import Model

from cinedata.agent.models import ModelRouter, build_router
from cinedata.agent.retriever import normalize
from cinedata.agent.sql_agent import ResultadoAgente, TurnoAnterior, Visualizacao, responder
from cinedata.config import Settings
from cinedata.db.catalog import BUSINESS_RULES, TABLES
from cinedata.db.connection import QueryResult, ReadOnlyDatabase

MEMORIA_MAX_TURNOS = 3


class DadosResposta(BaseModel):
    colunas: list[str]
    linhas: list[list[Any]]
    truncado: bool


class Metadados(BaseModel):
    modelo: str
    requisicoes: int
    tempo_ms: float
    cache: bool


class RespostaServico(BaseModel):
    conversa_id: str
    status: Literal["ok", "fora_do_escopo", "erro"]
    resposta: str
    sql: str | None = None
    explicacao: str = ""
    dados: DadosResposta | None = None
    visualizacao: Visualizacao = Field(default_factory=Visualizacao)
    metadados: Metadados


@dataclass
class _Turno:
    pergunta: str
    sql: str | None
    resposta: str


def versao_catalogo() -> str:
    """Muda quando tabelas ou regras mudam, para o SQL guardado não envelhecer."""

    material = "\n".join(
        f"{table.name}:{','.join(column.name for column in table.columns)}" for table in TABLES
    )
    material += "\n" + "\n".join(f"{chave}:{texto}" for chave, texto in sorted(BUSINESS_RULES.items()))
    return hashlib.sha256(material.encode()).hexdigest()[:16]


def normalizar_pergunta(pergunta: str) -> str:
    return " ".join(normalize(pergunta).split())


def dados_de(result: QueryResult) -> DadosResposta:
    return DadosResposta(colunas=list(result.columns), linhas=[list(row) for row in result.rows], truncado=result.truncated)


class CacheRespostas:
    def __init__(self, settings: Settings) -> None:
        self.enabled = settings.cache_enabled
        self.path = settings.resolve_cache_path()
        self.versao = versao_catalogo()
        self._entradas: dict[str, dict[str, Any]] = {}
        self._carregar()

    def _carregar(self) -> None:
        if not self.enabled or not self.path.is_file():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if payload.get("versao_catalogo") != self.versao:
            return
        entradas = payload.get("entradas")
        if isinstance(entradas, dict):
            self._entradas = entradas

    def obter(self, pergunta: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        entrada = self._entradas.get(normalizar_pergunta(pergunta))
        return entrada if isinstance(entrada, dict) else None

    def guardar(self, pergunta: str, corpo: dict[str, Any]) -> None:
        if not self.enabled:
            return
        self._entradas[normalizar_pergunta(pergunta)] = corpo
        self._gravar()

    def limpar(self) -> None:
        self._entradas = {}
        if self.path.is_file():
            self.path.unlink()

    def _gravar(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"versao_catalogo": self.versao, "entradas": self._entradas}
        temporario = self.path.with_suffix(".tmp")
        temporario.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporario.replace(self.path)


@dataclass
class ServicoAgente:
    settings: Settings
    db: ReadOnlyDatabase
    model: Model | None = None
    hoje: date | None = None
    cache: CacheRespostas = field(init=False)
    _conversas: dict[str, list[_Turno]] = field(default_factory=dict)
    _roteador: ModelRouter | None = None

    def __post_init__(self) -> None:
        self.cache = CacheRespostas(self.settings)

    def roteador(self) -> ModelRouter:
        """Monta a cadeia uma vez, para o circuit breaker sobreviver entre perguntas."""

        if self._roteador is None:
            self._roteador = build_router(self.settings)
        return self._roteador

    async def perguntar(self, pergunta: str, conversa_id: str | None = None) -> RespostaServico:
        texto = pergunta.strip()
        conversa = conversa_id or str(uuid.uuid4())
        inicio = time.perf_counter()
        if not texto:
            return self._erro(conversa, "A pergunta está vazia.", inicio, modelo="")

        guardada = self.cache.obter(texto)
        if guardada is not None:
            resposta = self._do_cache(conversa, guardada, inicio)
            self._lembrar(conversa, texto, resposta)
            return resposta

        historico = [
            TurnoAnterior(pergunta=turno.pergunta, sql=turno.sql, resposta=turno.resposta)
            for turno in self._conversas.get(conversa, [])[-MEMORIA_MAX_TURNOS:]
        ]
        try:
            resultado = await responder(
                texto,
                db=self.db,
                settings=self.settings,
                model=self.model if self.model is not None else self.roteador().model,
                hoje=self.hoje,
                historico=historico,
            )
        except UsageLimitExceeded:
            teto = self.settings.max_llm_requests
            return self._erro(
                conversa,
                f"A pergunta usou as {teto} chamadas permitidas ao modelo e parou antes de responder. "
                "Tente uma frase mais direta.",
                inicio,
                modelo="",
                requisicoes=teto,
            )
        except Exception as exc:
            return self._erro(conversa, str(exc), inicio, modelo="")

        resposta = self._do_agente(conversa, resultado, inicio)
        if resultado.status == "ok" and resultado.sql:
            self.cache.guardar(texto, _corpo(resposta))
        self._lembrar(conversa, texto, resposta)
        return resposta

    def limpar_cache(self) -> None:
        self.cache.limpar()

    def _lembrar(self, conversa_id: str, pergunta: str, resposta: RespostaServico) -> None:
        turnos = self._conversas.setdefault(conversa_id, [])
        turnos.append(_Turno(pergunta=pergunta, sql=resposta.sql, resposta=resposta.resposta))
        del turnos[:-MEMORIA_MAX_TURNOS]

    def _do_cache(self, conversa_id: str, corpo: dict[str, Any], inicio: float) -> RespostaServico:
        resposta = RespostaServico.model_validate({"conversa_id": conversa_id, **corpo})
        resposta.metadados.cache = True
        resposta.metadados.requisicoes = 0
        resposta.metadados.tempo_ms = _ms(inicio)
        return resposta

    def _do_agente(self, conversa_id: str, resultado: ResultadoAgente, inicio: float) -> RespostaServico:
        dados = dados_de(resultado.dados) if resultado.dados is not None else None
        return RespostaServico(
            conversa_id=conversa_id,
            status=resultado.status,
            resposta=resultado.resposta,
            sql=resultado.sql,
            explicacao=resultado.explicacao,
            dados=dados,
            visualizacao=resultado.visualizacao,
            metadados=Metadados(
                modelo=resultado.modelo,
                requisicoes=resultado.requisicoes,
                tempo_ms=_ms(inicio),
                cache=False,
            ),
        )

    def _erro(
        self,
        conversa_id: str,
        mensagem: str,
        inicio: float,
        modelo: str,
        requisicoes: int = 0,
    ) -> RespostaServico:
        return RespostaServico(
            conversa_id=conversa_id,
            status="erro",
            resposta=mensagem,
            metadados=Metadados(
                modelo=modelo,
                requisicoes=requisicoes,
                tempo_ms=_ms(inicio),
                cache=False,
            ),
        )


def _corpo(resposta: RespostaServico) -> dict[str, Any]:
    corpo = resposta.model_dump()
    corpo.pop("conversa_id", None)
    return corpo


def _ms(inicio: float) -> float:
    return round((time.perf_counter() - inicio) * 1000, 1)
