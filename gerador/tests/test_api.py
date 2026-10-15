import asyncio
import csv
import io
import json
import time

import pytest
from fastapi.testclient import TestClient

from gerador.app.config import Settings
from gerador.app.llm_client import LLMError, LLMResult
from gerador.app.main import create_app
from gerador.app.storage import Storage

TEXTS = [
    'O jardim guarda o perfume das flores durante a manhã. Os pássaros cantam entre os galhos enquanto a cidade desperta.',
    'A biblioteca recebeu uma coleção de mapas antigos do litoral. Cada desenho revela caminhos que desapareceram com as mudanças da paisagem.',
    'Na cozinha da minha avó, o pão cresce devagar sobre a mesa. Ela conhece o ponto da massa apenas pelo toque dos dedos.',
]


class FakeClient:
    def __init__(self, texts=None, delay=0):
        self.texts = texts or TEXTS
        self.calls = []
        self.budgets = []
        self.delay = delay
        self.active = 0
        self.peak = 0

    async def gerar(self, prompt, max_tokens, temperatura=None):
        index = len(self.calls)
        self.calls.append(prompt)
        self.budgets.append(max_tokens)
        self.active += 1
        self.peak = max(self.peak,self.active)
        await asyncio.sleep(self.delay)
        self.active -= 1
        value = self.texts[index % len(self.texts)]
        if isinstance(value, Exception):
            raise value
        if isinstance(value, LLMResult):
            return value
        return LLMResult(value, 'provider/test', 'stop', 15, 12, temperatura)


@pytest.fixture
def api(tmp_path):
    fake = FakeClient()
    app = create_app(Settings(db_path=str(tmp_path/'test.db')), lambda *args: fake)
    with TestClient(app) as client:
        yield client, fake, tmp_path/'test.db'


def payload(fixed, **overrides):
    return {'parametros':fixed, 'modelo':'provider/test', 'api_key':'DO-NOT-PERSIST-THIS-KEY', 'seed':5, **overrides}


def test_generate_persist_approve_export(api,fixed):
    client,fake,path = api
    result = client.post('/gerar',json=payload(fixed)).json()
    assert result['status']=='ok' and result['texto']==TEXTS[0]
    assert result['temperatura'] is None and result['tokens_saida']==12
    assert result['prompt'] and result['tentativas']
    assert client.get('/historico').json()[0]['id']==result['id']
    assert client.patch(f"/geracoes/{result['id']}",json={'aprovado':True}).json()['aprovado'] is True
    exported = client.get('/exportar?formato=jsonl').text
    assert json.loads(exported)['aprovado'] is True
    csv_rows=list(csv.DictReader(io.StringIO(client.get('/exportar?formato=csv').text)))
    assert len(csv_rows)==1 and json.loads(csv_rows[0]['parametros_finais'])==result['parametros_finais']
    assert 'DO-NOT-PERSIST' not in exported
    with Storage(path).connection() as connection:
        persisted = [tuple(row) for row in connection.execute('SELECT * FROM geracoes').fetchall()]
        assert 'DO-NOT-PERSIST' not in str(persisted)


def test_batch_history_metrics_and_balance(api,fixed):
    client,fake,_=api
    response=client.post('/gerar/lote',json=payload({**fixed,'tom':'variar'},n=3))
    assert response.status_code==200
    data=response.json()
    assert data['status']=='concluido' and data['n_ok']==3
    assert data['metricas']['n_ok']==3
    assert len(set(item['parametros_finais']['tom'] for item in data['itens']))==3
    assert 'o jardim guarda o perfume das' in fake.calls[1]
    assert client.get('/lotes/'+data['lote_id']).json()['n_processado']==3
    assert len(client.get('/historico',params={'lote_id':data['lote_id']}).json())==3
    assert 'api_key' not in data['parametros_base']
    assert 'DO-NOT-PERSIST' not in json.dumps(data)


def test_async_batch_progress(api,fixed):
    client,fake,_=api
    fake.delay=0.03
    response=client.post('/gerar/lote',json=payload(fixed,n=3,assincrono=True))
    assert response.status_code==202
    batch_id=response.json()['lote_id']
    for _ in range(100):
        data=client.get('/lotes/'+batch_id).json()
        if data['status'] not in ('pendente','processando'):
            break
        time.sleep(0.01)
    assert data['status']=='concluido' and data['n_ok']==3


def test_parallel_batch_limit(api,fixed):
    client,fake,_=api
    fake.delay=0.01
    data=client.post('/gerar/lote',json=payload(fixed,n=3,anti_repeticao=False,concorrencia=2)).json()
    assert data['n_ok']==3 and fake.peak==2


def test_parallel_duplicate_never_accepted(api,fixed):
    client,fake,_=api
    fake.texts=[TEXTS[0]]
    fake.delay=0.01
    data=client.post('/gerar/lote',json=payload(fixed,n=3,anti_repeticao=False,concorrencia=3)).json()
    assert data['n_ok']==1
    failed=[item for item in data['itens'] if item['status']=='falhou']
    assert len(failed)==2 and all(len(item['tentativas'])==3 for item in failed)


def test_validation_retry_persisted(api,fixed):
    client,fake,_=api
    fake.texts=['Título\n'+TEXTS[0],TEXTS[1]]
    data=client.post('/gerar',json=payload(fixed)).json()
    assert data['status']=='ok' and len(data['tentativas'])==2
    assert 'Corrija os problemas' in fake.calls[1]
    assert data['tokens_entrada']==30


