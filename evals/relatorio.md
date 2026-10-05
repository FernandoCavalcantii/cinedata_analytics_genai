# Avaliação das 14 perguntas — 02/10/2026

Acerto: 14 de 14. Requisições gastas: 46.

A soma das perguntas abaixo é 31. As outras 15 são da primeira passagem das perguntas que foram repetidas.

| Categoria | Acertos | Total |
| :--- | ---: | ---: |
| Bilheteria e Finanças | 3 | 3 |
| Popularidade e Engajamento | 3 | 3 |
| Elenco e Equipe | 3 | 3 |
| Gêneros e Produtoras | 3 | 3 |
| Avaliações dos Usuários | 2 | 2 |

### top10_receita — acertou

- Categoria: Bilheteria e Finanças
- Modelo: gemini-3.5-flash-lite
- Requisições: 2
- Teto de chamadas: dentro
- Comparação: ranking equivalente
- SQL:

```sql
SELECT m.titulo, f.receita_brl FROM dim_movies m JOIN fact_movies_performance f ON m.sk_movie_id = f.sk_movie_id WHERE f.receita_brl IS NOT NULL ORDER BY f.receita_brl DESC LIMIT 10
```

### lucro_medio_genero — acertou

- Categoria: Bilheteria e Finanças
- Modelo: gemini-3.5-flash-lite
- Requisições: 2
- Teto de chamadas: dentro
- Comparação: linhas equivalentes, sem exigir a ordem
- SQL:

```sql
SELECT 
  g.nome_genero,
  ROUND(AVG(f.lucro_brl), 2) AS lucro_medio_brl,
  COUNT(m.sk_movie_id) AS quantidade_filmes
FROM dim_movies m
JOIN bridge_movie_genre bg ON m.sk_movie_id = bg.sk_movie_id
JOIN dim_genres g ON bg.sk_genre_id = g.sk_genre_id
JOIN fact_movies_performance f ON m.sk_movie_id = f.sk_movie_id
WHERE f.receita_brl IS NOT NULL AND f.receita_brl > 0
GROUP BY g.nome_genero
ORDER BY lucro_medio_brl DESC
```

### maior_margem — acertou

- Categoria: Bilheteria e Finanças
- Modelo: gemini-3.5-flash-lite
- Requisições: 2
- Teto de chamadas: dentro
- Comparação: coincidiu com a referência 1
- SQL:

```sql
SELECT 
  m.titulo,
  p.orcamento_brl,
  p.receita_brl,
  p.lucro_brl,
  ROUND(p.lucro_brl * 100.0 / p.receita_brl, 2) AS margem_lucro_pct
FROM fact_movies_performance p
JOIN dim_movies m ON p.sk_movie_id = m.sk_movie_id
WHERE p.receita_brl IS NOT NULL AND p.receita_brl > 0
  AND p.orcamento_brl IS NOT NULL AND p.orcamento_brl > 0
ORDER BY margem_lucro_pct DESC
LIMIT 10
```

### cinco_populares — acertou

- Categoria: Popularidade e Engajamento
- Modelo: gemini-3.5-flash-lite
- Requisições: 2
- Teto de chamadas: dentro
- Comparação: ranking equivalente
- SQL:

```sql
SELECT m.titulo, p.popularidade 
FROM dim_movies m 
JOIN fact_movies_performance p ON m.sk_movie_id = p.sk_movie_id 
WHERE p.popularidade IS NOT NULL 
ORDER BY p.popularidade DESC 
LIMIT 5
```

### divergencia_tmdb_imdb — acertou

- Categoria: Popularidade e Engajamento
- Modelo: gemini-3.5-flash-lite
- Requisições: 2
- Teto de chamadas: dentro
- Comparação: coincidiu com a referência 3
- SQL:

```sql
SELECT 
  m.titulo, 
  f.nota_tmdb, 
  f.nota_imdb, 
  ROUND(ABS(f.nota_tmdb - f.nota_imdb), 2) AS divergencia 
FROM dim_movies m 
JOIN fact_movies_performance f ON m.sk_movie_id = f.sk_movie_id 
WHERE f.nota_tmdb > 0 
  AND f.nota_imdb IS NOT NULL 
  AND f.qtd_tmdb >= 50 
  AND f.qtd_imdb >= 50 
ORDER BY divergencia DESC 
LIMIT 10
```

### nota_media_por_ano — acertou

- Categoria: Popularidade e Engajamento
- Modelo: gemini-3.5-flash-lite
- Requisições: 2
- Teto de chamadas: dentro
- Comparação: linhas equivalentes, sem exigir a ordem
- SQL:

