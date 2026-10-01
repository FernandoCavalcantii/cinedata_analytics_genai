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
        openai_api_key="",
    )


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
