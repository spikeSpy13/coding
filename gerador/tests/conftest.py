import pytest

from gerador.app.config import load_parameters


@pytest.fixture
def config():
    return load_parameters()


@pytest.fixture
def capability(config):
    return {**config['temperatura'], 'suportada': False}


@pytest.fixture
def fixed():
    return {'tipo_texto': 'descricao', 'pessoa': 'terceira', 'tempo_verbal': 'presente',
            'modo_desenvolvimento': 'descricao', 'registro': 'literario', 'tom': 'neutro',
            'publico': 'adulto', 'variante': 'pt_br', 'tamanho': 'curto',
            'complexidade_sintatica': 'mista', 'vocabulario': 'medio',
            'posicao_ideia_central': 'inicio', 'tipo_paragrafo': 'padrao', 'ousadia': 'equilibrada'}
