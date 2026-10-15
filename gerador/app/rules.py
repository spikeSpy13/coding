from dataclasses import dataclass
from random import Random


@dataclass(frozen=True)
class Rule:
    conditions: dict[str, str]
    target: str
    choices: tuple[str, ...]
    message: str


RULES = [
    Rule({'tipo_texto': 'instrucao', 'pessoa': 'primeira'}, 'pessoa', ('segunda', 'impessoal'), 'Instruções combinam melhor com segunda pessoa ou voz impessoal.'),
    Rule({'tipo_texto': 'relato', 'pessoa': 'impessoal'}, 'pessoa', ('primeira',), 'Relatos pessoais pedem primeira pessoa.'),
    Rule({'tipo_texto': 'relato', 'tempo_verbal': 'futuro'}, 'tempo_verbal', ('passado',), 'Relatos de experiência pedem passado.'),
    Rule({'registro': 'tecnico', 'tom': 'bem_humorado'}, 'tom', ('neutro', 'serio'), 'Registro técnico e tom bem-humorado podem conflitar.'),
    Rule({'publico': 'crianca', 'vocabulario': 'rico'}, 'vocabulario', ('simples',), 'Para crianças, prefira vocabulário simples.'),
    Rule({'publico': 'crianca', 'complexidade_sintatica': 'complexa'}, 'complexidade_sintatica', ('simples',), 'Para crianças, prefira sintaxe simples.'),
    Rule({'tipo_paragrafo': 'transicao', 'tamanho': 'longo'}, 'tamanho', ('curto',), 'Parágrafos de transição devem ser curtos.'),
    Rule({'tipo_paragrafo': 'enfase'}, 'tamanho', ('curto',), 'Parágrafos de ênfase devem ser curtos.'),
]


def apply_rules(parameters: dict, protected: set, rng: Random):
    result, warnings = dict(parameters), []
    for rule in RULES:
        if all(result.get(key) == value for key, value in rule.conditions.items()) and result.get(rule.target) not in rule.choices:
            if rule.target in protected:
                warnings.append(rule.message + f' Mantido {rule.target} fixado ou balanceado no lote.')
            else:
                before = result[rule.target]
                result[rule.target] = rng.choice(rule.choices)
                warnings.append(f'{rule.target}: {before} → {result[rule.target]}. {rule.message}')
    return result, warnings
