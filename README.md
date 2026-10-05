<a name="readme-top"></a>

# CineData Analytics GenAI

Perguntas em português sobre o catálogo de filmes da CineData. Quem não escreve SQL recebe a resposta em texto, com a tabela quando o banco devolve linhas.

## Para rodar

O caminho previsto para a correção é o Docker. São três coisas: Docker com Compose, o arquivo `cinerocket.db` da camada Gold, e pelo menos uma chave de modelo no `.env`.

Na pasta do projeto:

```bash
mkdir -p "cinerocket-db"
cp /caminho/do/cinerocket.db "cinerocket-db/cinerocket (1).db"
cp .env.example .env
```

Abra o `.env`. Basta uma chave do Gemini para o chat responder. Várias chaves vão na mesma linha, separadas por vírgula, na ordem em que devem ser tentadas. Chave vazia é ignorada. Chave repetida entra uma vez só.

```bash
GEMINI_API_KEYS=AIza-chave-da-conta-1,AIza-chave-da-conta-2
GEMINI_MODEL=gemini-3.5-flash-lite
```

Se a primeira chave falha (cota, erro ou tempo), ela fica de lado por cinco minutos e a próxima entra. Esgotadas as chaves do Gemini, a pergunta segue para o OpenRouter, se `OPENROUTER_API_KEY` estiver preenchida. Os modelos dessa reserva ficam em `OPENROUTER_MODELS`, também separados por vírgula. O padrão tenta `nvidia/nemotron-3.5-lightning:free` e, se o pool gratuito estiver lotado, `openrouter/free`. A conta gratuita do OpenRouter tem teto de 50 requisições por dia, e uma pergunta pode gastar mais de uma chamada. Sem chave do OpenRouter, o agente usa só o Gemini.

`LOGFIRE_TOKEN` é opcional. Vazio, a API sobe e não envia rastreamento. Preenchido, as chamadas do agente aparecem no projeto Logfire dessa conta. Não é necessário para corrigir nem para usar o chat.

```bash
docker compose up -d --build
```

- Chat: http://localhost:5173
- API: http://localhost:8000 (`/docs` e `GET /health`)

`GET /health` devolve `banco: true` quando o SQLite foi encontrado e `provedor: true` quando há chave no `.env`.

Na primeira subida a imagem é construída. Nas seguintes, `docker compose up -d` basta. `docker compose down` para os containers. O banco fica no seu disco, montado só para leitura. A imagem não guarda o `.env` nem o `.db`.

