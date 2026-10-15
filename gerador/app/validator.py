import re

from langdetect import DetectorFactory, LangDetectException, detect_langs

DetectorFactory.seed = 0


def sentence_count(text):
    # Protect frequent Portuguese abbreviations and decimal numbers.
    clean = re.sub(r'\b(?:sr|sra|dr|dra|prof|profa|etc|ex|art|pág)\.', lambda m: m[0].replace('.', '∯'), text, flags=re.I)
    clean = re.sub(r'(?<=\d)\.(?=\d)', '∯', clean)
    return len(re.findall(r'[.!?…]+(?:[”»\"\')\]]*)(?=\s|$)', clean))


def validate(text: str, size: str, config: dict, finish_reason: str | None = None) -> list[str]:
    errors = []
    stripped = text.strip()
    if not stripped:
        return ['Texto vazio.']
    if '\n' in stripped or '\r' in stripped:
        errors.append('Use apenas um parágrafo sem título ou quebras de linha.')
    if re.match(r'^(?:#{1,6}\s|[-*•]\s|\d+[.)]\s|aqui (?:está|esta|vai)|t[íi]tulo\s*:|par[áa]grafo\s*:)', stripped, re.I):
        errors.append('Remova título, marcadores ou prefixo explicativo.')
    if stripped.startswith(('"', '“', '«', '```')):
        errors.append('Remova aspas externas ou blocos Markdown.')
    minimum, maximum = config['tamanho_frases'][size]
    count = sentence_count(stripped)
    if not max(1, minimum - 1) <= count <= maximum + 1:
        errors.append(f'Número de frases inválido: {count}; esperado {minimum}–{maximum}, tolerância de 1.')
    if finish_reason in ('length', 'max_tokens') or not re.search(r'[.!?][”»\"\')\]]*$', stripped) or stripped.endswith('...'):
        errors.append('Texto possivelmente truncado ou sem pontuação final.')
    try:
        languages = detect_langs(stripped)
        if not any(lang.lang == 'pt' and lang.prob >= 0.5 for lang in languages):
            errors.append('O texto não foi identificado como português.')
    except LangDetectException:
        errors.append('Não foi possível identificar o idioma.')
    return errors
