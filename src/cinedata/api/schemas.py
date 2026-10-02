"""Contrato HTTP da Seção 3 do plano, com exemplo para o /docs."""

from pydantic import BaseModel, Field, field_validator

from cinedata.agent.service import RespostaServico

PERGUNTAS_EDITAL = [
    "Top 10 filmes com maior receita em R$",
    "Lucro médio por gênero, considerando apenas filmes com receita informada",
    "Filmes com maior margem de lucro, entre os que possuem receita e orçamento informados",
    "Os 5 filmes mais populares",
    "Filmes com maior divergência entre a nota TMDB e a nota IMDb",
    "Nota média IMDb por ano de lançamento",
    "Ator com mais participações em filmes lançados nos últimos 5 anos",
    "Diretores com maior nota média (mínimo de 5 filmes)",
    "Dupla ator-diretor que mais trabalhou junta",
    "Quantidade de filmes por gênero",
    "Produtora com maior lucro total",
    "Gênero com maior margem de lucro média",
    "Filmes mais avaliados pelos usuários",
    "Filmes em que a nota média dos usuários mais diverge da nota IMDb",
]


class PedidoPergunta(BaseModel):
    pergunta: str = Field(examples=["Top 10 filmes com maior receita em R$"])
    conversa_id: str | None = None

    @field_validator("pergunta")
    @classmethod
    def _pergunta_nao_vazia(cls, value: str) -> str:
        texto = value.strip()
        if not texto:
            raise ValueError("A pergunta está vazia.")
        return texto


class ErroAPI(BaseModel):
    erro: str


class Saude(BaseModel):
    banco: bool
    provedor: bool


class ListaExemplos(BaseModel):
    perguntas: list[str]


EXEMPLO_RESPOSTA = RespostaServico.model_validate(
    {
        "conversa_id": "sessao-1",
        "status": "ok",
        "resposta": "Avatar lidera a receita.",
        "sql": "SELECT titulo, receita_brl FROM dim_movies LIMIT 10",
        "explicacao": "Ordenei por receita em reais.",
        "dados": {"colunas": ["titulo", "receita_brl"], "linhas": [["Avatar", 1]], "truncado": False},
        "visualizacao": {"tipo": "barra", "eixos": ["titulo", "receita_brl"]},
        "metadados": {"modelo": "gemini-3.5-flash-lite", "requisicoes": 2, "tempo_ms": 1200, "cache": False},
    }
)
