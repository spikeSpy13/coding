"""OpenRouter speech synthesis. Audio and credentials are never written to disk."""
from dataclasses import dataclass
from email.message import Message
import io
import wave

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class SpeechRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    texto: str = Field(min_length=1, max_length=12000)
    modelo: str = Field(min_length=1, max_length=200)
    voz: str = Field(default='', max_length=120)
    velocidade: float = Field(default=1, ge=0.5, le=2, allow_inf_nan=False)
    api_key: SecretStr | None = Field(default=None, exclude=True)

    @field_validator('texto', 'modelo', 'voz')
    @classmethod
    def strip_values(cls, value, info):
        value = value.strip()
        if info.field_name != 'voz' and not value:
            raise ValueError('Preencha este campo.')
        if info.field_name == 'modelo' and ('/' not in value or any(c.isspace() for c in value)):
            raise ValueError('Informe o identificador provedor/modelo de síntese de voz.')
        return value


class SpeechError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


@dataclass
class SpeechAudio:
    content: bytes
    media_type: str = 'audio/mpeg'


def pcm_to_wav(content: bytes, content_type: str, *, gemini: bool = False) -> SpeechAudio:
    """Wrap signed 16-bit little-endian PCM using the provider's audio metadata."""
    header = Message()
    header['content-type'] = content_type
    try:
        # Gemini documents 24 kHz mono; other providers must supply their format.
        rate = int(header.get_param('rate', '24000' if gemini else '0'))
        channels = int(header.get_param('channels', '1' if gemini else '0'))
        if not 8000 <= rate <= 192000 or channels not in (1, 2):
            raise ValueError
        if not content or len(content) % (2 * channels):
            raise ValueError
    except (TypeError, ValueError):
        raise SpeechError('O provedor retornou áudio PCM vazio, incompleto ou com formato inválido.') from None
    output = io.BytesIO()
    with wave.open(output, 'wb') as audio:
        audio.setnchannels(channels)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(content)
    return SpeechAudio(output.getvalue(), 'audio/wav')


class OpenRouterSpeechClient:
    def __init__(self, transport=None):
        self.transport = transport

    async def synthesize(self, request: SpeechRequest, api_key: str) -> SpeechAudio:
        gemini = request.modelo.startswith('google/gemini-') and '-tts' in request.modelo
        payload = {'model': request.modelo, 'input': request.texto, 'response_format': 'pcm' if gemini else 'mp3'}
        if request.voz:
            payload['voice'] = request.voz
        elif gemini:
            payload['voice'] = 'Kore'
        # Some providers reject speed overrides. Omit the field at its default value.
        if request.velocidade != 1 and not gemini:
            payload['speed'] = request.velocidade
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=15), transport=self.transport) as client:
                async with client.stream('POST', 'https://openrouter.ai/api/v1/audio/speech',
                    headers={'Authorization': f'Bearer {api_key}', 'X-Title': 'Gerador de Paragrafos'}, json=payload) as response:
                    if response.is_error:
                        messages = {
                            400: 'O modelo rejeitou a configuração de voz. Confira modelo e voz; tente velocidade 1.',
                            401: 'Chave OpenRouter inválida. Confira a chave no topo da página.',
                            402: 'Saldo insuficiente no OpenRouter para gerar o áudio.',
                            403: 'Sem permissão para acessar a síntese de voz no OpenRouter.',
                            404: 'Modelo de voz não encontrado. Escolha um modelo TTS disponível no OpenRouter.',
                            413: 'O parágrafo ultrapassa o limite de texto deste modelo de voz.',
                            429: 'Limite de requisições de voz atingido. Aguarde e tente novamente.',
                        }
                        raise SpeechError(messages.get(response.status_code, 'O provedor de voz está indisponível. Tente novamente mais tarde.'),
                                          response.status_code if response.status_code in messages else 502)
                    content_type = response.headers.get('content-type', '')
                    media = content_type.split(';')[0].strip().lower()
                    if media not in ('audio/mpeg', 'audio/mp3', 'audio/pcm', 'application/octet-stream'):
                        raise SpeechError('O provedor não retornou áudio em um formato reconhecido. Confira o modelo de voz.')
                    audio = bytearray()
                    async for chunk in response.aiter_bytes():
                        audio.extend(chunk)
                        if len(audio) > 20 * 1024 * 1024:
                            raise SpeechError('O áudio excedeu o limite de 20 MB. Use um parágrafo menor.')
                    if media == 'audio/pcm' or (gemini and media == 'application/octet-stream'):
                        return pcm_to_wav(bytes(audio), content_type, gemini=gemini)
                    if not (audio.startswith(b'ID3') or (len(audio) >= 2 and audio[0] == 255 and audio[1] & 224 == 224)):
                        raise SpeechError('O provedor retornou áudio vazio ou em formato inválido.')
                    return SpeechAudio(bytes(audio))
        except httpx.TimeoutException:
            raise SpeechError('O provedor de voz demorou demais para responder. Tente novamente.', 504) from None
        except httpx.TransportError:
            raise SpeechError('Não foi possível conectar ao OpenRouter para gerar o áudio.') from None
