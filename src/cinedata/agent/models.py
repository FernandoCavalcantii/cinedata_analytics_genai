"""Roteador de modelos: Gemini e OpenAI na ordem de LLM_PRIMARY, OpenRouter por último.

No free tier do OpenRouter, requisições que falham também consomem a cota diária.
Por isso o cliente OpenAI do OpenRouter roda com `max_retries=0` e, depois de um
erro de cota/permissão, o modelo fica "aberto" por um tempo e é pulado sem tocar a rede.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from google.genai.types import HttpRetryOptions
from openai import AsyncOpenAI
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models import Model, ModelRequestParameters
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.models.wrapper import WrapperModel
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider
from pydantic_ai.settings import ModelSettings

from cinedata.config import Settings

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
TRIPPING_STATUS_CODES = {401, 402, 403, 404, 429, 503}


class NoProviderConfiguredError(RuntimeError):
    pass


@dataclass
class CircuitBreaker:
    name: str
    cooldown_seconds: float
    open_until: float = 0.0
    last_error: str = ""

    @property
    def is_open(self) -> bool:
        return time.monotonic() < self.open_until

    def trip(self, reason: str, seconds: float | None = None) -> None:
        self.open_until = time.monotonic() + (seconds or self.cooldown_seconds)
        self.last_error = reason[:300]

    def remaining_seconds(self) -> float:
        return max(0.0, self.open_until - time.monotonic())


def _is_daily_quota_error(exc: ModelHTTPError) -> bool:
    body = str(exc.body).lower()
    return exc.status_code == 429 and ("per-day" in body or "per day" in body or "daily" in body)


class CircuitBreakerModel(WrapperModel):
    """Pula o modelo enquanto o breaker do modelo (ou do provedor inteiro) estiver aberto."""

    def __init__(self, wrapped: Model, breaker: CircuitBreaker, provider_breaker: CircuitBreaker | None = None):
        super().__init__(wrapped)
        self.breaker = breaker
        self.provider_breaker = provider_breaker

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        for breaker in (self.provider_breaker, self.breaker):
            if breaker is not None and breaker.is_open:
                raise ModelAPIError(
                    self.model_name,
                    f"circuit breaker '{breaker.name}' aberto por mais {breaker.remaining_seconds():.0f}s "
                    f"(último erro: {breaker.last_error})",
                )
        try:
            return await self.wrapped.request(messages, model_settings, model_request_parameters)
        except ModelHTTPError as exc:
            if exc.status_code in TRIPPING_STATUS_CODES:
                reason = f"HTTP {exc.status_code}: {str(exc.body)[:200]}"
                if self.provider_breaker is not None and (_is_daily_quota_error(exc) or exc.status_code in {401, 402}):
                    self.provider_breaker.trip(reason)
                self.breaker.trip(reason, exc.retry_after)
            raise


@dataclass
class ModelRouter:
    model: Model
    chain: list[str]
    breakers: list[CircuitBreaker]

    def status(self) -> list[dict[str, object]]:
        return [
            {"nome": b.name, "aberto": b.is_open, "segundos_restantes": round(b.remaining_seconds()), "ultimo_erro": b.last_error}
            for b in self.breakers
        ]


def _append(models: list[Model], chain: list[str], breakers: list[CircuitBreaker], model: Model, label: str, cooldown: float) -> None:
    breaker = CircuitBreaker(label, cooldown_seconds=cooldown)
    breakers.append(breaker)
    models.append(CircuitBreakerModel(model, breaker))
    chain.append(label)


def _append_gemini(settings: Settings, models: list[Model], chain: list[str], breakers: list[CircuitBreaker]) -> None:
    for index, key in enumerate(settings.gemini_keys(), start=1):
        provider = GoogleProvider(api_key=key, retry_options=HttpRetryOptions(attempts=1))
        label = f"google:{settings.gemini_model}#{index}"
        _append(models, chain, breakers, GoogleModel(settings.gemini_model, provider=provider), label, settings.circuit_breaker_cooldown_seconds)


def _append_openai(settings: Settings, models: list[Model], chain: list[str], breakers: list[CircuitBreaker]) -> None:
    for index, key in enumerate(settings.openai_keys(), start=1):
        provider = OpenAIProvider(api_key=key)
        label = f"openai:{settings.openai_model}#{index}"
        _append(models, chain, breakers, OpenAIChatModel(settings.openai_model, provider=provider), label, settings.circuit_breaker_cooldown_seconds)


def build_router(settings: Settings) -> ModelRouter:
    models: list[Model] = []
    chain: list[str] = []
    breakers: list[CircuitBreaker] = []
    cooldown = settings.circuit_breaker_cooldown_seconds
    appenders = {"gemini": _append_gemini, "openai": _append_openai}

    for provider_name in settings.direct_provider_order():
        appenders[provider_name](settings, models, chain, breakers)

    if settings.openrouter_api_key and settings.openrouter_models:
        client = AsyncOpenAI(
            base_url=OPENROUTER_BASE_URL,
            api_key=settings.openrouter_api_key,
            max_retries=0,
            timeout=settings.llm_timeout_seconds,
            default_headers={"X-Title": "CineData Analytics GenAI"},
        )
        provider = OpenRouterProvider(openai_client=client)
        provider_breaker = CircuitBreaker("openrouter (cota da chave)", cooldown_seconds=cooldown)
        breakers.append(provider_breaker)
        for name in settings.openrouter_models:
            breaker = CircuitBreaker(f"openrouter:{name}", cooldown_seconds=cooldown)
            breakers.append(breaker)
            models.append(CircuitBreakerModel(OpenRouterModel(name, provider=provider), breaker, provider_breaker))
            chain.append(f"openrouter:{name}")

    if not models:
        raise NoProviderConfiguredError(
            "Nenhum provedor de LLM configurado. Defina GEMINI_API_KEYS, OPENAI_API_KEYS ou OPENROUTER_API_KEY no .env."
        )

    model = models[0] if len(models) == 1 else FallbackModel(*models)
    return ModelRouter(model=model, chain=chain, breakers=breakers)
