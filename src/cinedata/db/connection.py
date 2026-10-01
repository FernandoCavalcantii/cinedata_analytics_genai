"""Acesso somente leitura ao `cinerocket.db`.

Três barreiras independentes do guardrail de AST protegem o banco:
`mode=ro` na URI, `PRAGMA query_only = ON` e um authorizer do SQLite
que só autoriza leitura das tabelas do modelo dimensional.
"""

from __future__ import annotations

import csv
import io
import sqlite3
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

from cinedata.db.catalog import TABLE_NAMES

ALLOWED_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}
BLOCKED_FUNCTIONS = {"load_extension", "readfile", "writefile", "edit", "fts3_tokenizer"}
PROGRESS_HANDLER_OPCODES = 10_000


class DatabaseError(Exception):
    """Erro de acesso ao banco com mensagem segura para devolver ao modelo."""


class DatabaseNotFoundError(DatabaseError):
    pass


class QueryTimeoutError(DatabaseError):
    pass


@dataclass(frozen=True)
class QueryResult:
    columns: list[str]
    rows: list[list[Any]]
    truncated: bool
    elapsed_ms: float
    sql: str = field(repr=False, default="")

    @property
    def row_count(self) -> int:
        return len(self.rows)

    def to_records(self) -> list[dict[str, Any]]:
        return [dict(zip(self.columns, row)) for row in self.rows]

    def to_csv(self) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(self.columns)
        writer.writerows(self.rows)
        return buffer.getvalue()

    def preview_markdown(self, max_rows: int = 15) -> str:
        """Tabela compacta usada para o modelo narrar o resultado sem inventar números."""

        if not self.columns:
            return "(sem colunas)"
        header = "| " + " | ".join(self.columns) + " |"
        divider = "| " + " | ".join("---" for _ in self.columns) + " |"
        body = ["| " + " | ".join(_format_cell(v) for v in row) + " |" for row in self.rows[:max_rows]]
        return "\n".join([header, divider, *body])


def _format_cell(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value).replace("|", "/").replace("\n", " ")[:120]


def _authorizer(action: int, arg1: str | None, arg2: str | None, _db: str | None, _trigger: str | None) -> int:
    if action not in ALLOWED_ACTIONS:
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_READ and arg1 is not None and arg1 not in TABLE_NAMES:
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_FUNCTION and arg2 is not None and arg2.lower() in BLOCKED_FUNCTIONS:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


class ReadOnlyDatabase:
    def __init__(self, path: Path, *, timeout_seconds: float = 10.0, max_rows: int = 200) -> None:
        self.path = path.expanduser().resolve()
        if not self.path.is_file():
            raise DatabaseNotFoundError(
                f"Banco não encontrado em {self.path}. Coloque o cinerocket.db em data/ ou defina CINEROCKET_DB_PATH."
            )
        self.timeout_seconds = timeout_seconds
        self.max_rows = max_rows
        self._uri = f"file:{quote(self.path.as_posix(), safe='/')}?mode=ro&immutable=1"

    def _connect(self, deadline: float) -> sqlite3.Connection:
        connection = sqlite3.connect(self._uri, uri=True, check_same_thread=False)
        connection.execute("PRAGMA query_only = ON")
        connection.set_authorizer(_authorizer)
        connection.set_progress_handler(lambda: int(time.monotonic() > deadline), PROGRESS_HANDLER_OPCODES)
        return connection

    def execute(self, sql: str, params: Sequence[Any] = (), *, max_rows: int | None = None) -> QueryResult:
        limit = self.max_rows if max_rows is None else max_rows
        started = time.monotonic()
        deadline = started + self.timeout_seconds
        connection = self._connect(deadline)
        try:
            cursor = connection.execute(sql, params)
            columns = [description[0] for description in cursor.description or []]
            fetched = cursor.fetchmany(limit + 1)
        except sqlite3.OperationalError as exc:
            if "interrupted" in str(exc).lower():
                raise QueryTimeoutError(
                    f"A consulta excedeu o limite de {self.timeout_seconds:g}s. "
                    "Simplifique os JOINs, filtre antes de agregar ou use LIMIT."
                ) from exc
            raise DatabaseError(f"Erro do SQLite: {exc}") from exc
        except sqlite3.DatabaseError as exc:
            raise DatabaseError(f"Erro do SQLite: {exc}") from exc
        finally:
            connection.close()

        truncated = len(fetched) > limit
        rows = [list(row) for row in fetched[:limit]]
        elapsed_ms = (time.monotonic() - started) * 1000
        return QueryResult(columns=columns, rows=rows, truncated=truncated, elapsed_ms=elapsed_ms, sql=sql)

    def fetch_column(self, sql: str, params: Iterable[Any] = ()) -> list[Any]:
        return [row[0] for row in self.execute(sql, tuple(params)).rows]

    def ping(self) -> bool:
        try:
            self.execute("SELECT 1 FROM dim_movies LIMIT 1")
        except DatabaseError:
            return False
        return True
