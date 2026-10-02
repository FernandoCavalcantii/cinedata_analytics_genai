"""Rotas HTTP. Nenhuma delas chama o modelo direto: a pergunta passa pelo serviço."""

from fastapi import APIRouter, Depends, Request

from cinedata.agent.service import RespostaServico, ServicoAgente
from cinedata.api.dependencies import get_servico
from cinedata.api.exceptions import levantar_se_for_falha_de_infra
from cinedata.api.schemas import EXEMPLO_RESPOSTA, PERGUNTAS_EDITAL, ErroAPI, ListaExemplos, PedidoPergunta, Saude

router = APIRouter()


@router.get("/health", response_model=Saude)
def health(request: Request) -> Saude:
    return Saude(banco=request.app.state.banco, provedor=request.app.state.provedor)


@router.get("/api/v1/exemplos", response_model=ListaExemplos)
def exemplos() -> ListaExemplos:
    return ListaExemplos(perguntas=list(PERGUNTAS_EDITAL))


@router.post(
    "/api/v1/perguntas",
    response_model=RespostaServico,
    responses={
        200: {"content": {"application/json": {"example": EXEMPLO_RESPOSTA.model_dump()}}},
        422: {"model": ErroAPI, "description": "Pergunta vazia."},
        503: {"model": ErroAPI, "description": "Nenhum provedor disponível."},
        504: {"model": ErroAPI, "description": "A consulta SQL excedeu o tempo."},
    },
)
async def perguntas(pedido: PedidoPergunta, servico: ServicoAgente = Depends(get_servico)) -> RespostaServico:
    resposta = await servico.perguntar(pedido.pergunta, pedido.conversa_id)
    levantar_se_for_falha_de_infra(resposta)
    return resposta
