import asyncio
import logging
from dataclasses import dataclass, field
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)


@dataclass
class LLMResult:
    text: str
    model: str
    finish_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    temperature: float | None = None
    warnings: list[str] = field(default_factory=list)


class LLMError(Exception):
    """Sanitized error safe to persist and show in the UI."""


class LLMClient(Protocol):
    async def gerar(self, prompt: str, max_tokens: int, temperatura: float | None = None) -> LLMResult: ...


class OpenRouterClient:
    def __init__(self, api_key: str, model: str, temperature_supported=False, transport=None, sleep=asyncio.sleep):
        self.api_key = api_key
        self.model = model
        self.temperature_supported = temperature_supported
        self.transport = transport
        self.sleep = sleep

    async def gerar(self, prompt, max_tokens, temperatura=None):
        payload = {'model': self.model, 'max_tokens': max_tokens,
                   'messages': [{'role': 'system', 'content': 'Você escreve parágrafos em português e segue o formato solicitado.'},
                                {'role': 'user', 'content': prompt}]}
        if self.temperature_supported and temperatura is not None:
            payload['temperature'] = temperatura
        warnings = []
        retries = 0
        sampling_retry = False
        async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=15), transport=self.transport) as client:
            while True:
                try:
                    response = await client.post('https://openrouter.ai/api/v1/chat/completions',
                        headers={'Authorization': f'Bearer {self.api_key}', 'X-Title': 'Gerador de Paragrafos'}, json=payload)
                except (httpx.TransportError, httpx.TimeoutException):
                    if retries < 2:
                        await self.sleep(2 ** retries)
                        retries += 1
                        continue
                    raise LLMError('Falha de conexão com OpenRouter após 3 tentativas.') from None
                if response.status_code == 400 and not sampling_retry and 'temperature' in payload and any(
                    word in response.text.lower() for word in ('temperature', 'top_p', 'top_k', 'sampling')):
                    payload.pop('temperature', None)
                    sampling_retry = True
                    self.temperature_supported = False
                    warnings.append('O modelo rejeitou a temperatura; chamada repetida sem parâmetros de amostragem.')
                    logger.warning('OpenRouter rejeitou amostragem; repetindo sem os parâmetros opcionais.')
                    continue
                if response.status_code == 429 or response.status_code >= 500:
                    if retries < 2:
                        delay = 2 ** retries
                        try:
                            delay = max(delay, min(float(response.headers.get('retry-after', delay)), 30))
                        except ValueError:
                            pass
                        await self.sleep(delay)
                        retries += 1
                        continue
                if response.is_error:
                    messages = {401: 'Chave OpenRouter inválida.', 402: 'Saldo insuficiente no OpenRouter.',
                                403: 'OpenRouter bloqueado ou sem permissão de acesso.', 404: 'Modelo não encontrado no OpenRouter.',
                                429: 'Limite de requisições do OpenRouter atingido.'}
                    raise LLMError(messages.get(response.status_code, f'OpenRouter respondeu com HTTP {response.status_code}. Verifique o modelo e suas configurações.'))
                try:
                    body = response.json()
                    if body.get('error'):
                        raise LLMError('OpenRouter retornou erro do provedor. Verifique o modelo selecionado.')
                    choice = body['choices'][0]
                    text = choice['message']['content']
                    if not isinstance(text, str):
                        raise ValueError('Invalid content')
                    usage = body.get('usage') or {}
                    return LLMResult(text=text.strip(), model=body.get('model') or self.model,
                        finish_reason=choice.get('finish_reason'), input_tokens=usage.get('prompt_tokens'),
                        output_tokens=usage.get('completion_tokens'), temperature=payload.get('temperature'), warnings=warnings)
                except (ValueError, KeyError, IndexError, TypeError):
                    raise LLMError('OpenRouter não retornou um texto utilizável.') from None
