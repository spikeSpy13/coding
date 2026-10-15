import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import server


class RunnerTests(unittest.TestCase):
    def test_python_output(self):
        self.assertEqual(server.execute('print(sum(range(5)))'), {'output': '10\n', 'exit_code': 0})

    def test_python_error(self):
        result = server.execute('raise ValueError("teste")')
        self.assertNotEqual(result['exit_code'], 0)
        self.assertIn('ValueError: teste', result['output'])

    def test_timeout(self):
        result = server.execute('while True: pass')
        self.assertEqual(result['exit_code'], 124)
        self.assertIn('10 segundos', result['output'])

    @patch.dict('os.environ', {}, clear=True)
    def test_missing_key(self):
        with self.assertRaisesRegex(ValueError, 'chave'):
            server.generate({'prompt': 'hello', 'model': 'test/model'})

    @patch('server.urlopen')
    def test_generation(self, open_url):
        open_url.return_value.__enter__.return_value = io.BytesIO(json.dumps({
            'choices': [{'message': {'content': '```python\nprint(42)\n```'}}]
        }).encode())
        result = server.generate({'api_key': 'test-key', 'model': 'test/model', 'prompt': 'print 42'})
        self.assertEqual(result['code'], 'print(42)')
        request = open_url.call_args.args[0]
        self.assertEqual(request.full_url, 'https://openrouter.ai/api/v1/chat/completions')
        self.assertEqual(json.loads(request.data)['model'], 'test/model')

    @patch('server.urlopen', side_effect=HTTPError('https://openrouter.ai', 401, '', {}, None))
    def test_invalid_key(self, _):
        with self.assertRaisesRegex(ValueError, 'inválida'):
            server.generate({'api_key': 'test-key', 'model': 'test/model', 'prompt': 'hello'})


if __name__ == '__main__':
    unittest.main()
