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


def test_empty_content_preserves_reasoning_usage_without_exposing_reasoning():
    body={'choices':[{'message':{'content':None,'reasoning':'private reasoning text'},'finish_reason':'length'}],
          'usage':{'prompt_tokens':20,'completion_tokens':800,'completion_tokens_details':{'reasoning_tokens':796}}}
    client=OpenRouterClient('test-key','provider/test',transport=httpx.MockTransport(lambda r:httpx.Response(200,json=body)))
    result=asyncio.run(client.gerar('Escreva.',800))
    assert result.text=='' and result.finish_reason=='length'
    assert result.output_tokens==800 and result.reasoning_tokens==796 and result.reasoning_present
    assert 'private reasoning' not in str(result)


@pytest.mark.parametrize('mode,expected', [('desativado',{'enabled':False,'exclude':True}),('baixo',{'effort':'low','exclude':True})])
def test_optional_reasoning_controls(mode,expected):
    def handler(request):
        assert json.loads(request.content)['reasoning']==expected
        return ok()
    client=OpenRouterClient('test-key','provider/test',transport=httpx.MockTransport(handler),reasoning=mode)
    asyncio.run(client.gerar('Escreva.',4096))


def test_reasoning_fallback():
    bodies=[]
    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(400,json={'error':{'message':'reasoning unsupported'}}) if len(bodies)==1 else ok()
    client=OpenRouterClient('test-key','provider/test',transport=httpx.MockTransport(handler),reasoning='baixo')
    result=asyncio.run(client.gerar('Escreva.',4096))
    assert 'reasoning' in bodies[0] and 'reasoning' not in bodies[1]
    assert result.warnings and len(result.diagnostics['chamadas'])==2


def test_automatic_reasoning_does_not_send_override():
    def handler(request):
        assert 'reasoning' not in json.loads(request.content)
        return ok()
    client=OpenRouterClient('test-key','provider/test',transport=httpx.MockTransport(handler))
    asyncio.run(client.gerar('Escreva.',4096))


def test_embedded_provider_error_retried_and_diagnosed_without_raw_body():
    client=OpenRouterClient('secret-key','provider/test',transport=httpx.MockTransport(
        lambda r:httpx.Response(200,json={'error':{'code':429,'message':'Bearer secret-key'}})),sleep=no_sleep)
    with pytest.raises(LLMError) as error:
        asyncio.run(client.gerar('Escreva.',4096))
    assert len(error.value.diagnostics['chamadas'])==3
    assert error.value.diagnostics['chamadas'][0]['codigo_provedor']==429
    assert 'secret-key' not in str(error.value)+str(error.value.diagnostics)


def test_text_blocks_are_read_but_reasoning_blocks_are_not():
    body={'choices':[{'message':{'content':[{'type':'reasoning','text':'Not output'}, {'type':'text','text':'Texto final.'}]},'finish_reason':'stop'}]}
    client=OpenRouterClient('key','provider/test',transport=httpx.MockTransport(lambda r:httpx.Response(200,json=body)))
    assert asyncio.run(client.gerar('Escreva.',4096)).text=='Texto final.'