```sql
SELECT 
  d.ano_lancamento, 
  ROUND(AVG(f.nota_imdb), 2) AS nota_media_imdb,
  COUNT(d.sk_movie_id) AS quantidade_filmes
FROM dim_movies d
JOIN fact_movies_performance f ON d.sk_movie_id = f.sk_movie_id
WHERE f.nota_imdb IS NOT NULL 
  AND d.ano_lancamento IS NOT NULL
GROUP BY d.ano_lancamento
ORDER BY d.ano_lancamento DESC
```

### ator_cinco_anos — acertou

- Categoria: Elenco e Equipe
- Modelo: gemini-3.5-flash-lite
- Requisições: 2
- Teto de chamadas: dentro
- Comparação: ranking equivalente
- SQL:

```sql
SELECT p.nome_pessoa AS ator, COUNT(DISTINCT m.sk_movie_id) AS quantidade_filmes
FROM dim_movies m
JOIN bridge_movie_person bmp ON m.sk_movie_id = bmp.sk_movie_id
JOIN dim_people p ON bmp.sk_person_id = p.sk_person_id
WHERE p.tipo_pessoa = 'Ator'
  AND m.status_filme = 'Lançado'
  AND m.data_lancamento >= date('now', '-5 years')
  AND m.data_lancamento <= date('now')
GROUP BY p.nome_pessoa
ORDER BY quantidade_filmes DESC
LIMIT 1
```

### diretores_nota — acertou

- Categoria: Elenco e Equipe
- Modelo: gemini-3.5-flash-lite
- Requisições: 2
- Teto de chamadas: dentro
- Comparação: ranking equivalente
- SQL:

```sql
SELECT 
  p.nome_pessoa AS diretor,
  COUNT(DISTINCT m.sk_movie_id) AS qtd_filmes,
  ROUND(AVG(f.nota_imdb), 2) AS nota_media_imdb
FROM dim_movies m
JOIN bridge_movie_person bp ON m.sk_movie_id = bp.sk_movie_id
JOIN dim_people p ON bp.sk_person_id = p.sk_person_id
JOIN fact_movies_performance f ON m.sk_movie_id = f.sk_movie_id
WHERE p.tipo_pessoa = 'Diretor' 
  AND f.nota_imdb IS NOT NULL
GROUP BY p.nome_pessoa
HAVING COUNT(DISTINCT m.sk_movie_id) >= 5
ORDER BY nota_media_imdb DESC
LIMIT 10
```

### dupla_ator_diretor — acertou

- Categoria: Elenco e Equipe
- Modelo: gemini-3.5-flash-lite
- Requisições: 4
- Teto de chamadas: dentro
- Comparação: ranking equivalente
- SQL:

```sql
SELECT 
  p_ator.nome_pessoa AS ator, 
  p_dir.nome_pessoa AS diretor, 
  COUNT(DISTINCT m.sk_movie_id) AS total_filmes
FROM dim_movies m
JOIN bridge_movie_person b_ator ON m.sk_movie_id = b_ator.sk_movie_id
JOIN dim_people p_ator ON b_ator.sk_person_id = p_ator.sk_person_id AND p_ator.tipo_pessoa = 'Ator'
JOIN bridge_movie_person b_dir ON m.sk_movie_id = b_dir.sk_movie_id
JOIN dim_people p_dir ON b_dir.sk_person_id = p_dir.sk_person_id AND p_dir.tipo_pessoa = 'Diretor'
WHERE p_ator.nome_pessoa <> p_dir.nome_pessoa
GROUP BY p_ator.nome_pessoa, p_dir.nome_pessoa
ORDER BY total_filmes DESC
LIMIT 1
```

### filmes_por_genero — acertou

- Categoria: Gêneros e Produtoras
- Modelo: gemini-3.5-flash-lite
- Requisições: 2
- Teto de chamadas: dentro
- Comparação: linhas equivalentes, sem exigir a ordem
- SQL:

```sql
SELECT g.nome_genero, COUNT(b.sk_movie_id) AS quantidade_filmes
FROM dim_genres g
JOIN bridge_movie_genre b ON g.sk_genre_id = b.sk_genre_id
GROUP BY g.nome_genero
ORDER BY quantidade_filmes DESC
```

### produtora_lucro — acertou

- Categoria: Gêneros e Produtoras
- Modelo: gemini-3.5-flash-lite
- Requisições: 2
- Teto de chamadas: dentro
- Comparação: ranking equivalente
- SQL:

```sql
SELECT 
    c.nome_produtora,
    ROUND(SUM(p.lucro_brl), 2) AS lucro_total_brl,
    COUNT(m.sk_movie_id) AS qtd_filmes
FROM dim_companies c
JOIN bridge_movie_company b ON c.sk_company_id = b.sk_company_id
JOIN dim_movies m ON b.sk_movie_id = m.sk_movie_id
JOIN fact_movies_performance p ON m.sk_movie_id = p.sk_movie_id
WHERE p.receita_brl IS NOT NULL AND p.receita_brl > 0
GROUP BY c.sk_company_id, c.nome_produtora
ORDER BY lucro_total_brl DESC
LIMIT 1
```

