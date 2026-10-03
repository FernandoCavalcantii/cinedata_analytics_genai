"""Lê `regras.yaml` e `exemplos.yaml` ao lado deste módulo."""

from __future__ import annotations

from pathlib import Path

import yaml

PASTA = Path(__file__).resolve().parent


def carregar_regras() -> dict[str, str]:
    payload = yaml.safe_load((PASTA / "regras.yaml").read_text(encoding="utf-8"))
    regras = payload["regras"]
    return {chave: str(texto).strip() for chave, texto in regras.items()}


def carregar_exemplos() -> list[dict[str, str]]:
    payload = yaml.safe_load((PASTA / "exemplos.yaml").read_text(encoding="utf-8"))
    return [{"pergunta": item["pergunta"], "sql": item["sql"]} for item in payload["exemplos"]]


def texto_exemplos() -> str:
    blocos = [f"Pergunta: {item['pergunta']}\nSQL: {item['sql']}" for item in carregar_exemplos()]
    return "\n\n".join(blocos) + "\n"
