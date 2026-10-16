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


GEMINI = 'google/gemini-3.8-flash-lite-tts'


@pytest.mark.parametrize('voice', ['', 'Puck'])
def test_gemini_requests_pcm_with_explicit_voice_and_wraps_real_frames(voice):
    import io
    import wave
    pcm = b'\x00\x00\xff\x7f\x00\x80' * 100
    def handler(request):
        assert json.loads(request.content) == {
            'model': GEMINI, 'input': TEXT, 'response_format': 'pcm', 'voice': voice or 'Kore',
        }
        return httpx.Response(200, content=pcm, headers={'content-type':'audio/pcm;rate=24000;channels=1'})
    client = OpenRouterSpeechClient(httpx.MockTransport(handler))
    result = asyncio.run(client.synthesize(SpeechRequest(texto=TEXT, modelo=GEMINI, voz=voice, velocidade=1.5), KEY))
    assert result.media_type == 'audio/wav'
    with wave.open(io.BytesIO(result.content)) as audio:
        assert audio.getframerate() == 24000 and audio.getnchannels() == 1
        assert audio.getsampwidth() == 2
        assert audio.readframes(audio.getnframes()) == pcm


@pytest.mark.parametrize('media,rate,channels', [
    ('audio/pcm;rate=22050;channels=2',22050,2),
    ('audio/pcm',24000,1),
    ('application/octet-stream',24000,1),
])
def test_gemini_honors_pcm_metadata_and_documented_defaults(media,rate,channels):
    import io
    import wave
    client = OpenRouterSpeechClient(httpx.MockTransport(lambda request:httpx.Response(200,content=b'\0'*100,headers={'content-type':media})))
    result = asyncio.run(client.synthesize(SpeechRequest(texto=TEXT,modelo=GEMINI),KEY))
    with wave.open(io.BytesIO(result.content)) as audio:
        assert audio.getframerate() == rate and audio.getnchannels() == channels
        assert audio.readframes(audio.getnframes()) == b'\0'*100


@pytest.mark.parametrize('content,media', [
    (b'', 'audio/pcm'), (b'\0', 'audio/pcm'),
    (b'\0'*4, 'audio/pcm;rate=0;channels=1'),
    (b'\0'*4, 'audio/pcm;rate=24000;channels=90'),
    (b'\0'*4, 'audio/pcm;rate=broken;channels=1'),
])
def test_rejects_empty_or_malformed_pcm(content,media):
    client = OpenRouterSpeechClient(httpx.MockTransport(lambda request:httpx.Response(200,content=content,headers={'content-type':media})))
    with pytest.raises(SpeechError,match='PCM'):
        asyncio.run(client.synthesize(SpeechRequest(texto=TEXT,modelo=GEMINI),KEY))


def test_unknown_pcm_provider_requires_rate_and_channels():
    with pytest.raises(SpeechError,match='PCM'):
        synthesize(lambda request:httpx.Response(200,content=b'\0'*4,headers={'content-type':'audio/pcm'}))


def test_gemini_api_returns_wav_filename_and_no_cache(tmp_path):
    client = OpenRouterSpeechClient(httpx.MockTransport(lambda request:httpx.Response(200,content=b'\0'*100,headers={'content-type':'audio/pcm;rate=24000;channels=1'})))
    app = create_app(Settings(db_path=str(tmp_path/'test.db')),speech_client=client)
    with TestClient(app) as api:
        response = api.post('/audio/ler',json={'texto':TEXT,'modelo':GEMINI,'api_key':KEY})
        assert response.status_code == 200
        assert response.headers['content-type'] == 'audio/wav'
        assert response.headers['content-disposition'] == 'inline; filename="paragrafo.wav"'
        assert response.headers['cache-control'] == 'no-store'
        assert response.content[:4] == b'RIFF' and response.content[8:12] == b'WAVE'
