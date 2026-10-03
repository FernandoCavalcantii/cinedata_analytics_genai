"""O YAML das regras só cita tabelas e colunas que existem no catálogo e no banco."""

import re

from cinedata.agent.retriever import ALWAYS_RULES, CONCEPTS
from cinedata.db.catalog import BUSINESS_RULES, TABLE_NAMES, TABLES
from cinedata.knowledge import carregar_exemplos, carregar_regras

IDENTIFICADORES = re.compile(r"\b[a-z][a-z0-9]*_[a-z0-9_]+\b")


def test_yaml_cobre_as_regras_que_o_retriever_pede():
    regras = carregar_regras()
    pedidas = set(ALWAYS_RULES)
    for concept in CONCEPTS:
        pedidas.update(concept.rules)
    assert pedidas <= set(regras)
    assert regras == BUSINESS_RULES


def test_yaml_so_cita_tabelas_e_colunas_reais():
    colunas = {coluna.name for tabela in TABLES for coluna in tabela.columns}
    conhecidos = colunas | set(TABLE_NAMES)
    texto = "\n".join(carregar_regras().values())
    for exemplo in carregar_exemplos():
        texto += "\n" + exemplo["sql"]
    desconhecidos = sorted(token for token in set(IDENTIFICADORES.findall(texto)) if token not in conhecidos)
    assert desconhecidos == []


def test_tabelas_citadas_existem_no_banco(db) -> None:
    texto = "\n".join(carregar_regras().values())
    citadas = [nome for nome in TABLE_NAMES if nome in texto]
    assert citadas
    for nome in citadas:
        db.execute(f"SELECT 1 FROM {nome} LIMIT 1")
