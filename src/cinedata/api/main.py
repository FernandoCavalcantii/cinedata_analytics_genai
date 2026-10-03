"""Aplicação FastAPI. O roteador de modelos nasce uma vez no lifespan."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cinedata.agent.models import NoProviderConfiguredError
from cinedata.agent.service import ServicoAgente
from cinedata.api.exceptions import registrar_erros
from cinedata.api.router import router
from cinedata.config import get_settings
from cinedata.db.connection import ReadOnlyDatabase
from cinedata.observability import ligar_observabilidade


def create_app(
    *,
    servico: ServicoAgente | None = None,
    banco: bool | None = None,
    provedor: bool | None = None,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if servico is not None:
            app.state.servico = servico
            app.state.banco = True if banco is None else banco
            app.state.provedor = True if provedor is None else provedor
            yield
            return

        settings = get_settings()
        ligar_observabilidade(settings.logfire_token)
        db = ReadOnlyDatabase(
            settings.resolve_db_path(),
            timeout_seconds=settings.sql_timeout_seconds,
            max_rows=settings.sql_max_rows,
        )
        criado = ServicoAgente(settings, db)
        app.state.servico = criado
        app.state.banco = db.ping()
        try:
            criado.roteador()
            app.state.provedor = True
        except NoProviderConfiguredError:
            app.state.provedor = False
        yield

    app = FastAPI(
        title="CineData Analytics GenAI",
        summary="Perguntas em português sobre o catálogo de filmes.",
        lifespan=lifespan,
    )
    origens = cors_origins if cors_origins is not None else get_settings().cors_origins
    if origens:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origens,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    registrar_erros(app)
    app.include_router(router)
    return app


app = create_app()


def main() -> None:
    uvicorn.run("cinedata.api.main:app", host="127.0.0.1", port=8000)
