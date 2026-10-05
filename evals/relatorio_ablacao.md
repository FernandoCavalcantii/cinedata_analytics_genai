# Avaliação das 14 perguntas — 03/10/2026

Acerto: 8 de 14. Requisições gastas: 33.

| Categoria | Acertos | Total |
| :--- | ---: | ---: |
| Bilheteria e Finanças | 2 | 3 |
| Popularidade e Engajamento | 3 | 3 |
| Elenco e Equipe | 1 | 3 |
| Gêneros e Produtoras | 2 | 3 |
| Avaliações dos Usuários | 0 | 2 |

### top10_receita — acertou

- Categoria: Bilheteria e Finanças
- Modelo: gemini-3.5-flash-lite
- Requisições: 2
- Teto de chamadas: dentro
- Comparação: ranking equivalente
- SQL:

```sql
SELECT m.titulo, f.receita_brl
FROM dim_movies m
JOIN fact_movies_performance f ON m.sk_movie_id = f.sk_movie_id
WHERE f.receita_brl IS NOT NULL AND f.receita_brl > 0
ORDER BY f.receita_brl DESC
LIMIT 10
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
  COUNT(f.sk_movie_id) AS quantidade_filmes
FROM dim_genres g
JOIN bridge_movie_genre bg ON g.sk_genre_id = bg.sk_genre_id
JOIN fact_movies_performance f ON bg.sk_movie_id = f.sk_movie_id
WHERE f.receita_brl IS NOT NULL AND f.receita_brl > 0
GROUP BY g.nome_genero
ORDER BY lucro_medio_brl DESC
```

### maior_margem — errou

- Categoria: Bilheteria e Finanças
- Modelo: gemini-3.5-flash-lite
- Requisições: 3
- Teto de chamadas: dentro
- Comparação: referência 1: a linha 1 do ranking difere da referência; referência 2: a linha 1 do ranking difere da referência
- SQL:

```sql
SELECT 
  m.titulo,
  f.orcamento_brl,
  f.receita_brl,
  f.lucro_brl,
  ROUND((f.lucro_brl * 100.0 / f.receita_brl), 2) AS margem_lucro_percentual
FROM fact_movies_performance f
JOIN dim_movies m ON f.sk_movie_id = m.sk_movie_id
WHERE f.receita_brl IS NOT NULL 
  AND f.receita_brl > 1000000
  AND f.orcamento_brl IS NOT NULL 
  AND f.orcamento_brl > 100000
ORDER BY margem_lucro_percentual DESC
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
  p.nota_tmdb,
  p.nota_imdb,
  ROUND(ABS(p.nota_tmdb - p.nota_imdb), 2) AS divergencia
FROM dim_movies m
JOIN fact_movies_performance p ON m.sk_movie_id = p.sk_movie_id
WHERE p.nota_tmdb > 0 
  AND p.nota_imdb IS NOT NULL
  AND p.qtd_tmdb >= 50
  AND p.qtd_imdb >= 50
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
  m.ano_lancamento, 
  ROUND(AVG(p.nota_imdb), 2) AS nota_media_imdb,
  COUNT(m.sk_movie_id) AS quantidade_filmes
FROM dim_movies m
JOIN fact_movies_performance p ON m.sk_movie_id = p.sk_movie_id
WHERE p.nota_imdb IS NOT NULL 
  AND m.ano_lancamento IS NOT NULL
GROUP BY m.ano_lancamento
ORDER BY m.ano_lancamento DESC
```

### ator_cinco_anos — acertou

- Categoria: Elenco e Equipe
- Modelo: gemini-3.5-flash-lite
- Requisições: 2
- Teto de chamadas: dentro
- Comparação: ranking equivalente
- SQL:

```sql
SELECT 
    p.nome_pessoa, 
    COUNT(DISTINCT m.sk_movie_id) AS total_filmes
FROM dim_movies m
JOIN bridge_movie_person bmp ON m.sk_movie_id = bmp.sk_movie_id
JOIN dim_people p ON bmp.sk_person_id = p.sk_person_id
WHERE p.tipo_pessoa = 'Ator'
  AND m.status_filme = 'Lançado'
  AND m.data_lancamento >= date('now', '-5 years')
  AND m.data_lancamento <= date('now')
GROUP BY p.nome_pessoa
ORDER BY total_filmes DESC
LIMIT 1
```

### diretores_nota — errou

