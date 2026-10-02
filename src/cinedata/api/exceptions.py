"""Erros de domínio viram JSON. A pergunta vazia é 422, o timeout de SQL é 504, sem provedor é 503."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from cinedata.agent.models import NoProviderConfiguredError
from cinedata.agent.service import RespostaServico
from cinedata.db.connection import QueryTimeoutError


def registrar_erros(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _pergunta_invalida)
    app.add_exception_handler(QueryTimeoutError, _timeout_sql)
    app.add_exception_handler(NoProviderConfiguredError, _sem_provedor)


def levantar_se_for_falha_de_infra(resposta: RespostaServico) -> None:
    """O serviço devolve erro no contrato. Estes dois casos sobem como HTTP."""

    if resposta.status != "erro":
        return
    texto = resposta.resposta
    if "excedeu o limite de" in texto:
        raise QueryTimeoutError(texto)
    if "circuit breaker" in texto.lower() or texto.startswith("Nenhum provedor"):
        raise NoProviderConfiguredError(texto)


async def _pergunta_invalida(_request: Request, exc: RequestValidationError) -> JSONResponse:
    vazia = any("pergunta" in erro.get("loc", ()) for erro in exc.errors())
    mensagem = "A pergunta está vazia." if vazia else "Requisição inválida."
    return JSONResponse(status_code=422, content={"erro": mensagem})


async def _timeout_sql(_request: Request, exc: QueryTimeoutError) -> JSONResponse:
    return JSONResponse(status_code=504, content={"erro": str(exc)})


async def _sem_provedor(_request: Request, exc: NoProviderConfiguredError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"erro": str(exc)})
