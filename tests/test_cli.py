"""O loop do terminal imprime a tabela, o cache e o CSV, sem LLM real."""

import io

from rich.console import Console

from cinedata.agent.service import ServicoAgente
from cinedata.cli import loop
from cinedata.db import ReadOnlyDatabase
from pydantic_ai.models.function import FunctionModel

from tests.agent.test_service import PERGUNTA, _modelo_receita, _settings


class _Console(Console):
    def __init__(self, linhas: list[str], buffer: io.StringIO) -> None:
        super().__init__(file=buffer, force_terminal=False, width=120)
        self._linhas = iter(linhas)

    def input(self, prompt: str = "", **kwargs: object) -> str:
        self.print(prompt, end="")
        return next(self._linhas)


def test_terminal_mostra_tabela_cache_e_exporta_csv(db: ReadOnlyDatabase, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    chamadas = {"n": 0}
    servico = ServicoAgente(
        _settings(tmp_path),
        db,
        model=FunctionModel(_modelo_receita(chamadas, []), model_name="falso"),
    )
    buffer = io.StringIO()
    console = _Console(
        [PERGUNTA, PERGUNTA, "csv", "Me conte uma piada", "sair"],
        buffer,
    )

    loop(servico, console, "sessao")
    texto = buffer.getvalue()

    assert "Avatar" in texto
    assert "cache: não" in texto
    assert "cache: sim" in texto
    assert "Sem SQL" in texto
    csv = (tmp_path / "resultado.csv").read_text(encoding="utf-8")
    assert "Avatar" in csv
