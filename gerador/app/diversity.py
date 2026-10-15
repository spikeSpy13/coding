import re
import statistics
import unicodedata
from collections import Counter


def words(text: str) -> list[str]:
    return re.findall(r'[^\W\d_]+', unicodedata.normalize('NFC', text).casefold(), re.UNICODE)


def opening(text: str, n=6) -> str:
    return ' '.join(words(text)[:n])


def similarity(left: str, right: str) -> float:
    a, b = words(left), words(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    size = min(3, len(a), len(b))
    first = {tuple(a[i:i + size]) for i in range(len(a) - size + 1)}
    second = {tuple(b[i:i + size]) for i in range(len(b) - size + 1)}
    return len(first & second) / len(first | second)


def too_similar(text: str, history: list[str], threshold=0.4) -> bool:
    return any(words(text) == words(previous) or similarity(text, previous) > threshold for previous in history)


def metrics(items: list[dict]) -> dict:
    accepted = [item for item in items if item['status'] == 'ok']
    tokens = [word for item in accepted for word in words(item['texto'])]
    lengths = [len(words(item['texto'])) for item in accepted]
    counts = {}
    for item in items:
        for name, value in item['parametros_finais'].items():
            counts.setdefault(name, Counter())[value] += 1
    return {
        'n_ok': len(accepted), 'n_falhou': len(items) - len(accepted),
        'aberturas_unicas': len({opening(item['texto']) for item in accepted}) / len(accepted) if accepted else 0,
        'diversidade_lexical': len(set(tokens)) / len(tokens) if tokens else 0,
        'comprimento': {'unidade': 'palavras', 'media': statistics.mean(lengths) if lengths else 0,
                        'desvio': statistics.pstdev(lengths) if lengths else 0},
        'contagem_parametros': {key: dict(value) for key, value in counts.items()},
    }
