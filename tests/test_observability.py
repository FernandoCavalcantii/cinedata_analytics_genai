from cinedata.observability import ligar_observabilidade


def test_sem_token_a_observabilidade_fica_desligada() -> None:
    assert ligar_observabilidade("") is False
