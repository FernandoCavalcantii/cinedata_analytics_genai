"""Acesso somente leitura ao banco e catálogo semântico do schema."""

from cinedata.db.catalog import BUSINESS_RULES, TABLE_NAMES, TABLES, render_schema
from cinedata.db.connection import (
    DatabaseError,
    DatabaseNotFoundError,
    QueryResult,
    QueryTimeoutError,
    ReadOnlyDatabase,
)

__all__ = [
    "BUSINESS_RULES",
    "TABLE_NAMES",
    "TABLES",
    "DatabaseError",
    "DatabaseNotFoundError",
    "QueryResult",
    "QueryTimeoutError",
    "ReadOnlyDatabase",
    "render_schema",
]
