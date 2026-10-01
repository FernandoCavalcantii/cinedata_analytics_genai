"""Etapas determinísticas do CHESS: Information Retriever e Schema Selector.

Não consomem chamadas de LLM: palavras-chave mapeiam conceitos de negócio para
tabelas e regras, e entidades citadas na pergunta são confirmadas no próprio banco.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from cinedata.db.catalog import BUSINESS_RULES, GENRE_TRANSLATIONS, TABLES, render_schema
from cinedata.db.connection import DatabaseError, ReadOnlyDatabase

ALWAYS_RULES = ("dialeto", "apresentacao")


@dataclass(frozen=True)
class Concept:
    name: str
    pattern: re.Pattern[str]
    tables: tuple[str, ...]
    rules: tuple[str, ...] = ()


def _c(name: str, regex: str, tables: tuple[str, ...], rules: tuple[str, ...] = ()) -> Concept:
    return Concept(name, re.compile(regex), tables, rules)


FACT = ("fact_movies_performance",)
GENRES = ("dim_genres", "bridge_movie_genre")
PEOPLE = ("dim_people", "bridge_movie_person")
COMPANIES = ("dim_companies", "bridge_movie_company")

CONCEPTS: tuple[Concept, ...] = (
    _c("receita", r"\b(receit|faturament|bilheter|arrecad|renda)\w*", FACT, ("receita",)),
    _c("lucro", r"\b(lucr|prejuiz|rentab|lucrativ)\w*", FACT, ("receita", "lucro")),
    _c("margem", r"\b(margem|margens|roi|retorno)\b", FACT, ("receita", "lucro", "margem")),
    _c("orcamento", r"\b(orcament|custo|investiment|gast)\w*", FACT, ("lucro",)),
    _c("popularidade", r"\bpopular\w*", FACT, ("popularidade",)),
    _c("notas", r"\b(nota|notas|imdb|tmdb|avaliad[oa]s? pela critica|rating)\b", FACT, ("notas",)),
    _c("divergencia", r"\b(diverg|diferenc|discrepan|discord)\w*", FACT, ("divergencia", "notas", "minimos")),
    _c("media", r"\b(media|medias|medio|medios)\b", (), ("minimos",)),
    _c("genero", r"\b(genero|generos|categoria|categorias)\b", GENRES, ("generos",)),
    _c("pessoas", r"\b(ator|atores|atriz|atrizes|elenco|diretor|diretores|diretora|dirigid\w*|direcao|"
                  r"roteir\w*|pessoa|pessoas|dupla|duplas|parceri\w*|artista\w*)\b", PEOPLE, ("pessoas",)),
    _c("produtoras", r"\b(produtor\w*|estudio\w*|empresa\w*|companhia\w*)\b", COMPANIES),
    _c("avaliacoes", r"\b(avaliac\w*|avaliad\w*|review\w*|resenha\w*|comentari\w*|usuari\w*|public\w*|espectador\w*)",
       ("dim_reviews",), ("avaliacoes_usuarios", "minimos")),
    _c("comentarios", r"\b(comentari\w*|resenha\w*|texto\w*|opini\w*)", ("movie_reviews",), ("avaliacoes_usuarios",)),
    _c("periodo", r"\b(ultim[oa]s?|recentes?|decada|desde|entre)\b|\b(?:19|20)\d{2}\b", (), ("periodo",)),
)

_CONNECTORS = {"de", "da", "do", "dos", "das", "of", "the", "and", "&"}

_CAPITALIZED_SEQUENCE = re.compile(
    r"\b([A-ZÀ-Ý][\w'.:-]+(?:\s+(?:de|da|do|dos|das|of|the|and|&|[A-ZÀ-Ý0-9][\w'.:-]*))*\s+[A-ZÀ-Ý0-9][\w'.:-]*)"
)
_QUOTED = re.compile(r"[\"“”']([^\"“”']{2,80})[\"“”']")


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()


@dataclass
class RetrievalContext:
    tables: list[str]
    rules: list[str]
    hints: list[str] = field(default_factory=list)
    concepts: list[str] = field(default_factory=list)

    def schema_prompt(self) -> str:
        return render_schema(self.tables)

    def rules_prompt(self) -> str:
        return "\n".join(f"- {BUSINESS_RULES[rule]}" for rule in self.rules)

    def hints_prompt(self) -> str:
        return "\n".join(f"- {hint}" for hint in self.hints) or "- (nenhum valor específico identificado)"


class InformationRetriever:
    def __init__(self, db: ReadOnlyDatabase | None = None) -> None:
        self.db = db

    def retrieve(self, question: str) -> RetrievalContext:
        normalized = normalize(question)
        tables: set[str] = {"dim_movies"}
        rules: list[str] = list(ALWAYS_RULES)
        concepts: list[str] = []

        for concept in CONCEPTS:
            if concept.pattern.search(normalized):
                concepts.append(concept.name)
                tables.update(concept.tables)
                rules += [rule for rule in concept.rules if rule not in rules]

        hints = self._genre_hints(normalized)
        if hints:
            tables.update(GENRES)
            if "generos" not in rules:
                rules.append("generos")

        entity_hints, entity_tables = self._entity_hints(question)
        hints += entity_hints
        tables.update(entity_tables)
        if entity_tables & set(PEOPLE) and "pessoas" not in rules:
            rules.append("pessoas")

        if not concepts and not hints:
            tables = {table.name for table in TABLES}
            rules = list(BUSINESS_RULES)

        ordered = [table.name for table in TABLES if table.name in tables]
        return RetrievalContext(tables=ordered, rules=rules, hints=hints, concepts=concepts)

    @staticmethod
    def _genre_hints(normalized: str) -> list[str]:
        found: dict[str, str] = {}
        for term, genre in GENRE_TRANSLATIONS.items():
            if re.search(rf"\b{re.escape(term)}\b", normalized):
                found.setdefault(genre, term)
        return [f"O termo '{term}' corresponde a dim_genres.nome_genero = '{genre}'." for genre, term in found.items()]

    def _entity_hints(self, question: str) -> tuple[list[str], set[str]]:
        if self.db is None:
            return [], set()
        candidates = _entity_candidates(question)
        hints: list[str] = []
        tables: set[str] = set()
        for candidate in sorted(c for c in candidates if len(c) >= 3)[:8]:
            try:
                roles = self.db.fetch_column(
                    "SELECT DISTINCT tipo_pessoa FROM dim_people WHERE nome_pessoa = ? COLLATE NOCASE", (candidate,)
                )
                if roles:
                    hints.append(
                        f"'{candidate}' existe em dim_people.nome_pessoa com papel(éis): {', '.join(sorted(roles))}."
                    )
                    tables.update(PEOPLE)
                    continue
                companies = self.db.fetch_column(
                    "SELECT nome_produtora FROM dim_companies WHERE nome_produtora = ? COLLATE NOCASE LIMIT 1",
                    (candidate,),
                )
                if companies:
                    hints.append(f"'{candidate}' existe em dim_companies.nome_produtora como '{companies[0]}'.")
                    tables.update(COMPANIES)
                    continue
                titles = self.db.fetch_column(
                    "SELECT titulo FROM dim_movies WHERE titulo = ? COLLATE NOCASE LIMIT 1", (candidate,)
                )
                if titles:
                    hints.append(f"'{candidate}' existe em dim_movies.titulo como '{titles[0]}'.")
            except DatabaseError:
                continue
        return hints, tables


def _entity_candidates(question: str) -> set[str]:
    """Nomes citados na pergunta, inclusive quando a frase começa com uma palavra comum.

    "Filmes da Warner Bros. Pictures" gera "Warner Bros. Pictures" além da frase inteira,
    porque a primeira maiúscula pode ser só o início da oração.
    """

    candidates: set[str] = set()
    for match in _QUOTED.findall(question):
        _add_candidate(candidates, match)
    for match in _CAPITALIZED_SEQUENCE.findall(question):
        words = match.split()
        for index, word in enumerate(words):
            if word[:1].islower() or word.lower() in _CONNECTORS:
                continue
            if index == 0 or word[:1].isupper():
                _add_candidate(candidates, " ".join(words[index:]))
    return candidates


def _add_candidate(candidates: set[str], text: str) -> None:
    cleaned = text.strip(" .?!,;:")
    if len(cleaned) >= 3:
        candidates.add(cleaned)
