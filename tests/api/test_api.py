"""A API devolve o contrato do serviço, sem chamar LLM."""

from fastapi.testclient import TestClient

from cinedata.agent.service import DadosResposta, Metadados, RespostaServico
from cinedata.api.main import create_app
from cinedata.api.schemas import PERGUNTAS_EDITAL


class _Falso:
    def __init__(self) -> None:
        self.chamadas: list[tuple[str, str | None]] = []

    async def perguntar(self, pergunta: str, conversa_id: str | None = None) -> RespostaServico:
        self.chamadas.append((pergunta, conversa_id))
        if "timeout" in pergunta:
            texto = "A consulta excedeu o limite de 10s. Simplifique os JOINs."
            status = "erro"
            resposta = texto
        elif "sem provedor" in pergunta:
            status = "erro"
            resposta = "Nenhum provedor de LLM configurado. Defina GEMINI_API_KEYS ou OPENROUTER_API_KEY no .env."
        elif "breaker" in pergunta:
            status = "erro"
            resposta = "circuit breaker 'google:gemini-3.5-flash-lite#1' aberto por mais 200s"
        else:
            status = "ok"
            resposta = "Avatar lidera."
        return RespostaServico(
            conversa_id=conversa_id or "gerada",
            status=status,
            resposta=resposta,
            sql="SELECT 1" if status == "ok" else None,
            explicacao="Ordenei por receita." if status == "ok" else "",
            dados=DadosResposta(colunas=["titulo"], linhas=[["Avatar"]], truncado=False) if status == "ok" else None,
            metadados=Metadados(modelo="falso", requisicoes=0, tempo_ms=1, cache=False),
        )


def _cliente(servico: _Falso | None = None, **kwargs: object) -> TestClient:
    app = create_app(servico=servico or _Falso(), **kwargs)  # type: ignore[arg-type]
    return TestClient(app)


def test_pergunta_devolve_o_contrato_e_repete_a_conversa() -> None:
    servico = _Falso()
    with _cliente(servico) as client:
        resposta = client.post(
            "/api/v1/perguntas",
            json={"pergunta": "Top 10 filmes com maior receita em R$", "conversa_id": "c1"},
        )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["resposta"] == "Avatar lidera."
    assert corpo["conversa_id"] == "c1"
    assert corpo["dados"]["linhas"] == [["Avatar"]]
    assert servico.chamadas == [("Top 10 filmes com maior receita em R$", "c1")]


def test_pergunta_vazia_responde_422() -> None:
    with _cliente() as client:
        vazia = client.post("/api/v1/perguntas", json={"pergunta": "   "})
        ausente = client.post("/api/v1/perguntas", json={})

    assert vazia.status_code == 422
    assert vazia.json() == {"erro": "A pergunta está vazia."}
    assert ausente.status_code == 422
    assert ausente.json() == {"erro": "A pergunta está vazia."}


def test_exemplos_traz_as_14_perguntas() -> None:
    with _cliente() as client:
        resposta = client.get("/api/v1/exemplos")

    assert resposta.status_code == 200
    perguntas = resposta.json()["perguntas"]
    assert len(perguntas) == 14
    assert perguntas == PERGUNTAS_EDITAL
    assert perguntas[0] == "Top 10 filmes com maior receita em R$"


def test_health_informa_banco_e_provedor() -> None:
    with _cliente(banco=False, provedor=False) as client:
        resposta = client.get("/health")

    assert resposta.status_code == 200
    assert resposta.json() == {"banco": False, "provedor": False}


def test_timeout_de_sql_responde_504_e_sem_provedor_responde_503() -> None:
    with _cliente() as client:
        timeout = client.post("/api/v1/perguntas", json={"pergunta": "consulta timeout"})
        sem_chave = client.post("/api/v1/perguntas", json={"pergunta": "sem provedor"})
        breaker = client.post("/api/v1/perguntas", json={"pergunta": "breaker aberto"})

    assert timeout.status_code == 504
    assert "excedeu o limite" in timeout.json()["erro"]
    assert sem_chave.status_code == 503
    assert breaker.status_code == 503


def test_docs_lista_as_tres_rotas_e_o_exemplo() -> None:
    with _cliente() as client:
        esquema = client.get("/openapi.json")

    assert esquema.status_code == 200
    caminhos = esquema.json()["paths"]
    assert {"/health", "/api/v1/exemplos", "/api/v1/perguntas"} <= set(caminhos)
    exemplo = caminhos["/api/v1/perguntas"]["post"]["responses"]["200"]["content"]["application/json"]["example"]
    assert exemplo["resposta"] == "Avatar lidera a receita."


def test_cors_so_entra_quando_a_origem_esta_configurada() -> None:
    origem = "http://localhost:5173"
    with _cliente() as fechado:
        sem_cors = fechado.get("/health", headers={"Origin": origem})
    with _cliente(cors_origins=[origem]) as aberto:
        com_cors = aberto.get("/health", headers={"Origin": origem})

    assert "access-control-allow-origin" not in sem_cors.headers
    assert com_cors.headers["access-control-allow-origin"] == origem
