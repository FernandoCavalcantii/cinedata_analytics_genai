"""Catálogo semântico da camada Gold: tabelas, colunas, junções e regras de negócio.

As descrições e regras foram derivadas de auditoria direta do `cinerocket.db`
e são injetadas no prompt pelo Schema Selector.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Column:
    name: str
    type: str
    description: str


@dataclass(frozen=True)
class Table:
    name: str
    description: str
    columns: tuple[Column, ...]
    joins: tuple[str, ...] = ()


TABLES: tuple[Table, ...] = (
    Table(
        name="dim_movies",
        description="Catálogo de filmes (1 linha por filme, 95.645 filmes).",
        columns=(
            Column("sk_movie_id", "TEXT PK", "Chave substituta do filme."),
            Column("id_filme", "TEXT", "ID do filme na origem (TMDB)."),
            Column("titulo", "TEXT", "Título do filme (em inglês, capitalizado)."),
            Column("data_lancamento", "DATE", "Data de lançamento no formato 'YYYY-MM-DD'."),
            Column("ano_lancamento", "INTEGER", "Ano de lançamento (2016 a 2029)."),
            Column("duracao_minutos", "INTEGER", "Duração em minutos."),
            Column("idioma_original", "TEXT", "Sempre NULL nesta base; não usar."),
            Column("status_filme", "TEXT", "'Lançado', 'Pós-Produção', 'Em Produção' ou 'Planejado'."),
            Column("sinopse", "TEXT", "Sinopse do filme."),
            Column("url_poster", "TEXT", "URL do pôster."),
            Column("url_backdrop", "TEXT", "URL da imagem de fundo."),
        ),
    ),
    Table(
        name="fact_movies_performance",
        description="Métricas financeiras e de audiência (1 linha por filme).",
        columns=(
            Column("sk_movie_id", "TEXT PK/FK", "Filme (dim_movies.sk_movie_id)."),
            Column("orcamento_usd", "NUMERIC", "Orçamento em dólares; NULL quando não informado."),
            Column("receita_usd", "NUMERIC", "Receita/bilheteria em dólares; NULL quando não informada."),
            Column("lucro_usd", "NUMERIC", "Lucro em dólares (ver regras de lucro)."),
            Column("orcamento_brl", "NUMERIC", "Orçamento em reais; NULL quando não informado."),
            Column("receita_brl", "NUMERIC", "Receita/bilheteria/faturamento em reais; NULL quando não informada."),
            Column("lucro_brl", "NUMERIC", "Lucro em reais (ver regras de lucro)."),
            Column("popularidade", "REAL", "Índice de popularidade do TMDB (maior = mais popular)."),
            Column("nota_tmdb", "REAL", "Nota média TMDB (0-10); 0 significa sem votos."),
            Column("qtd_tmdb", "INTEGER", "Quantidade de votos no TMDB."),
            Column("nota_imdb", "REAL", "Nota média IMDb (0-10); NULL quando ausente."),
            Column("qtd_imdb", "INTEGER", "Quantidade de votos no IMDb."),
        ),
        joins=("fact_movies_performance.sk_movie_id = dim_movies.sk_movie_id",),
    ),
    Table(
        name="dim_genres",
        description="Gêneros cinematográficos (19 linhas, nomes em inglês).",
        columns=(
            Column("sk_genre_id", "TEXT PK", "Chave do gênero."),
            Column(
                "nome_genero",
                "TEXT",
                "Action, Adventure, Animation, Comedy, Crime, Documentary, Drama, Family, Fantasy, "
                "History, Horror, Music, Mystery, Romance, Science Fiction, Thriller, Tv Movie, War, Western.",
            ),
        ),
    ),
    Table(
        name="bridge_movie_genre",
        description="Ponte N:N filme <-> gênero (um filme pode ter vários gêneros).",
        columns=(
            Column("sk_movie_id", "TEXT FK", "Filme."),
            Column("sk_genre_id", "TEXT FK", "Gênero."),
        ),
        joins=(
            "bridge_movie_genre.sk_movie_id = dim_movies.sk_movie_id",
            "bridge_movie_genre.sk_genre_id = dim_genres.sk_genre_id",
        ),
    ),
    Table(
        name="dim_people",
        description="Pessoas do elenco e equipe. A mesma pessoa tem uma linha (e um sk) por papel.",
        columns=(
            Column("sk_person_id", "TEXT PK", "Chave da pessoa naquele papel."),
            Column("nome_pessoa", "TEXT", "Nome da pessoa."),
            Column("tipo_pessoa", "TEXT", "'Ator', 'Diretor' ou 'Roteirista'."),
        ),
    ),
    Table(
        name="bridge_movie_person",
        description="Ponte N:N filme <-> pessoa (elenco e equipe).",
        columns=(
            Column("sk_movie_id", "TEXT FK", "Filme."),
            Column("sk_person_id", "TEXT FK", "Pessoa (já carrega o papel via dim_people.tipo_pessoa)."),
        ),
        joins=(
            "bridge_movie_person.sk_movie_id = dim_movies.sk_movie_id",
            "bridge_movie_person.sk_person_id = dim_people.sk_person_id",
        ),
    ),
    Table(
        name="dim_companies",
        description="Produtoras/estúdios.",
        columns=(
            Column("sk_company_id", "TEXT PK", "Chave da produtora."),
            Column("nome_produtora", "TEXT", "Nome da produtora."),
        ),
    ),
    Table(
        name="bridge_movie_company",
        description="Ponte N:N filme <-> produtora.",
        columns=(
            Column("sk_movie_id", "TEXT FK", "Filme."),
            Column("sk_company_id", "TEXT FK", "Produtora."),
        ),
        joins=(
            "bridge_movie_company.sk_movie_id = dim_movies.sk_movie_id",
            "bridge_movie_company.sk_company_id = dim_companies.sk_company_id",
        ),
    ),
    Table(
        name="dim_reviews",
        description="Agregado das avaliações dos usuários por filme (1 linha por filme avaliado).",
        columns=(
            Column("sk_review_id", "TEXT PK", "Chave do agregado (igual ao sk_movie_id)."),
            Column("sk_movie_id", "TEXT FK", "Filme."),
            Column("qtd_avaliacoes_usuarios", "INTEGER", "Quantidade de avaliações de usuários do filme."),
            Column("nota_media_usuarios", "REAL", "Nota média dos usuários (0-10)."),
        ),
        joins=("dim_reviews.sk_movie_id = dim_movies.sk_movie_id",),
    ),
    Table(
        name="movie_reviews",
        description="Avaliações individuais dos usuários (nota e comentário).",
        columns=(
            Column("id", "INTEGER PK", "ID da avaliação."),
            Column("sk_movie_review_id", "TEXT", "Chave técnica da avaliação."),
            Column("sk_movie_id", "TEXT FK", "Filme."),
            Column("name", "TEXT", "Nome do usuário que avaliou."),
            Column("rating", "REAL", "Nota dada pelo usuário (0-10)."),
            Column("text", "TEXT", "Comentário/resenha."),
            Column("created_at", "TEXT", "Data/hora da avaliação."),
        ),
        joins=("movie_reviews.sk_movie_id = dim_movies.sk_movie_id",),
    ),
)

TABLES_BY_NAME: dict[str, Table] = {table.name: table for table in TABLES}
TABLE_NAMES: frozenset[str] = frozenset(TABLES_BY_NAME)

BUSINESS_RULES: dict[str, str] = {
    "dialeto": (
        "Banco SQLite. Use apenas SELECT (CTEs com WITH são permitidas). Datas são texto 'YYYY-MM-DD': "
        "use date('now'), strftime e comparações de texto. Não existe ILIKE; LIKE já ignora maiúsculas em ASCII."
    ),
    "receita": (
        "Receita = faturamento = bilheteria = arrecadação = receita_brl (em R$, padrão) ou receita_usd "
        "se o usuário pedir dólar. 'Receita informada' significa receita_brl IS NOT NULL AND receita_brl > 0."
    ),
    "lucro": (
        "lucro_brl só é confiável quando receita_brl > 0: se a receita é NULL, lucro_brl vale 0 ou -orcamento "
        "(receita desconhecida, não prejuízo real); se o orçamento é NULL, lucro_brl = receita_brl. "
        "Em análises de lucro filtre sempre receita_brl > 0."
    ),
    "margem": (
        "Margem de lucro (%) = lucro_brl * 100.0 / receita_brl, exigindo receita_brl > 0 AND orcamento_brl > 0. "
        "Retorno sobre orçamento (ROI %) = lucro_brl * 100.0 / orcamento_brl, só se o usuário pedir ROI/retorno."
    ),
    "notas": (
        "nota_imdb e nota_tmdb usam escala 0-10. nota_tmdb = 0 significa sem votos: filtre nota_tmdb > 0. "
        "Filtre nota_imdb IS NOT NULL. Quando o usuário disser só 'nota', use nota_imdb e diga isso na explicação."
    ),
    "divergencia": "Divergência entre notas = ABS(nota_a - nota_b), ordenada de forma decrescente.",
    "popularidade": "Popularidade = fact_movies_performance.popularidade (TMDB); ignore valores NULL.",
    "pessoas": (
        "Atores: dim_people.tipo_pessoa = 'Ator'; diretores: 'Diretor'; roteiristas: 'Roteirista'. "
        "Como a mesma pessoa tem um sk por papel, agrupe por nome_pessoa e conte COUNT(DISTINCT sk_movie_id). "
        "Em duplas ator-diretor, exclua a mesma pessoa nos dois papéis (ator.nome_pessoa <> diretor.nome_pessoa)."
    ),
    "periodo": (
        "'Últimos N anos' = data_lancamento >= date('now', '-N years') AND data_lancamento <= date('now'). "
        "Ano específico: ano_lancamento = AAAA."
    ),
    "generos": (
        "nome_genero está em INGLÊS: traduza o termo do usuário (ex.: 'ação' -> 'Action', 'terror' -> 'Horror', "
        "'ficção científica' -> 'Science Fiction'). Contagens por gênero usam bridge_movie_genre."
    ),
    "avaliacoes_usuarios": (
        "Avaliações de usuários: use dim_reviews (qtd_avaliacoes_usuarios, nota_media_usuarios) para rankings e "
        "médias; use movie_reviews apenas para comentários/textos ou avaliações individuais."
    ),
    "minimos": (
        "Ao comparar médias ou divergências, um mínimo de votos/avaliações evita distorções; se aplicar um "
        "mínimo não pedido pelo usuário, informe o critério na explicação."
    ),
    "apresentacao": (
        "Sempre traga colunas legíveis (titulo, nome_genero, nome_pessoa, nome_produtora) em vez de chaves sk_*. "
        "Use ROUND(x, 2) em médias e percentuais e ORDER BY coerente com a pergunta. Sem LIMIT explícito na "
        "pergunta, limite rankings a 10 linhas."
    ),
}

GENRE_TRANSLATIONS: dict[str, str] = {
    "acao": "Action",
    "aventura": "Adventure",
    "animacao": "Animation",
    "desenho": "Animation",
    "comedia": "Comedy",
    "crime": "Crime",
    "policial": "Crime",
    "documentario": "Documentary",
    "drama": "Drama",
    "familia": "Family",
    "infantil": "Family",
    "fantasia": "Fantasy",
    "historia": "History",
    "historico": "History",
    "terror": "Horror",
    "horror": "Horror",
    "musica": "Music",
    "musical": "Music",
    "misterio": "Mystery",
    "romance": "Romance",
    "romantico": "Romance",
    "ficcao cientifica": "Science Fiction",
    "sci-fi": "Science Fiction",
    "suspense": "Thriller",
    "thriller": "Thriller",
    "filme de tv": "Tv Movie",
    "telefilme": "Tv Movie",
    "guerra": "War",
    "faroeste": "Western",
    "western": "Western",
}


def render_schema(table_names: list[str] | tuple[str, ...]) -> str:
    """Renderiza as tabelas escolhidas como DDL comentado, o formato que LLMs leem melhor."""

    blocks: list[str] = []
    for name in table_names:
        table = TABLES_BY_NAME[name]
        lines = [f"-- {table.description}", f"CREATE TABLE {table.name} ("]
        lines += [f"  {col.name} {col.type},  -- {col.description}" for col in table.columns]
        lines.append(");")
        lines += [f"-- JOIN: {join}" for join in table.joins]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
