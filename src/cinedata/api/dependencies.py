"""O serviço criado no lifespan chega nas rotas por injeção."""

from fastapi import Request

from cinedata.agent.service import ServicoAgente


def get_servico(request: Request) -> ServicoAgente:
    return request.app.state.servico
