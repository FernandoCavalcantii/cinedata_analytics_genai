"""Circuit breaker sem rede e sem chave real."""

import asyncio

import pytest
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.function import FunctionModel

from cinedata.agent.models import CircuitBreaker, CircuitBreakerModel, NoProviderConfiguredError, build_router
from cinedata.config import Settings


def _settings_sem_chave() -> Settings:
    return Settings(
        openrouter_api_key="",
        openrouter_models=[],
        gemini_api_keys=[],
    )


def test_cadeia_prioriza_gemini_e_deixa_openrouter_por_ultimo() -> None:
    settings = Settings(
        openrouter_api_key="chave-openrouter",
        openrouter_models=["nvidia/nemotron-3.5-lightning:free", "openrouter/free"],
        gemini_api_keys=["chave-gemini"],
        gemini_model="gemini-3.5-flash-lite",
    )

    router = build_router(settings)

    assert router.chain == [
        "google:gemini-3.5-flash-lite#1",
        "openrouter:nvidia/nemotron-3.5-lightning:free",
        "openrouter:openrouter/free",
    ]


def test_aceita_quantas_chaves_gemini_forem_escritas() -> None:
    so_openrouter = Settings(
        openrouter_api_key="chave-openrouter",
        openrouter_models=["openrouter/free"],
        gemini_api_keys=[],
    )
    assert build_router(so_openrouter).chain == ["openrouter:openrouter/free"]

    quatro = Settings(
        openrouter_api_key="",
        openrouter_models=[],
        gemini_api_keys=["g1", "g2", "g3", "g4"],
        gemini_model="gemini-3.5-flash-lite",
    )
    assert build_router(quatro).chain == [
        "google:gemini-3.5-flash-lite#1",
        "google:gemini-3.5-flash-lite#2",
        "google:gemini-3.5-flash-lite#3",
        "google:gemini-3.5-flash-lite#4",
    ]


def test_sem_provedor_configurado() -> None:
    with pytest.raises(NoProviderConfiguredError):
        build_router(_settings_sem_chave())


def test_http_429_abre_o_breaker_e_a_chamada_seguinte_nao_chega_ao_modelo() -> None:
    calls = {"n": 0}

    def fail(_messages, _info):
        calls["n"] += 1
        raise ModelHTTPError(status_code=429, model_name="fake", body="pool lotado")

    breaker = CircuitBreaker("modelo de teste", cooldown_seconds=300)
    model = CircuitBreakerModel(FunctionModel(fail, model_name="fake"), breaker)

    async def run() -> None:
        with pytest.raises(ModelHTTPError):
            await model.request([], None, ModelRequestParameters())
        assert breaker.is_open is True
        with pytest.raises(ModelAPIError, match="circuit breaker"):
            await model.request([], None, ModelRequestParameters())

    asyncio.run(run())
    assert calls["n"] == 1


def test_cota_diaria_abre_o_breaker_do_provedor() -> None:
    def fail(_messages, _info):
        raise ModelHTTPError(status_code=429, model_name="fake", body="daily limit exceeded")

    provider = CircuitBreaker("openrouter (cota da chave)", cooldown_seconds=300)
    model_breaker = CircuitBreaker("openrouter:modelo", cooldown_seconds=300)
    model = CircuitBreakerModel(FunctionModel(fail, model_name="fake"), model_breaker, provider)

    async def run() -> None:
        with pytest.raises(ModelHTTPError):
            await model.request([], None, ModelRequestParameters())

    asyncio.run(run())
    assert provider.is_open is True
    assert model_breaker.is_open is True
