import random
from dataclasses import dataclass

from .models import BatchRequest, GenerateRequest
from .rules import apply_rules


@dataclass
class Sample:
    parameters: dict[str, str]
    warnings: list[str]
    template: int
    temperature: float | None


def sample(request: GenerateRequest, config: dict, capability: dict) -> list[Sample]:
    rng = random.Random(request.seed)
    batch = isinstance(request, BatchRequest)
    n = request.n if batch else 1
    axes = config['eixos']
    unknown = set(request.parametros) - axes.keys() - {'tema'}
    if unknown:
        raise ValueError('Parâmetros desconhecidos: ' + ', '.join(sorted(unknown)))
    strategies = request.estrategias if batch else {}
    if set(strategies) - axes.keys():
        raise ValueError('Estratégia para eixo desconhecido.')
    values, fixed, varied = {}, set(), set()
    for name, axis in axes.items():
        value = request.parametros.get(name, axis.get('padrao', 'aleatorio'))
        if value not in axis['valores'] and value not in ('aleatorio', 'variar'):
            raise ValueError(f'Valor inválido para {name}: {value}')
        if value == 'variar' and not batch:
            raise ValueError('variar só pode ser usado em lote.')
        strategy = strategies.get(name)
        if strategy == 'fixo' and value in ('aleatorio', 'variar'):
            raise ValueError(f'Escolha um valor para fixar {name}.')
        if request.modo_sorteio == 'surpreenda_me':
            value = 'aleatorio'
        elif strategy in ('aleatorio', 'variar'):
            value = strategy
        # Explicit fixed boldness is always preserved.
        if batch and not capability['suportada'] and name == 'ousadia' and name not in request.parametros:
            value = 'variar'
        if value == 'variar':
            varied.add(name)
            pool = []
            while len(pool) < n:
                cycle = list(axis['valores'])
                rng.shuffle(cycle)
                pool.extend(cycle)
            values[name] = pool[:n]
        elif value == 'aleatorio':
            weights = [axis.get('pesos', {}).get(v, 1) for v in axis['valores']]
            values[name] = rng.choices(axis['valores'], weights=weights, k=n)
        else:
            fixed.add(name)
            values[name] = [value] * n
    temperature = request.temperatura if request.temperatura is not None else capability['padrao']
    if capability['suportada'] and not capability['min'] <= temperature <= capability['max']:
        raise ValueError('Temperatura fora da faixa configurada para este modelo.')
    template_offset = rng.randrange(3)
    results = []
    for index in range(n):
        params = {name: choices[index] for name, choices in values.items()}
        params['tema'] = request.parametros.get('tema', '').strip() or 'aleatorio'
        params, warnings = apply_rules(params, fixed | varied, rng)
        temp = None
        if capability['suportada']:
            jitter = capability['jitter_lote'] if batch and request.jitter else 0
            temp = round(max(capability['min'], min(capability['max'], temperature + rng.uniform(-jitter, jitter))), 4)
        elif request.temperatura is not None:
            warnings.append('Temperatura ignorada: não habilitada para este modelo.')
        results.append(Sample(params, warnings, (template_offset + index) % 3, temp))
    return results
