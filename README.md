# CineData Analytics GenAI

Agente Text-to-SQL para o catálogo de filmes da CineData Analytics (Rocket Lab 2026.2).

## Subir a API

Na raiz do projeto, com o `.env` preenchido e o banco em `cinerocket-db/cinerocket (1).db`:

```bash
docker compose up --build
```

A API fica em `http://127.0.0.1:8000`. A documentação interativa fica em `http://127.0.0.1:8000/docs`.

O banco é montado somente leitura em `/app/data/cinerocket.db`. A imagem não copia o `.env` nem o arquivo `.db`.

No Windows, ler o banco direto do disco do host pode ser lento. Se `/health` demorar, copie o arquivo uma vez para um volume do Docker e aponte `CINEROCKET_DB_PATH` para ele.

O CI instala com `pip`, sem lock de versões. A versão do PydanticAI no GitHub Actions pode divergir da que está na máquina de desenvolvimento. No Windows o `uvicorn` entra sem o extra `standard`, porque o `uvloop` não existe naquele sistema.
