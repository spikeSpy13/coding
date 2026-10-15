from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    parametros: dict[str, str] = Field(default_factory=dict)
    modelo: str | None = Field(default=None, max_length=200)
    api_key: SecretStr | None = Field(default=None, exclude=True)
    temperatura: float | None = Field(default=None, ge=0, le=2, allow_inf_nan=False)
    temperatura_suportada: bool | None = None
    max_tokens: int = Field(default=800, ge=100, le=16000)
    limiar_similaridade: float = Field(default=0.4, ge=0, le=1, allow_inf_nan=False)
    seed: int | None = None
    anti_repeticao: bool = True
    n_historico: int = Field(default=10, ge=0, le=100)
    modo_sorteio: Literal['manual', 'parcial', 'surpreenda_me'] = 'parcial'
    sessao_id: str = Field(default='padrao', min_length=1, max_length=100, pattern=r'^[\w-]+$')

    @field_validator('modelo')
    @classmethod
    def valid_model(cls, value):
        if value is not None:
            value = value.strip()
            if not value or any(char.isspace() for char in value):
                raise ValueError('Informe um identificador de modelo OpenRouter sem espaços.')
        return value

    @field_validator('parametros')
    @classmethod
    def bound_parameters(cls, value):
        if len(value) > 20 or any(len(k) > 80 or len(v) > 2000 for k, v in value.items()):
            raise ValueError('Parâmetros excedem o limite permitido.')
        return value


class BatchRequest(GenerateRequest):
    n: int = Field(default=10, ge=1, le=100)
    estrategias: dict[str, Literal['fixo', 'aleatorio', 'variar']] = Field(default_factory=dict)
    jitter: bool = False
    assincrono: bool = False
    concorrencia: int = Field(default=5, ge=1, le=20)


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    aprovado: bool | None


class ModelConfiguration(BaseModel):
    model_config = ConfigDict(extra='forbid')
    modelo: str = Field(default='', max_length=200)
    temperatura_suportada: bool | None = None
