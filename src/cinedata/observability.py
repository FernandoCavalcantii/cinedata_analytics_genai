"""Liga o Logfire só quando há token e o extra `observability` está instalado."""

from __future__ import annotations

import os


def ligar_observabilidade(token: str | None = None) -> bool:
    """Instrumenta o PydanticAI. Sem token ou sem o pacote, não faz nada."""

    if token is None:
        token = os.environ.get("LOGFIRE_TOKEN", "")
    token = token.strip()
    if not token:
        return False
    try:
        import logfire
    except ImportError:
        return False
    logfire.configure(token=token, send_to_logfire="if-token-present")
    logfire.instrument_pydantic_ai()
    return True
