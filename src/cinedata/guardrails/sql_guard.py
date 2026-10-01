"""Guardrail de AST: só deixa passar um único SELECT sobre as tabelas do modelo dimensional.

As mensagens de erro são escritas para o LLM: viram o feedback do `ModelRetry`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from cinedata.db.catalog import TABLE_NAMES
from cinedata.db.connection import BLOCKED_FUNCTIONS

logging.getLogger("sqlglot").setLevel(logging.ERROR)

_FORBIDDEN_NODE_NAMES = (
    "Insert", "Update", "Delete", "Merge", "Drop", "Create", "Alter", "TruncateTable",
    "Command", "Pragma", "Attach", "Detach", "Transaction", "Commit", "Rollback",
    "Set", "Use", "Copy", "LoadData", "Analyze", "Grant", "Revoke",
)
FORBIDDEN_NODES: tuple[type[exp.Expression], ...] = tuple(
    getattr(exp, name) for name in _FORBIDDEN_NODE_NAMES if hasattr(exp, name)
)


class UnsafeSQLError(ValueError):
    """SQL rejeitado pelo guardrail."""


@dataclass(frozen=True)
class ValidatedSQL:
    sql: str
    tables: tuple[str, ...]


def validate_sql(sql: str, allowed_tables: frozenset[str] = TABLE_NAMES) -> ValidatedSQL:
    cleaned = sql.strip().strip(";").strip()
    if not cleaned:
        raise UnsafeSQLError("A consulta SQL está vazia.")

    try:
        statements = [statement for statement in sqlglot.parse(cleaned, read="sqlite") if statement is not None]
    except ParseError as exc:
        raise UnsafeSQLError(f"SQL inválido para SQLite: {_first_line(exc)}") from exc

    if len(statements) != 1:
        raise UnsafeSQLError("Envie exatamente UM comando SQL, sem ';' separando múltiplos comandos.")

    root = statements[0]
    if not isinstance(root, (exp.Select, exp.SetOperation)):
        raise UnsafeSQLError(
            f"Somente consultas de leitura (SELECT/WITH) são permitidas; recebido: {root.key.upper()}."
        )

    for node in root.walk():
        if isinstance(node, FORBIDDEN_NODES):
            raise UnsafeSQLError(f"Operação proibida dentro da consulta: {node.key.upper()}.")
        if isinstance(node, exp.Func):
            name = (node.name if isinstance(node, exp.Anonymous) else node.sql_name()).lower()
            if name in BLOCKED_FUNCTIONS:
                raise UnsafeSQLError(f"Função proibida: {name}.")

    cte_names = {cte.alias_or_name for cte in root.find_all(exp.CTE)}
    referenced = {table.name for table in root.find_all(exp.Table) if table.name}
    unknown = sorted(referenced - cte_names - allowed_tables)
    if unknown:
        raise UnsafeSQLError(
            f"Tabela(s) inexistente(s) ou não permitida(s): {', '.join(unknown)}. "
            f"Tabelas disponíveis: {', '.join(sorted(allowed_tables))}."
        )

    return ValidatedSQL(sql=cleaned, tables=tuple(sorted(referenced - cte_names)))


def _first_line(exc: Exception) -> str:
    return str(exc).splitlines()[0][:300]
