"""Local Python coding workspace. Run with python3 server.py."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

STATIC = Path(__file__).parent / 'static'


def execute(code):
    with tempfile.TemporaryDirectory(prefix='python-studio-') as directory:
        path = Path(directory) / 'main.py'
        path.write_text(code, encoding='utf-8')
        # This is a local development runner, not a security sandbox.
        with tempfile.TemporaryFile() as output:
            try:
                result = subprocess.run(
                    [sys.executable, '-I', '-u', str(path)], cwd=directory,
                    stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                    timeout=10, env={'PATH': os.defpath, 'PYTHONIOENCODING': 'utf-8'},
                )
                status = result.returncode
            except subprocess.TimeoutExpired:
                status = 124
            output.seek(0)
            text = output.read(100_000).decode('utf-8', errors='replace')
            if output.read(1):
                text += '\n[Saída truncada em 100 KB]'
            if status == 124:
                text += '\n[Execução interrompida após 10 segundos]'
            return {'output': text, 'exit_code': status}


def generate(data):
    key = data.get('api_key', '').strip() or os.environ.get('OPENROUTER_API_KEY', '')
    if not key:
        raise ValueError('Informe sua chave OpenRouter nas configurações.')
    prompt = data.get('prompt', '').strip()
    model = data.get('model', '').strip()
    if not prompt or not model:
        raise ValueError('Informe um pedido e selecione um modelo.')
    payload = {'model': model, 'messages': [
        {'role': 'system', 'content': 'Você é um assistente Python. Retorne somente código Python executável, sem Markdown. O programa roda sem entrada interativa; use print para apresentar resultados. Use a biblioteca padrão salvo solicitação explícita.'},
        {'role': 'user', 'content': f'Código atual:\n{data.get("code", "")}\n\nPedido:\n{prompt}'},
    ]}
    request = Request('https://openrouter.ai/api/v1/chat/completions',
                      data=json.dumps(payload).encode(), headers={
                          'Authorization': f'Bearer {key}', 'Content-Type': 'application/json',
                          'X-Title': 'Python Studio',
                      })
    try:
        with urlopen(request, timeout=90) as response:
            result = json.load(response)
    except HTTPError as error:
        messages = {401: 'Chave OpenRouter inválida.', 402: 'Saldo insuficiente no OpenRouter.',
                    429: 'Limite de requisições atingido. Tente novamente em instantes.'}
        raise ValueError(messages.get(error.code, f'OpenRouter respondeu com erro HTTP {error.code}.')) from None
    except (URLError, TimeoutError):
        raise ValueError('Não foi possível conectar ao OpenRouter. Tente novamente.') from None
    try:
        code = result['choices'][0]['message']['content']
        if not isinstance(code, str) or not code.strip():
            raise ValueError()
    except (KeyError, IndexError, TypeError, ValueError):
        raise ValueError('O modelo não retornou código. Tente outro modelo.') from None
    code = code.strip()
    if code.startswith('```'):
        code = code.split('\n', 1)[-1]
        if code.endswith('```'):
            code = code[:-3]
    return {'code': code.strip()}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send_json(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        files = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'),
                 '/style.css': ('style.css', 'text/css')}
        if self.path == '/api/health':
            return self.send_json(200, {'ok': True})
        if self.path not in files:
            return self.send_json(404, {'error': 'Não encontrado.'})
        name, mime = files[self.path]
        body = (STATIC / name).read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', mime + '; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        # Only requests from this interface may execute local Python.
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            return self.send_json(403, {'error': 'Origem não permitida.'})
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + self.headers.get('Host', ''):
            return self.send_json(403, {'error': 'Origem não permitida.'})
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.send_json(415, {'error': 'Envie JSON.'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 200_000:
                raise ValueError('Pedido vazio ou grande demais.')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('Pedido inválido.')
            if self.path == '/api/generate':
                result = generate(data)
            elif self.path == '/api/run':
                code = data.get('code')
                if not isinstance(code, str) or not code.strip():
                    raise ValueError('Escreva um código antes de executar.')
                result = execute(code)
            else:
                return self.send_json(404, {'error': 'Não encontrado.'})
            self.send_json(200, result)
        except (ValueError, TypeError) as error:
            self.send_json(400, {'error': str(error)})
        except Exception:
            self.send_json(500, {'error': 'Erro interno ao processar o pedido.'})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', '8000'))
    print(f'Python Studio: http://127.0.0.1:{port}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()
