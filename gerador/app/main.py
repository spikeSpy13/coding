import asyncio
from contextlib import asynccontextmanager
from typing import Literal
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles

from .config import ROOT, Settings, load_parameters, temperature_capability
from .exporter import export_rows
from .models import ApprovalRequest, BatchRequest, GenerateRequest, ModelConfiguration
from .service import Generator
from .storage import Storage
from .speech import OpenRouterSpeechClient, SpeechError, SpeechRequest


def create_app(settings=None, client_factory=None, speech_client=None):
    settings = settings or Settings.from_env()
    config = load_parameters()
    speech = speech_client or OpenRouterSpeechClient()

    @asynccontextmanager
    async def lifespan(app):
        storage = Storage(settings.db_path)
        storage.interrupt_batches()
        app.state.storage = storage
        app.state.generator = Generator(settings, config, storage, client_factory)
        app.state.tasks = set()
        yield
        tasks = list(app.state.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    app = FastAPI(title='Gerador de Parágrafos', version='1.0.0', lifespan=lifespan)

    @app.middleware('http')
    async def protect_requests(request, call_next):
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            origin = request.headers.get('origin')
            if request.headers.get('sec-fetch-site') == 'cross-site' or (origin and urlparse(origin).netloc != request.headers.get('host')):
                return JSONResponse({'detail': 'Origem não permitida.'}, status_code=403)
            if request.headers.get('content-type', '').split(';')[0] != 'application/json':
                return JSONResponse({'detail': 'Envie JSON.'}, status_code=415)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        # FastAPI's default error body can echo request inputs, including API credentials.
        return JSONResponse(status_code=422, content={'detail': [
            {'loc': list(item['loc']), 'msg': item['msg'], 'type': item['type']}
            for item in error.errors()
        ]})

    def catalogue(model, override=None):
        capability = temperature_capability(config, model, settings)
        if override is not None:
            capability['suportada'] = override
        return {'eixos': config['eixos'], 'rotulos': config['rotulos'],
                'tamanho_frases': config['tamanho_frases'], 'temperatura': capability,
                'modelo': model, 'provedor': 'openrouter', 'chave_configurada': bool(settings.api_key),
                'padroes': {'max_tokens': settings.max_tokens, 'concorrencia': settings.concurrency,
                            'limiar_similaridade': settings.similarity_threshold}}

    @app.get('/parametros')
    async def parameters():
        return catalogue(settings.model)

    @app.post('/configuracao')
    async def configuration(body: ModelConfiguration):
        return catalogue(body.modelo, body.temperatura_suportada)

    @app.get('/saude')
    async def health():
        with app.state.storage.connection() as connection:
            connection.execute('SELECT 1').fetchone()
        return {'ok': True, 'provedor': 'openrouter'}

    def prepare(body):
        try:
            return app.state.generator.prepare(body)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None

    @app.post('/gerar')
    async def generate(body: GenerateRequest):
        samples, client = prepare(body)
        return await app.state.generator.single(body, samples, client)

    @app.post('/audio/ler')
    async def read_paragraph(body: SpeechRequest):
        key = body.api_key.get_secret_value().strip() if body.api_key else settings.api_key
        if not key:
            raise HTTPException(422, 'Informe sua chave OpenRouter no topo da página para ouvir o parágrafo.')
        if len(key) > 1000 or not key.isascii() or any(c.isspace() or ord(c) < 32 for c in key):
            raise HTTPException(422, 'A chave OpenRouter contém caracteres inválidos.')
        try:
            audio = await speech.synthesize(body, key)
        except SpeechError as error:
            raise HTTPException(error.status, str(error)) from None
        return Response(audio.content, media_type=audio.media_type,
                        headers={'Content-Disposition': 'inline; filename="paragrafo.mp3"'})

    @app.post('/gerar/lote')
    async def batch(body: BatchRequest):
        samples, client = prepare(body)
        batch_id = app.state.storage.create_batch(body.n, body.model_dump(exclude={'api_key'}))
        if body.assincrono or body.n > settings.async_threshold:
            task = asyncio.create_task(app.state.generator.batch(batch_id, body, samples, client))
            app.state.tasks.add(task)
            task.add_done_callback(app.state.tasks.discard)
            return JSONResponse(status_code=202, content=app.state.storage.batch(batch_id))
        return await app.state.generator.batch(batch_id, body, samples, client)

    @app.get('/lotes/{batch_id}')
    async def batch_status(batch_id: str):
        data = app.state.storage.batch(batch_id)
        if data is None:
            raise HTTPException(404, 'Lote não encontrado.')
        return data

    @app.get('/historico')
    async def history(limite: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), lote_id: str | None = None):
        return app.state.storage.history(limite, offset, lote_id)

    @app.patch('/geracoes/{item_id}')
    async def approve(item_id: int, body: ApprovalRequest):
        data = app.state.storage.approve(item_id, body.aprovado)
        if data is None:
            raise HTTPException(404, 'Geração não encontrada.')
        return data

    @app.get('/exportar')
    async def export(lote_id: str | None = None, formato: Literal['csv', 'jsonl'] = 'jsonl'):
        if lote_id and app.state.storage.batch(lote_id) is None:
            raise HTTPException(404, 'Lote não encontrado.')
        return StreamingResponse(export_rows(app.state.storage, lote_id, formato),
            media_type='text/csv; charset=utf-8' if formato == 'csv' else 'application/x-ndjson',
            headers={'Content-Disposition': f'attachment; filename="paragrafos.{formato}"'})

    dist = ROOT / 'frontend' / 'dist'
    if (dist / 'assets').exists():
        app.mount('/assets', StaticFiles(directory=dist / 'assets'), name='assets')

    @app.get('/', include_in_schema=False)
    async def index():
        if not (dist / 'index.html').exists():
            raise HTTPException(503, 'Interface não compilada. Execute npm ci && npm run build em gerador/frontend.')
        return FileResponse(dist / 'index.html')

    return app


app = create_app()
