import asyncio
import logging
import weakref

from .config import temperature_capability
from .diversity import metrics, too_similar
from .llm_client import LLMError, OpenRouterClient
from .prompt_builder import build_prompt
from .sampler import sample
from .validator import validate

logger = logging.getLogger(__name__)


class Generator:
    def __init__(self, settings, config, storage, client_factory=None):
        self.settings, self.config, self.storage = settings, config, storage
        self.client_factory = client_factory
        self.locks = weakref.WeakValueDictionary()
        self.capacity = asyncio.Semaphore(20)

    def session_lock(self, session):
        lock = self.locks.get(session)
        if lock is None:
            lock = asyncio.Lock()
            self.locks[session] = lock
        return lock

    def prepare(self, request):
        model = request.modelo or self.settings.model
        key = request.api_key.get_secret_value().strip() if request.api_key else self.settings.api_key
        if not model:
            raise ValueError('Escolha ou adicione um modelo OpenRouter na página.')
        if not key:
            raise ValueError('Informe sua chave OpenRouter na página.')
        if len(key) > 1000 or not key.isascii() or any(char.isspace() or ord(char) < 32 for char in key):
            raise ValueError('A chave contém caracteres inválidos. Cole apenas a chave OpenRouter.')
        capability = temperature_capability(self.config, model, self.settings)
        if request.temperatura_suportada is not None:
            capability['suportada'] = request.temperatura_suportada
        samples = sample(request, self.config, capability)
        client = (self.client_factory(key, model, capability['suportada']) if self.client_factory else
                  OpenRouterClient(key, model, capability['suportada'], reasoning=request.raciocinio))
        return samples, client

    async def single(self, request, samples, client):
        if request.anti_repeticao:
            async with self.session_lock(request.sessao_id):
                return await self.generate(request, samples[0], client)
        return await self.generate(request, samples[0], client)

    async def generate(self, request, selected, client, batch_id=None, index=None, accepted=None):
        warnings = list(selected.warnings)
        attempts, feedback = [], []
        text, reason, prompt, actual_model = '', None, '', request.modelo or self.settings.model
        temp = None
        input_tokens, output_tokens = 0, 0
        budget = request.max_tokens
        ceiling = max(budget, request.teto_tokens)
        last_prompt = ''
        for attempt in range(3):
            history = []
            if request.anti_repeticao and request.n_historico:
                history = [row['texto'] for row in reversed(self.storage.history(request.n_historico, session_id=request.sessao_id, ok_only=True))]
            # Include all accepted batch items for deduplication, even with anti-repetition disabled.
            comparison = list(dict.fromkeys(history + (accepted or [])))
            prompt = build_prompt(selected.parameters, self.config, selected.template + attempt,
                                  history=history, feedback=feedback)
            try:
                async with self.capacity:
                    result = await client.gerar(prompt, budget, selected.temperature)
            except LLMError as error:
                reason = str(error)
                input_tokens += error.diagnostics.get('tokens_entrada', 0)
                output_tokens += error.diagnostics.get('tokens_saida', 0)
                attempts.append({'prompt': prompt, 'texto': '', 'motivos': [reason], 'tipo': 'provedor',
                                 'max_tokens': budget, 'diagnostico': error.diagnostics})
                if text:
                    warnings.append('A última resposta parcial foi preservada; uma tentativa posterior falhou no provedor.')
                break
            text, actual_model, temp = result.text, result.model, result.temperature
            last_prompt = prompt
            warnings.extend(w for w in result.warnings if w not in warnings)
            input_tokens += result.input_tokens or 0
            output_tokens += result.output_tokens or 0
            feedback = validate(text, selected.parameters['tamanho'], self.config, result.finish_reason)
            if result.reasoning_present and not text:
                feedback.append('O provedor informou raciocínio, mas não entregou um parágrafo final.')
            if result.finish_reason in ('tool_calls', 'error'):
                feedback.append('O provedor encerrou sem uma resposta final utilizável.')
            # Re-read the shared list after awaiting the model. No await between check and acceptance.
            comparison = list(dict.fromkeys(comparison + (accepted or [])))
            if too_similar(text, comparison, request.limiar_similaridade):
                feedback.append('Texto semelhante a um anterior; use outra abertura, vocabulário e imagens.')
            attempts.append({'prompt': prompt, 'texto': text, 'motivos': feedback[:],
                             'temperatura': temp, 'modelo': actual_model,
                             'tokens_entrada': result.input_tokens, 'tokens_saida': result.output_tokens,
                             'finish_reason': result.finish_reason, 'max_tokens': budget,
                             'tokens_raciocinio': result.reasoning_tokens, 'raciocinio_presente': result.reasoning_present,
                             'diagnostico': result.diagnostics})
            if not feedback:
                reason = None
                if accepted is not None:
                    accepted.append(text)
                break
            reason = '; '.join(feedback)
            if result.finish_reason in ('refusal', 'content_filter'):
                break
            final_call = result.diagnostics.get('chamadas', [{}])[-1]
            used_tokens = final_call.get('tokens_saida') if result.diagnostics.get('chamadas') else result.output_tokens
            exhausted = result.finish_reason in ('length', 'max_tokens') or (
                (used_tokens or 0) >= budget * 0.95 and (not text or any('truncado' in error for error in feedback)))
            if exhausted:
                if request.recuperar_truncamento and budget < ceiling and attempt < 2:
                    next_budget = min(ceiling, budget * 2)
                    warnings.append(f'Resposta cortada: orçamento da próxima tentativa aumentado de {budget} para {next_budget} tokens.')
                    budget = next_budget
                else:
                    hint = 'Limite de saída atingido. Aumente os tokens ou reduza o raciocínio nos ajustes; não repetimos o mesmo orçamento esgotado.'
                    reason += ' ' + hint
                    attempts[-1]['motivos'].append(hint)
                    break
        item = self.storage.save({
            'lote_id': batch_id, 'indice': index, 'sessao_id': request.sessao_id,
            'parametros': selected.parameters, 'modo_sorteio': request.modo_sorteio,
            'temperatura': temp, 'prompt': last_prompt or prompt, 'texto': text,
            'status': 'falhou' if reason else 'ok', 'motivo_falha': reason,
            'modelo': actual_model, 'tokens_entrada': input_tokens, 'tokens_saida': output_tokens,
            'avisos': warnings, 'tentativas': attempts,
            'metadados': {'seed': request.seed, 'anti_repeticao': request.anti_repeticao,
                          'n_historico': request.n_historico, 'max_tokens': request.max_tokens,
                          'recuperar_truncamento': request.recuperar_truncamento,
                          'teto_tokens': ceiling, 'raciocinio': request.raciocinio,
                          'modelo_solicitado': request.modelo or self.settings.model,
                          'limiar_similaridade': request.limiar_similaridade,
                          'temperatura_suportada': request.temperatura_suportada},
        })
        if batch_id:
            self.storage.update_batch(batch_id, 'processando')
        return item

    async def batch(self, batch_id, request, samples, client):
        self.storage.update_batch(batch_id, 'processando')
        accepted = []
        try:
            if request.anti_repeticao:
                async with self.session_lock(request.sessao_id):
                    for index, selected in enumerate(samples):
                        await self.generate(request, selected, client, batch_id, index, accepted)
            else:
                semaphore = asyncio.Semaphore(min(request.concorrencia, 20))

                async def one(index, selected):
                    async with semaphore:
                        await self.generate(request, selected, client, batch_id, index, accepted)

                # TaskGroup waits for/cancels siblings before the batch can be marked terminal.
                async with asyncio.TaskGroup() as group:
                    for index, selected in enumerate(samples):
                        group.create_task(one(index, selected))
            data = self.storage.batch(batch_id)
            self.storage.update_batch(batch_id, 'concluido', metrics(data['itens']))
        except asyncio.CancelledError:
            self.storage.update_batch(batch_id, 'interrompido', error='Processamento interrompido. Itens concluídos foram preservados.')
            raise
        except Exception:
            logger.error('Falha interna ao processar lote; detalhes e credenciais não registrados.')
            self.storage.update_batch(batch_id, 'falhou', error='Falha interna ao processar o lote.')
        return self.storage.batch(batch_id)
