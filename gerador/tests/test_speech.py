import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from gerador.app.config import Settings
from gerador.app.main import create_app
from gerador.app.speech import OpenRouterSpeechClient, SpeechError, SpeechRequest

TEXT = 'O jardim floresce pela manhã. As crianças brincam perto da fonte.'
MP3 = b'ID3\x04\x00\x00test-audio'
KEY = 'PRIVATE-TEST-CREDENTIAL'


def synthesize(handler, **overrides):
    client = OpenRouterSpeechClient(httpx.MockTransport(handler))
    return asyncio.run(client.synthesize(SpeechRequest(texto=TEXT, modelo='provider/tts', **overrides), KEY))


def test_exact_text_and_speech_endpoint():
    def handler(request):
        assert str(request.url) == 'https://openrouter.ai/api/v1/audio/speech'
        assert request.headers['Authorization'] == f'Bearer {KEY}'
        assert json.loads(request.content) == {
            'model': 'provider/tts', 'input': TEXT, 'response_format': 'mp3', 'voice': 'voice-pt', 'speed': 1.25,
        }
        return httpx.Response(200, content=MP3, headers={'content-type': 'audio/mpeg'})
    result = synthesize(handler, voz='voice-pt', velocidade=1.25)
    assert result.content == MP3 and result.media_type == 'audio/mpeg'


def test_defaults_omit_optional_provider_fields():
    def handler(request):
        assert set(json.loads(request.content)) == {'model', 'input', 'response_format'}
        return httpx.Response(200, content=MP3, headers={'content-type': 'application/octet-stream'})
    assert synthesize(handler).content == MP3


@pytest.mark.parametrize('status', [400, 401, 402, 403, 404, 413, 429, 500])
def test_provider_errors_are_sanitized_without_paid_retries(status):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={'error': {'message': KEY}})
    with pytest.raises(SpeechError) as exc:
        synthesize(handler)
    assert KEY not in str(exc.value)
    assert exc.value.status == (502 if status == 500 else status)
    assert len(calls) == 1


@pytest.mark.parametrize('body,media', [(b'', 'audio/mpeg'), (b'not audio', 'audio/mpeg'), (MP3, 'application/json')])
def test_rejects_invalid_audio(body, media):
    with pytest.raises(SpeechError):
        synthesize(lambda request: httpx.Response(200, content=body, headers={'content-type': media}))


def test_timeout_sanitized():
    def handler(request):
        raise httpx.ReadTimeout(KEY)
    with pytest.raises(SpeechError) as exc:
        synthesize(handler)
    assert exc.value.status == 504 and KEY not in str(exc.value)


def test_size_limit():
    with pytest.raises(SpeechError, match='20 MB'):
        synthesize(lambda request: httpx.Response(200, content=b'ID3' + b'0' * (20*1024*1024), headers={'content-type': 'audio/mpeg'}))


def test_audio_api_no_history_or_key_storage(tmp_path):
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(200, content=MP3, headers={'content-type': 'audio/mpeg'})
    app = create_app(Settings(db_path=str(tmp_path/'test.db')), speech_client=OpenRouterSpeechClient(httpx.MockTransport(handler)))
    with TestClient(app) as api:
        payload = {'texto': TEXT, 'modelo': 'provider/tts', 'api_key': KEY}
        response = api.post('/audio/ler', json=payload)
        assert response.status_code == 200 and response.content == MP3
        assert response.headers['content-type'] == 'audio/mpeg'
        assert response.headers['cache-control'] == 'no-store'
        assert api.get('/historico').json() == []
        assert api.post('/audio/ler', json={**payload, 'api_key': None}).status_code == 422
        assert api.post('/audio/ler', json={**payload, 'api_key': 'bad\nkey'}).status_code == 422
        invalid = api.post('/audio/ler', json={**payload, 'velocidade': 99})
        assert invalid.status_code == 422 and KEY not in invalid.text
        assert len(seen) == 1
    assert KEY.encode() not in (tmp_path/'test.db').read_bytes()


def test_server_key_fallback_and_api_error(tmp_path):
    def handler(request):
        assert request.headers['Authorization'] == f'Bearer {KEY}'
        return httpx.Response(401, json={'error': KEY})
    app = create_app(Settings(db_path=str(tmp_path/'test.db'), api_key=KEY), speech_client=OpenRouterSpeechClient(httpx.MockTransport(handler)))
    with TestClient(app) as api:
        response = api.post('/audio/ler', json={'texto': TEXT, 'modelo': 'provider/tts'})
        assert response.status_code == 401 and KEY not in response.text


@pytest.mark.parametrize('override', [{'texto':' '}, {'modelo':'chat-model'}, {'velocidade':0}, {'voz':'v'*121}])
def test_invalid_configuration(override):
    with pytest.raises(ValueError):
        SpeechRequest(**{'texto':TEXT, 'modelo':'provider/tts', **override})
