import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    db_path: str = str(ROOT / 'data' / 'gerador.db')
    api_key: str = ''
    model: str = ''
    max_tokens: int = 800
    concurrency: int = 5
    similarity_threshold: float = 0.4
    async_threshold: int = 10
    temperature_supported: bool | None = None

    @classmethod
    def from_env(cls):
        load_dotenv(ROOT / '.env')
        temp = os.getenv('LLM_TEMPERATURE_SUPPORTED')
        settings = cls(
            db_path=os.getenv('DB_PATH', cls.db_path),
            api_key=os.getenv('OPENROUTER_API_KEY', ''),
            model=os.getenv('LLM_MODEL', ''),
            max_tokens=int(os.getenv('MAX_TOKENS', '800')),
            concurrency=int(os.getenv('CONCORRENCIA_LOTE', '5')),
            similarity_threshold=float(os.getenv('LIMIAR_SIMILARIDADE', '0.4')),
            temperature_supported=None if temp is None else temp.lower() == 'true',
        )
        if not 1 <= settings.concurrency <= 20 or not 100 <= settings.max_tokens <= 16000:
            raise ValueError('CONCORRENCIA_LOTE deve ser 1–20; MAX_TOKENS, 100–16000.')
        if not 0 <= settings.similarity_threshold <= 1:
            raise ValueError('LIMIAR_SIMILARIDADE deve estar entre 0 e 1.')
        return settings


def load_parameters(path: Path | None = None):
    with (path or ROOT / 'app' / 'parameters.yaml').open(encoding='utf-8') as file:
        config = yaml.safe_load(file)
    for name, axis in config['eixos'].items():
        values = axis['valores']
        weights = axis.get('pesos', {})
        if not values or len(set(values)) != len(values):
            raise ValueError(f'Eixo inválido: {name}')
        if any(weights.get(v, 1) < 0 for v in values) or not sum(weights.get(v, 1) for v in values):
            raise ValueError(f'Pesos inválidos: {name}')
        if set(values) - config['rotulos'].get(name, {}).keys():
            raise ValueError(f'Faltam rótulos para {name}.')
    return config


def temperature_capability(config, model: str, settings: Settings):
    configured = config.get('modelos', {}).get(model, config['modelos']['padrao'])
    supported = configured['temperatura'].get('suportada', False)
    # A global override applies only to the default model, never an arbitrary UI selection.
    if model and model == settings.model and settings.temperature_supported is not None:
        supported = settings.temperature_supported
    return {**config['temperatura'], **configured['temperatura'], 'suportada': supported}