- Categoria: Elenco e Equipe
- Modelo: gemini-3.5-flash-lite
- Requisições: 2
- Teto de chamadas: dentro
- Comparação: referência 1: a linha 2 do ranking difere da referência
- SQL:

```sql
SELECT 
    p.nome_pessoa AS diretor,
    COUNT(DISTINCT m.sk_movie_id) AS qtd_filmes,
    ROUND(AVG(f.nota_imdb), 2) AS nota_media_imdb,
    ROUND(AVG(f.nota_tmdb), 2) AS nota_media_tmdb
FROM dim_people p
JOIN bridge_movie_person bmp ON p.sk_person_id = bmp.sk_person_id
JOIN dim_movies m ON bmp.sk_movie_id = m.sk_movie_id
JOIN fact_movies_performance f ON m.sk_movie_id = f.sk_movie_id
WHERE p.tipo_pessoa = 'Diretor'
  AND f.nota_imdb IS NOT NULL
GROUP BY p.sk_person_id, p.nome_pessoa
HAVING COUNT(DISTINCT m.sk_movie_id) >= 5
ORDER BY nota_media_imdb DESC
LIMIT 10
```

### dupla_ator_diretor — errou

- Categoria: Elenco e Equipe
- Modelo: 
- Requisições: 0
- Teto de chamadas: dentro
- Comparação: O agente respondeu erro sem SQL executado.
- SQL:

```sql

```

### filmes_por_genero — acertou

- Categoria: Gêneros e Produtoras
- Modelo: gemini-3.5-flash-lite
- Requisições: 2
- Teto de chamadas: dentro
- Comparação: linhas equivalentes, sem exigir a ordem
- SQL:

```sql
SELECT 
  g.nome_genero, 
  COUNT(b.sk_movie_id) AS quantidade_filmes
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
  p.nome_produtora,
  ROUND(SUM(f.lucro_brl), 2) AS lucro_total_brl,
  COUNT(DISTINCT m.sk_movie_id) AS quantidade_filmes
FROM dim_companies p
JOIN bridge_movie_company b ON p.sk_company_id = b.sk_company_id
JOIN dim_movies m ON b.sk_movie_id = m.sk_movie_id
JOIN fact_movies_performance f ON m.sk_movie_id = f.sk_movie_id
WHERE f.receita_brl IS NOT NULL AND f.receita_brl > 0
GROUP BY p.sk_company_id, p.nome_produtora
ORDER BY lucro_total_brl DESC
LIMIT 1
```

### genero_margem — errou

- Categoria: Gêneros e Produtoras
- Modelo: gemini-3.5-flash-lite
- Requisições: 3
- Teto de chamadas: dentro
- Comparação: referência 1: 5 linhas contra 1 da referência
- SQL:

```sql
SELECT 
  g.nome_genero,
  ROUND(AVG(p.lucro_brl * 100.0 / p.receita_brl), 2) AS margem_lucro_media_percentual,
  COUNT(*) AS qtd_filmes
FROM dim_genres g
JOIN bridge_movie_genre bg ON g.sk_genre_id = bg.sk_genre_id
JOIN dim_movies m ON bg.sk_movie_id = m.sk_movie_id
JOIN fact_movies_performance p ON m.sk_movie_id = p.sk_movie_id
WHERE p.receita_brl IS NOT NULL AND p.receita_brl > 0 
  AND p.orcamento_brl IS NOT NULL AND p.orcamento_brl > 0
  AND p.lucro_brl > 0
GROUP BY g.sk_genre_id, g.nome_genero
ORDER BY margem_lucro_media_percentual DESC
LIMIT 5
```

### mais_avaliados — errou

- Categoria: Avaliações dos Usuários
- Modelo: gemini-3.5-flash-lite
- Requisições: 3
- Teto de chamadas: dentro
- Comparação: referência 1: a linha 1 do ranking difere da referência
- SQL:

```sql
SELECT m.titulo, SUM(r.qtd_avaliacoes_usuarios) AS total_avaliacoes, AVG(r.nota_media_usuarios) AS media_notas
FROM dim_reviews r
JOIN dim_movies m ON r.sk_movie_id = m.sk_movie_id
GROUP BY m.titulo
ORDER BY total_avaliacoes DESC
LIMIT 10
```

### divergencia_usuarios_imdb — errou

- Categoria: Avaliações dos Usuários
- Modelo: 
- Requisições: 6
- Teto de chamadas: dentro
- Comparação: O agente respondeu erro sem SQL executado.
- SQL:

```sql

```
