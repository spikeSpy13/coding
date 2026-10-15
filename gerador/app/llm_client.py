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
    reasoning_tokens: int | None = None
    reasoning_present: bool = False
    diagnostics: dict = field(default_factory=dict)


class LLMError(Exception):
    """Sanitized error safe to persist and show in the UI."""

    def __init__(self, message, diagnostics=None):
        super().__init__(message)
        self.diagnostics = diagnostics or {}


def token_count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def error_message(code):
    return {401: 'Chave OpenRouter inválida.', 402: 'Saldo insuficiente no OpenRouter.',
            403: 'OpenRouter bloqueado ou sem permissão de acesso.', 404: 'Modelo não encontrado no OpenRouter.',
            408: 'O provedor demorou demais para responder.',
            429: 'Limite de requisições do OpenRouter atingido. Aguarde antes de gerar novamente.',
            502: 'O provedor retornou uma resposta inválida. Tente outro modelo ou aguarde.',
            503: 'Provedor indisponível. Tente outro modelo ou aguarde.'}.get(
                code, f'OpenRouter retornou erro {code or "do provedor"}. Verifique o modelo e suas configurações.')


class LLMClient(Protocol):
    async def gerar(self, prompt: str, max_tokens: int, temperatura: float | None = None) -> LLMResult: ...


class OpenRouterClient:
    def __init__(self, api_key: str, model: str, temperature_supported=False, transport=None, sleep=asyncio.sleep, reasoning='automatico'):
        self.api_key = api_key
        self.model = model
        self.temperature_supported = temperature_supported
        self.transport = transport
        self.sleep = sleep
        self.reasoning = reasoning

    async def gerar(self, prompt, max_tokens, temperatura=None):
        payload = {'model': self.model, 'max_tokens': max_tokens,
                   'messages': [{'role': 'system', 'content': 'Você escreve parágrafos em português. Entregue apenas o texto final, sem planejamento, raciocínio, análise ou comentários.'},
                                {'role': 'user', 'content': prompt}]}
        if self.temperature_supported and temperatura is not None:
            payload['temperature'] = temperatura
        if self.reasoning != 'automatico':
            payload['reasoning'] = ({'enabled': False, 'exclude': True} if self.reasoning == 'desativado' else
                                    {'effort': {'baixo': 'low', 'medio': 'medium', 'alto': 'high'}[self.reasoning], 'exclude': True})
        warnings = []
        retries = 0
        sampling_retry = False
        reasoning_retry = False
        calls = []

        def diagnostics():
            return {'chamadas': calls[:], 'raciocinio_solicitado': self.reasoning,
                    'raciocinio_enviado': payload.get('reasoning'), 'max_tokens': max_tokens,
                    'tokens_entrada': sum(c.get('tokens_entrada') or 0 for c in calls),
                    'tokens_saida': sum(c.get('tokens_saida') or 0 for c in calls),
                    'tokens_raciocinio': sum(c.get('tokens_raciocinio') or 0 for c in calls)}

        async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=15), transport=self.transport) as client:
            while True:
                try:
                    response = await client.post('https://openrouter.ai/api/v1/chat/completions',
                        headers={'Authorization': f'Bearer {self.api_key}', 'X-Title': 'Gerador de Paragrafos'}, json=payload)
                except (httpx.TransportError, httpx.TimeoutException):
                    calls.append({'tipo': 'conexao'})
                    if retries < 2:
                        await self.sleep(2 ** retries)
                        retries += 1
                        continue
                    raise LLMError('Falha de conexão com OpenRouter após 3 tentativas.', diagnostics()) from None
                try:
                    body = response.json()
                except ValueError:
                    body = None
                if not isinstance(body, dict):
                    body = {}
                error = body.get('error')
                code = error.get('code') if isinstance(error, dict) else None
                try:
                    code = int(code) if code is not None else None
                except (ValueError, TypeError):
                    code = None
                status = response.status_code if response.is_error else code
                usage = body.get('usage') if isinstance(body.get('usage'), dict) else {}
                details = usage.get('completion_tokens_details') or {}
                reasoning_tokens = token_count(details.get('reasoning_tokens')) if isinstance(details, dict) else None
                calls.append({'http_status': response.status_code, 'codigo_provedor': code,
                              'tokens_entrada': token_count(usage.get('prompt_tokens')),
                              'tokens_saida': token_count(usage.get('completion_tokens')),
                              'tokens_raciocinio': reasoning_tokens})
                if status == 400 and not sampling_retry and 'temperature' in payload and any(
                    word in response.text.lower() for word in ('temperature', 'top_p', 'top_k', 'sampling')):
                    payload.pop('temperature', None)
                    sampling_retry = True
                    self.temperature_supported = False
                    warnings.append('O modelo rejeitou a temperatura; chamada repetida sem parâmetros de amostragem.')
                    logger.warning('OpenRouter rejeitou amostragem; repetindo sem os parâmetros opcionais.')
                    continue
                if status == 400 and not reasoning_retry and 'reasoning' in payload and any(
                    word in response.text.lower() for word in ('reasoning', 'thinking', 'effort')):
                    payload.pop('reasoning')
                    reasoning_retry = True
                    warnings.append('O modelo rejeitou o controle de raciocínio; chamada repetida com o padrão do provedor.')
                    continue
                if status in (408, 429) or (status is not None and status >= 500):
                    if retries < 2:
                        delay = 2 ** retries
                        try:
                            delay = max(delay, min(float(response.headers.get('retry-after', delay)), 30))
                        except ValueError:
                            pass
                        await self.sleep(delay)
                        retries += 1
                        continue
                if response.is_error or error:
                    raise LLMError(error_message(status), diagnostics())
                try:
                    choice = body['choices'][0]
                    message = choice['message']
                    if not isinstance(message, dict):
                        raise ValueError('Invalid message')
                    text = message.get('content')
                    if text is None:
                        text = ''
                    elif isinstance(text, list):
                        text = ''.join(block['text'] for block in text if isinstance(block, dict)
                                       and block.get('type') == 'text' and isinstance(block.get('text'), str))
                    if not isinstance(text, str):
                        raise ValueError('Invalid content')
                    finish = choice.get('finish_reason')
                    if finish not in ('stop', 'length', 'max_tokens', 'content_filter', 'tool_calls', 'error', None):
                        finish = 'outro'
                    if message.get('refusal'):
                        finish = 'refusal'
                    reasoning_present = bool(message.get('reasoning') or message.get('reasoning_details') or reasoning_tokens)
                    return LLMResult(text=text.strip(), model=body.get('model') or self.model,
                        finish_reason=finish, input_tokens=diagnostics()['tokens_entrada'],
                        output_tokens=diagnostics()['tokens_saida'], temperature=payload.get('temperature'), warnings=warnings,
                        reasoning_tokens=reasoning_tokens, reasoning_present=reasoning_present, diagnostics=diagnostics())
                except (ValueError, KeyError, IndexError, TypeError):
                    raise LLMError('OpenRouter retornou uma resposta sem a estrutura esperada. Tente outro modelo.', diagnostics()) from None