def test_exhausted_validation_is_failed(api,fixed):
    client,fake,_=api
    fake.texts=['Texto sem pontuação']
    data=client.post('/gerar',json=payload(fixed)).json()
    assert data['status']=='falhou' and len(fake.calls)==3 and data['motivo_falha']


def test_provider_failure_saved(api,fixed):
    client,fake,_=api
    fake.texts=[LLMError('Saldo insuficiente no OpenRouter.')]
    data=client.post('/gerar',json=payload(fixed)).json()
    assert data['status']=='falhou' and 'Saldo' in data['motivo_falha']


def test_session_isolation(api,fixed):
    client,fake,_=api
    client.post('/gerar',json=payload(fixed,sessao_id='first'))
    client.post('/gerar',json=payload(fixed,sessao_id='second'))
    assert 'Não comece' not in fake.calls[1]


def test_invalid_input_never_echoes_key(api,fixed):
    client,fake,_=api
    response=client.post('/gerar',json=payload(fixed,n_historico=-1))
    assert response.status_code==422
    assert 'DO-NOT-PERSIST' not in response.text
    assert not fake.calls
    assert client.post('/gerar',json={'parametros':fixed}).status_code==422
    assert client.post('/gerar',json=payload({'tom':'invalid'})).status_code==422


def test_same_origin_and_not_found(api,fixed):
    client,_,_=api
    assert client.post('/gerar',json=payload(fixed),headers={'Origin':'https://evil.example'}).status_code==403
    assert client.get('/lotes/missing').status_code==404
    assert client.patch('/geracoes/999',json={'aprovado':False}).status_code==404


def test_capability_configurable_without_secrets(api):
    client,_,_=api
    assert client.get('/parametros').json()['temperatura']['suportada'] is False
    data=client.post('/configuracao',json={'modelo':'anything/model','temperatura_suportada':True}).json()
    assert data['temperatura']['suportada'] is True
    assert data['provedor']=='openrouter'


def test_restart_marks_unfinished_batches(tmp_path):
    path=tmp_path/'restart.db'
    storage=Storage(path)
    batch_id=storage.create_batch(10,{'parametros':{}})
    with TestClient(create_app(Settings(db_path=str(path)))) as client:
        assert client.get('/lotes/'+batch_id).json()['status']=='interrompido'


def test_truncation_retries_with_increased_budget_and_exports_diagnostics(api,fixed):
    client,fake,_=api
    fake.texts=[LLMResult('A cidade acordou enquanto', 'provider/test', 'length', 20, 800, reasoning_tokens=750),TEXTS[0]]
    data=client.post('/gerar',json=payload(fixed,max_tokens=800,teto_tokens=1600)).json()
    assert data['status']=='ok' and fake.budgets==[800,1600]
    assert data['tentativas'][0]['finish_reason']=='length'
    assert data['tentativas'][0]['tokens_raciocinio']==750
    assert data['tentativas'][1]['max_tokens']==1600
    assert '800 para 1600' in str(data['avisos'])
    assert 'tokens_raciocinio' in client.get('/exportar').text


@pytest.mark.parametrize('recover,ceiling', [(False,1600),(True,800)])
def test_exhausted_budget_not_repeated(api,fixed,recover,ceiling):
    client,fake,_=api
    fake.texts=[LLMResult('A cidade', 'provider/test', 'length', 20, 800)]
    data=client.post('/gerar',json=payload(fixed,max_tokens=800,teto_tokens=ceiling,recuperar_truncamento=recover)).json()
    assert data['status']=='falhou' and fake.budgets==[800]
    assert 'Aumente os tokens' in data['motivo_falha']


def test_empty_reasoning_only_result_can_recover(api,fixed):
    client,fake,_=api
    fake.texts=[LLMResult('', 'provider/test','length',20,800,reasoning_tokens=800,reasoning_present=True),TEXTS[0]]
    data=client.post('/gerar',json=payload(fixed,max_tokens=800)).json()
    assert data['status']=='ok' and fake.budgets==[800,1600]
    assert data['tokens_saida']==812


def test_partial_text_and_matching_prompt_survive_later_provider_error(api,fixed):
    client,fake,_=api
    fake.texts=[LLMResult('A cidade acordou enquanto', 'provider/test','length',20,800),LLMError('Provedor indisponível.')]
    data=client.post('/gerar',json=payload(fixed,max_tokens=800)).json()
    assert data['status']=='falhou'
    assert data['texto']=='A cidade acordou enquanto'
    assert data['prompt']==data['tentativas'][0]['prompt']
    assert data['tentativas'][1]['tipo']=='provedor'
    assert data['tokens_saida']==800 and data['avisos']


def test_provider_refusal_is_not_retried(api,fixed):
    client,fake,_=api
    fake.texts=[LLMResult('', 'provider/test', 'content_filter',10,0)]
    data=client.post('/gerar',json=payload(fixed)).json()
    assert data['status']=='falhou' and len(fake.calls)==1


def test_default_token_budget(api,fixed):
    client,fake,_=api
    assert client.get('/parametros').json()['padroes']['max_tokens']==4096
    client.post('/gerar',json=payload(fixed))
    assert fake.budgets==[4096]
