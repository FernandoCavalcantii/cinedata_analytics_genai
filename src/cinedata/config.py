"""Configuração central da aplicação, carregada do ambiente e do arquivo `.env`."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from typing_extensions import Annotated

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DB_CANDIDATES = (
    "data/cinerocket.db",
    "cinerocket.db",
    "cinerocket-db/cinerocket.db",
    "cinerocket-db/cinerocket (1).db",
)

CommaList = Annotated[list[str], NoDecode]
DIRECT_PROVIDERS = ("gemini", "openai")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_models: CommaList = Field(
        default=["nvidia/nemotron-3.5-lightning:free", "openrouter/free"],
        alias="OPENROUTER_MODELS",
    )

    gemini_api_keys: CommaList = Field(default=[], alias="GEMINI_API_KEYS")
    gemini_model: str = Field(default="gemini-3.5-flash-lite", alias="GEMINI_MODEL")

    openai_api_keys: CommaList = Field(default=[], alias="OPENAI_API_KEYS")
    # Compatível com um .env antigo que ainda tenha uma única OPENAI_API_KEY.
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    # gemini ou openai. O outro provedor direto vem em seguida. OpenRouter fica sempre por último.
    llm_primary: str = Field(default="gemini", alias="LLM_PRIMARY")

    db_path: str = Field(default="", alias="CINEROCKET_DB_PATH")

    sql_timeout_seconds: float = Field(default=10.0, alias="SQL_TIMEOUT_SECONDS")
    sql_max_rows: int = Field(default=200, alias="SQL_MAX_ROWS")

    max_sql_retries: int = Field(default=2, alias="AGENT_MAX_SQL_RETRIES")
    max_llm_requests: int = Field(default=6, alias="AGENT_MAX_LLM_REQUESTS")
    # Ignorado pelo agente (ADR 013). A resposta sai depois que o modelo vê as linhas da ferramenta.
    narrate: bool = Field(default=True, alias="AGENT_NARRATE")
    cache_enabled: bool = Field(default=True, alias="AGENT_CACHE_ENABLED")
    cache_path: str = Field(default=".cache/respostas.json", alias="AGENT_CACHE_PATH")
    llm_timeout_seconds: float = Field(default=60.0, alias="LLM_TIMEOUT_SECONDS")
    circuit_breaker_cooldown_seconds: float = Field(default=300.0, alias="CIRCUIT_BREAKER_COOLDOWN_SECONDS")

    @field_validator("openrouter_models", "gemini_api_keys", "openai_api_keys", mode="before")
    @classmethod
    def _split_comma_list(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("llm_primary", mode="before")
    @classmethod
    def _primary_provider(cls, value: object) -> str:
        name = str(value or "gemini").strip().lower()
        if name not in DIRECT_PROVIDERS:
            raise ValueError("LLM_PRIMARY deve ser gemini ou openai.")
        return name

    def gemini_keys(self) -> list[str]:
        """Todas as chaves Gemini, na ordem em que foram escritas, sem repetir."""

        return _unique_keys(self.gemini_api_keys)

    def openai_keys(self) -> list[str]:
        """Todas as chaves OpenAI. `OPENAI_API_KEY` entra depois de `OPENAI_API_KEYS`, sem repetir."""

        keys = list(self.openai_api_keys)
        if self.openai_api_key.strip():
            keys.append(self.openai_api_key.strip())
        return _unique_keys(keys)

    def direct_provider_order(self) -> tuple[str, str]:
        """Provedor escolhido primeiro e o outro em seguida. OpenRouter não entra aqui."""

        first = self.llm_primary
        second = "openai" if first == "gemini" else "gemini"
        return first, second

    def resolve_db_path(self) -> Path:
        """Localiza o `cinerocket.db`; caminhos relativos partem da raiz do projeto."""

        if self.db_path:
            path = Path(self.db_path).expanduser()
            return path if path.is_absolute() else PROJECT_ROOT / path
        for candidate in DB_CANDIDATES:
            path = PROJECT_ROOT / candidate
            if path.is_file():
                return path
        return PROJECT_ROOT / DB_CANDIDATES[0]

    def resolve_cache_path(self) -> Path:
        path = Path(self.cache_path).expanduser()
        return path if path.is_absolute() else PROJECT_ROOT / path


def _unique_keys(keys: list[str]) -> list[str]:
    chosen: list[str] = []
    for key in keys:
        key = key.strip()
        if key and key not in chosen:
            chosen.append(key)
    return chosen


@lru_cache
def get_settings() -> Settings:
    return Settings()
