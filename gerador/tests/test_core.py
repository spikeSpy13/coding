from collections import Counter
from random import Random

import pytest

from gerador.app.diversity import metrics, similarity, too_similar
from gerador.app.models import BatchRequest, GenerateRequest
from gerador.app.prompt_builder import build_prompt
from gerador.app.rules import RULES, apply_rules
from gerador.app.sampler import sample
from gerador.app.validator import validate, sentence_count


def test_reproducible(config, capability):
    request = BatchRequest(n=24, seed=12, parametros={'tipo_texto': 'variar', 'tom': 'variar'})
    assert sample(request, config, capability) == sample(request, config, capability)
    changed = request.model_copy(update={'seed': 13})
    assert sample(changed, config, capability) != sample(request, config, capability)


@pytest.mark.parametrize('n', [1, 8, 24, 27])
def test_balanced_after_rules(config, capability, n):
    request = BatchRequest(n=n, seed=1, parametros={name:'variar' for name in config['eixos']})
    samples = sample(request, config, capability)
    for axis, definition in config['eixos'].items():
        counts = Counter(result.parameters[axis] for result in samples)
        sizes = [counts[value] for value in definition['valores']]
        assert max(sizes) - min(sizes) <= 1


def test_fixed_batch_preserved(config, capability, fixed):
    fixed.update(publico='crianca', vocabulario='rico', tipo_paragrafo='enfase', tamanho='longo')
    for result in sample(BatchRequest(n=4, parametros=fixed), config, capability):
        assert all(result.parameters[key] == value for key,value in fixed.items())
        assert result.warnings


@pytest.mark.parametrize('rule', RULES)
def test_rules_adjust_and_preserve(rule, fixed):
    values = {**fixed, **rule.conditions}
    if values[rule.target] in rule.choices:
        values[rule.target] = 'longo'
    adjusted, warnings = apply_rules(values, set(), Random(1))
    assert adjusted[rule.target] in rule.choices
    protected, warnings = apply_rules(values, set(values), Random(1))
    assert protected == values
    assert warnings


def test_surprise_retains_theme(config, capability, fixed):
    request = GenerateRequest(parametros={**fixed, 'tema':'Os barcos'}, modo_sorteio='surpreenda_me', seed=37)
    result = sample(request, config, capability)[0]
    assert result.parameters['tema'] == 'Os barcos'
    assert any(result.parameters[key] != value for key,value in fixed.items())


@pytest.mark.parametrize('parameters', [{'tamanho':'enorme'}, {'inexistente':'x'}, {'tom':'variar'}])
def test_reject_invalid_parameters(config, capability, parameters):
    with pytest.raises(ValueError):
        sample(GenerateRequest(parametros=parameters),config,capability)


def test_temperature_omission_and_jitter(config, capability):
    request = BatchRequest(n=20, temperatura=1, jitter=True, seed=42)
    assert all(item.temperature is None for item in sample(request,config,capability))
    temps = [item.temperature for item in sample(request,config,{**capability,'suportada':True})]
    assert all(0 <= temp <= 1 for temp in temps)
    assert len(set(temps)) > 1


def test_prompt_contains_all_parameters(config,fixed):
    params = {**fixed, 'tema':'Rios urbanos'}
    prompts = [build_prompt(params,config,index,history=['O velho barco atravessava o rio lentamente.']) for index in range(3)]
    assert len(set(prompts)) == 3
    for prompt in prompts:
        for axis, value in fixed.items():
            assert config['rotulos'][axis][value] in prompt
        assert 'Rios urbanos' in prompt and 'o velho barco atravessava o rio' in prompt


VALID = 'O jardim guarda o perfume das flores durante a manhã. Os pássaros cantam entre os galhos enquanto a cidade desperta.'


def test_valid_paragraph(config):
    assert validate(VALID, 'curto', config) == []
    assert sentence_count('O dr. Silva trabalha aqui. Ele chega às 8.30 horas.') == 2


@pytest.mark.parametrize('text', ['', 'Título\n'+VALID, 'Aqui está o parágrafo: '+VALID, '- '+VALID,
                                  VALID+'\n\n'+VALID, '"'+VALID+'"', VALID*6,
                                  'The garden is filled with flowers every morning. Birds are singing in the trees while the city wakes up.', VALID[:-1]])
def test_invalid_paragraph(config,text):
    assert validate(text,'curto',config)


def test_truncation(config):
    assert validate(VALID,'curto',config,'length')


def test_similarity():
    assert similarity(VALID, VALID.upper()) == 1
    assert too_similar(VALID,[VALID],0.4)
    assert not too_similar(VALID,['Uma receita de bolo exige farinha, açúcar e muita atenção ao forno.'],0.4)


def test_metrics(fixed):
    result = metrics([{'texto':VALID, 'status':'ok','parametros_finais':fixed},
                      {'texto':'', 'status':'falhou','parametros_finais':fixed}])
    assert result['n_ok'] == 1 and result['n_falhou'] == 1
    assert result['aberturas_unicas'] == 1
    assert result['comprimento']['media'] > 10
    assert result['contagem_parametros']['tom'] == {'neutro':2}


def test_history_does_not_ban_theme_words(config,fixed):
    prompt=build_prompt({**fixed,'tema':'morte'},config,history=['A morte atravessou a cidade durante a madrugada.'])
    entry=__import__('json').loads(next(line for line in prompt.splitlines() if line.startswith('{')))
    assert 'morte' not in entry['vocabulario']
    assert 'não uma lista de palavras proibidas' in prompt


def test_reasoning_leak_is_rejected(config):
    errors=validate('We need to produce a single paragraph. '+VALID,'curto',config)
    assert any('planejamento' in error for error in errors)
