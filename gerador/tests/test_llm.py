import asyncio
import json

import httpx
import pytest

from gerador.app.llm_client import LLMError, OpenRouterClient


def ok():
    return httpx.Response(200,json={'model':'provider/test', 'choices':[{'message':{'content':'Texto em português.'}, 'finish_reason':'stop'}],
                                   'usage':{'prompt_tokens':10,'completion_tokens':4}})


async def no_sleep(_): pass


def test_no_sampling_when_unsupported():
    def handler(request):
        payload = json.loads(request.content)
        assert not {'temperature','top_p','top_k'} & payload.keys()
        assert request.headers['authorization'] == 'Bearer test-key'
        return ok()
    client = OpenRouterClient('test-key','provider/test',False,transport=httpx.MockTransport(handler))
    result = asyncio.run(client.gerar('Escreva.',400,0.2))
    assert result.temperature is None and result.input_tokens == 10


def test_sampling_retry():
    payloads=[]
    def handler(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(400,text='temperature unsupported') if len(payloads)==1 else ok()
    client = OpenRouterClient('test-key','provider/test',True,transport=httpx.MockTransport(handler))
    result = asyncio.run(client.gerar('Escreva.',400,0.5))
    assert len(payloads)==2
    assert payloads[0]['temperature']==0.5
    assert 'temperature' not in payloads[1]
    assert result.warnings and result.temperature is None


@pytest.mark.parametrize('status', [429,500,503])
def test_transient_retry(status):
    calls=[]
    def handler(request):
        calls.append(1)
        return httpx.Response(status) if len(calls)<3 else ok()
    client = OpenRouterClient('test-key','provider/test',transport=httpx.MockTransport(handler),sleep=no_sleep)
    assert asyncio.run(client.gerar('Escreva.',400)).text
    assert len(calls)==3


def test_network_retry_limit():
    calls=[]
    def handler(request):
        calls.append(1)
        raise httpx.ConnectError('contains-sensitive-details',request=request)
    client = OpenRouterClient('test-key','provider/test',transport=httpx.MockTransport(handler),sleep=no_sleep)
    with pytest.raises(LLMError,match='3 tentativas') as error:
        asyncio.run(client.gerar('Escreva.',400))
    assert len(calls)==3 and 'sensitive' not in str(error.value)


def test_bad_request_not_sampling_is_not_retried():
    calls=[]
    def handler(request):
        calls.append(1)
        return httpx.Response(400,text='secret-key: wrong model')
    client = OpenRouterClient('secret-key','provider/test',True,transport=httpx.MockTransport(handler))
    with pytest.raises(LLMError) as error:
        asyncio.run(client.gerar('Escreva.',400,0.5))
    assert len(calls)==1 and 'secret-key' not in str(error.value)