### genero_margem — acertou

- Categoria: Gêneros e Produtoras
- Modelo: gemini-3.5-flash-lite
- Requisições: 2
- Teto de chamadas: dentro
- Comparação: ranking equivalente
- SQL:

```sql
SELECT 
  g.nome_genero,
  ROUND(SUM(f.lucro_brl) * 100.0 / SUM(f.receita_brl), 2) AS margem_lucro_percentual
FROM dim_genres g
JOIN bridge_movie_genre bg ON g.sk_genre_id = bg.sk_genre_id
JOIN dim_movies m ON bg.sk_movie_id = m.sk_movie_id
JOIN fact_movies_performance f ON m.sk_movie_id = f.sk_movie_id
WHERE f.receita_brl > 0 AND f.orcamento_brl > 0
GROUP BY g.nome_genero
ORDER BY margem_lucro_percentual DESC
LIMIT 1
```

### mais_avaliados — acertou

- Categoria: Avaliações dos Usuários
- Modelo: gemini-3.5-flash-lite
- Requisições: 3
- Teto de chamadas: dentro
- Comparação: ranking equivalente
- SQL:

```sql
WITH normalized AS (
  SELECT
    m.sk_movie_id,
    m.titulo,
    r.qtd_avaliacoes_usuarios,
    r.nota_media_usuarios,
    TRIM(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LOWER(m.titulo), ':', ' '), '-', ' '), '.', ' '), ',', ' '), '  ', ' '), '  ', ' '), '  ', ' '), '  ', ' '), '  ', ' '), '  ', ' ')) AS norm_titulo
  FROM dim_movies m
  JOIN dim_reviews r ON m.sk_movie_id = r.sk_movie_id
),
canonical_titles AS (
  SELECT
    norm_titulo,
    titulo AS main_titulo,
    SUM(qtd_avaliacoes_usuarios) AS total_avaliacoes,
    ROUND(SUM(qtd_avaliacoes_usuarios * nota_media_usuarios) / NULLIF(SUM(qtd_avaliacoes_usuarios), 0), 2) AS nota_media_ponderada
  FROM normalized
  GROUP BY norm_titulo
),
ranked_titles AS (
  SELECT
    ct.norm_titulo,
    ct.main_titulo AS titulo,
    ct.total_avaliacoes AS qtd_avaliacoes_usuarios,
    ct.nota_media_ponderada AS nota_media_usuarios,
    ROW_NUMBER() OVER (PARTITION BY ct.norm_titulo ORDER BY n.qtd_avaliacoes_usuarios DESC) AS rn
  FROM canonical_titles ct
  JOIN normalized n ON ct.norm_titulo = n.norm_titulo
)
SELECT titulo, qtd_avaliacoes_usuarios, nota_media_usuarios
FROM ranked_titles
WHERE rn = 1
ORDER BY qtd_avaliacoes_usuarios DESC
LIMIT 10

```

### divergencia_usuarios_imdb — acertou

- Categoria: Avaliações dos Usuários
- Modelo: gemini-3.5-flash-lite
- Requisições: 2
- Teto de chamadas: dentro
- Comparação: ranking equivalente
- SQL:

```sql
WITH cleaned AS (
  SELECT
    TRIM(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(m.titulo, ':', ' '), '-', ' '), '.', ' '), ',', ' '), '  ', ' '), '  ', ' '), '  ', ' '), '  ', ' '), '  ', ' '), '  ', ' ')) AS titulo_limpo,
    m.titulo,
    r.nota_media_usuarios,
    f.nota_imdb,
    r.qtd_avaliacoes_usuarios,
    f.qtd_imdb
  FROM dim_movies m
  JOIN fact_movies_performance f ON m.sk_movie_id = f.sk_movie_id
  JOIN dim_reviews r ON m.sk_movie_id = r.sk_movie_id
  WHERE r.nota_media_usuarios IS NOT NULL
    AND f.nota_imdb IS NOT NULL
    AND r.qtd_avaliacoes_usuarios >= 5
    AND f.qtd_imdb >= 5
),
grouped AS (
  SELECT
    titulo_limpo,
    MAX(titulo) AS titulo_original,
    AVG(nota_media_usuarios) AS nota_media_usuarios,
    AVG(nota_imdb) AS nota_imdb,
    ABS(AVG(nota_media_usuarios) - AVG(nota_imdb)) AS divergencia
  FROM cleaned
  GROUP BY titulo_limpo
)
SELECT
  titulo_original AS titulo,
  ROUND(nota_media_usuarios, 2) AS nota_media_usuarios,
  ROUND(nota_imdb, 2) AS nota_imdb,
  ROUND(divergencia, 2) AS divergencia
FROM grouped
ORDER BY divergencia DESC
LIMIT 10

```
