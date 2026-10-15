# Python Studio

Workspace para gerar código com OpenRouter, editar Python e executar com saída no terminal integrado. Interface em português, responsiva, com modelos personalizados e download de `main.py`.

## Iniciar

Requer Python 3.10 ou superior. Não há dependências externas.

```sh
cd /workspace/coding
python3 server.py
```

A aplicação atende em `http://127.0.0.1:8000`. A variável `PORT` permite trocar a porta. Use acesso local ou encaminhamento privado de porta para abrir a interface.

1. Abra **Configurações** e informe sua chave OpenRouter. Ela permanece na memória da página até recarregar. Como alternativa, defina `OPENROUTER_API_KEY` no ambiente do servidor antes de iniciar. Não versione chaves.
2. Selecione um modelo ou clique em **+** para adicionar seu identificador OpenRouter, como `provedor/modelo`. Apenas a lista de modelos fica no armazenamento local do navegador. Os modelos sugeridos dependem da disponibilidade e saldo da sua conta.
3. Descreva o programa no campo inferior e clique em **Gerar código**. O pedido e o código atual são enviados ao OpenRouter. A API pode cobrar pelo uso.
4. Revise ou edite o código à esquerda e clique em **Executar**. A saída aparece à direita. Ctrl/Cmd + Enter executa; no campo de pedido, gera código.

## Execução

O Python usa um diretório temporário por execução, sem entrada interativa, com limite de 60 segundos (1 minuto) e retorno de até 100 KB de saída. Arquivos temporários são removidos depois. O runner tem acesso às permissões do usuário do servidor: **não é um sandbox de segurança**. Use apenas código confiável e não exponha este servidor à Internet ou a usuários não confiáveis. Para um serviço público, implemente isolamento em contêineres e autenticação antes de disponibilizá-lo.

A geração nunca executa código automaticamente. A chave não é registrada em logs nem persistida pela aplicação. O servidor precisa acessar `openrouter.ai` via HTTPS. A interface funciona sem as fontes externas opcionais do Google.

## Validar

```sh
python3 -m unittest discover -s tests -v
node --check static/app.js
```

Os testes cobrem execução, erros Python, timeout e contrato de geração com OpenRouter simulado. A geração real exige uma chave válida e saldo/modelo disponível.