Uma pergunta igual a outra já respondida vem do cache e não chama o modelo. O funcionamento está em [Cache](#cache).

<p align="right"><a href="#readme-top">voltar ao topo</a></p>

<details>
  <summary>Sumário</summary>
  <ol>
    <li><a href="#sobre-o-projeto">Sobre o projeto</a></li>
    <li><a href="#chat">Chat</a></li>
    <li><a href="#terminal">Terminal</a></li>
    <li><a href="#cache">Cache</a></li>
    <li><a href="#o-que-perguntar">O que perguntar</a></li>
    <li><a href="#sem-docker">Sem Docker</a></li>
    <li><a href="#tecnologias">Tecnologias</a></li>
  </ol>
</details>

## Sobre o projeto

O agente lê a camada Gold em SQLite e responde perguntas de bilheteria, popularidade, elenco, gêneros e avaliações de usuários. A consulta é só `SELECT`. Antes de chegar ao banco, o SQL passa por uma checagem de leitura. O modelo escreve a consulta, vê as linhas e redige a resposta com esses números.

A ordem dos modelos é a do `.env`: cada chave do Gemini, e depois cada modelo do OpenRouter. As regras de negócio (moeda, margem, piso de votos, grafia de título) ficam em `src/cinedata/knowledge/regras.yaml`.

<p align="right"><a href="#readme-top">voltar ao topo</a></p>

## Chat

O serviço `web` do Compose serve a interface em http://localhost:5173 e fala com a API em http://localhost:8000.

A tela abre com as 14 perguntas do edital. Dá para clicar numa delas ou escrever outra no campo de baixo. A resposta mostra:

1. O texto em linguagem natural.
2. A tabela, quando a consulta devolve linhas. Se o modelo indicar um gráfico de barras, as barras aparecem junto.
3. **Como cheguei nesse número**, fechado até o clique. É a justificativa da conta.
4. **SQL**, também fechado até o clique.

A conversa segue na mesma sessão: a pergunta seguinte enxerga a anterior. Modelo, quantidade de chamadas e tempo ficam fora da tela. Esses dados continuam no JSON da API, em `POST /api/v1/perguntas`.

<p align="right"><a href="#readme-top">voltar ao topo</a></p>

## Terminal

O mesmo agente atende pelo comando `cinedata`, sem abrir o navegador. Com os containers no ar:

```bash
docker compose run --rm api cinedata
```

Escreva a pergunta e pressione Enter. A resposta sai em texto, com a explicação, o SQL e a tabela. No rodapé aparecem o modelo, as requisições gastas, o tempo e se a resposta veio do cache.

Comandos, escritos sozinhos e confirmados com Enter:

- `instrucoes`, `ajuda`, `help` ou `?` mostra o texto de uso.
- `limpar` apaga as respostas guardadas. A mesma pergunta volta a consultar o modelo.
- `csv` grava a última tabela em `resultado.csv`.
- `sair`, `exit` ou `quit` encerra.

`docker compose run --rm api cinedata --limpar-cache` apaga o cache e sai. `cinedata --conversa um-nome` continua uma conversa identificada por esse nome nesta sessão.

<p align="right"><a href="#readme-top">voltar ao topo</a></p>

## Cache

O cache evita gastar cota do Gemini ou do OpenRouter com uma pergunta que já foi respondida. Não há um número máximo de perguntas: cada acerto com SQL entra no arquivo e permanece até alguém limpar o cache ou até as regras e o catálogo mudarem.

A chave é o texto da pergunta, já sem diferença de maiúsculas, acentos e espaços repetidos. “Filmes mais avaliados pelos usuários” e “filmes mais avaliados pelos usuarios” são a mesma entrada. Uma frase diferente, mesmo que parecida, consulta o modelo de novo.

Quando há acerto, a API devolve a resposta guardada com zero requisições ao modelo. Só entra no cache uma resposta com status certo e com SQL. Erro e pergunta fora do catálogo não são reaproveitados.

No Docker o arquivo fica em `/tmp/respostas.json`, dentro do container da API. Ele dura enquanto esse container existir. `docker compose down` apaga o container e, com ele, o cache. No uso sem Docker o arquivo é `.cache/respostas.json`, na raiz do projeto.

Para esvaziar, no terminal: `limpar`, ou `docker compose run --rm api cinedata --limpar-cache`. `AGENT_CACHE_ENABLED=false` no `.env` desliga o recurso.

Isso é separado da memória da conversa. A memória guarda as últimas 3 perguntas da sessão atual para a frase seguinte fazer sentido (“e em dólar?”). Ela some quando o processo da API reinicia. O cache não some por isso.

<p align="right"><a href="#readme-top">voltar ao topo</a></p>

## O que perguntar

As frases abaixo estão no chat. Servem para a correção e também para `POST /api/v1/perguntas`.

**Bilheteria e finanças.** Top 10 filmes com maior receita em R$. Lucro médio por gênero, só com receita informada. Filmes com maior margem de lucro, entre os que têm receita e orçamento.

**Popularidade.** Os 5 filmes mais populares. Filmes com maior divergência entre a nota TMDB e a nota IMDb. Nota média IMDb por ano de lançamento.

**Elenco.** Ator com mais participações em filmes lançados nos últimos 5 anos. Diretores com maior nota média, mínimo de 5 filmes. Dupla ator-diretor que mais trabalhou junta.

**Gêneros e produtoras.** Quantidade de filmes por gênero. Produtora com maior lucro total. Gênero com maior margem de lucro média.

**Avaliações dos usuários.** Filmes mais avaliados pelos usuários. Filmes em que a nota média dos usuários mais diverge da nota IMDb.

Receita, faturamento e bilheteria são a mesma medida. O padrão é real. Se a pergunta pedir dólar, a consulta usa as colunas em USD.

<p align="right"><a href="#readme-top">voltar ao topo</a></p>

## Sem Docker

Python 3.11 ou superior. Node.js 20 para o chat. O banco pode ficar em `cinerocket.db` na raiz, em `data/cinerocket.db` ou em `cinerocket-db/`. O `.env` é o mesmo da seção [Para rodar](#para-rodar).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cinedata
```

A API, em outro terminal, com o mesmo ambiente ativo:

```bash
cinedata-api
```

O chat, em um terceiro terminal:

```bash
cd frontend
npm install
npm run dev
```

A interface fica em http://localhost:5173 e procura a API em http://127.0.0.1:8000.

Os testes não chamam o modelo:

```bash
pytest
```

<p align="right"><a href="#readme-top">voltar ao topo</a></p>

## Tecnologias

**Agente.** Python, PydanticAI, Gemini e OpenRouter.

**API.** FastAPI.

**Banco.** SQLite da camada Gold, somente leitura.

**Chat.** React, TypeScript e Vite.

**Execução.** Docker Compose.

<p align="right"><a href="#readme-top">voltar ao topo</a></p>
