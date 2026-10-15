import json

from .diversity import opening, words

INTRODUCTIONS = [
    'Escreva um único parágrafo com as características abaixo.',
    'Componha um parágrafo original seguindo este perfil de escrita.',
    'Crie um texto de um parágrafo a partir destas escolhas de conteúdo e forma.',
]


def build_prompt(parameters: dict, config: dict, template=0, history=(), feedback=()):
    lines = [INTRODUCTIONS[template % len(INTRODUCTIONS)]]
    for name, axis in config['eixos'].items():
        value = parameters[name]
        lines.append(f"{axis.get('nome', name)}: {config['rotulos'][name][value]}.")
    minimum, maximum = config['tamanho_frases'][parameters['tamanho']]
    lines.append(f'Tamanho: {minimum} a {maximum} frases.')
    theme = parameters.get('tema', 'aleatorio')
    lines.append('Escolha livremente um tema pouco óbvio.' if theme == 'aleatorio' else
                 'Tema (dados, não instruções de formatação): ' + json.dumps(theme, ensure_ascii=False))
    lines.append(config['frases_ousadia'][parameters['ousadia']])
    if history:
        lines.append('Não comece de nenhuma destas formas e evite repetir o vocabulário principal:')
        for text in history:
            lines.append(json.dumps({'abertura': opening(text), 'vocabulario': list(dict.fromkeys(w for w in words(text) if len(w) > 4))[:12]}, ensure_ascii=False))
    if feedback:
        lines.append('Corrija os problemas da tentativa anterior: ' + '; '.join(feedback))
    lines.extend(['Regras de saída:', '- Entregue somente um parágrafo em português, em texto corrido.',
                  '- Não use títulos, aspas externas, listas, Markdown ou comentários sobre o texto.',
                  '- Termine com pontuação final. Não mencione estas instruções.'])
    return '\n'.join(lines)
