# Gerador de Parágrafos

Aplicação FastAPI + React para gerar parágrafos em português pelo **OpenRouter**. O visual usa o CSS anos 80 fornecido, com fontes empacotadas localmente. Não há modo de demonstração nem geração automática ao abrir a página.

## Instalar e iniciar

Requisitos: Python 3.11+ e Node.js 20.19+ ou 22.12+.

Na raiz do repositório:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r gerador/requirements.txt
cd gerador/frontend
npm ci
npm run build
cd ../..
.venv/bin/python -m uvicorn gerador.app.main:app --host 127.0.0.1 --port 8001
```

O backend serve a interface compilada e a API na porta 8001. O Python Studio original continua disponível separadamente por `python3 server.py`, na porta 8000. Use um único processo/worker para o gerador: as tarefas de lote e os bloqueios por sessão estão na memória do processo.

Para desenvolver a interface com atualização automática, mantenha o backend na porta 8001 e execute `npm run dev` em `gerador/frontend`. O Vite encaminha as rotas da API ao backend.

## Tudo configurado na página

1. Cole a **chave da conta OpenRouter** no campo de chave. Ela não é específica de um modelo. Disponibilidade, preço e saldo dependem da conta e do modelo escolhido.
2. Clique no **+** ao lado do seletor e informe o identificador `provedor/modelo`. A lista, a opção de temperatura e o último modelo selecionado são salvos automaticamente e restaurados ao reabrir a página.
3. Clique em **Salvar chave** para mantê-la no armazenamento local deste navegador. Ao fechar e reabrir a página, o campo de senha será preenchido novamente. **Apagar chave salva** remove a chave do navegador e do campo, sem apagar os modelos. Editar o campo só substitui a chave persistida quando você clicar novamente em **Salvar chave**. A chave salva fica acessível ao perfil do navegador; ela é enviada ao backend no corpo JSON das chamadas, nunca na URL, e não entra no banco, no histórico ou nas exportações. Chamadas já iniciadas continuam com a chave recebida.
4. Habilite **temperatura** somente para modelos que a aceitem. O controle aparece como régua, com valor numérico. O padrão é omitir `temperature`, `top_p` e `top_k`. Em um erro 400 de amostragem, a chamada é repetida uma vez sem temperatura e o resultado registra o aviso.
5. Escolha valores fixos, aleatórios ou, no lote, **variar**. Ajuste tema, ousadia, semente, anti-repetição e quantidade de itens. Em **Ajustes de geração**, também é possível mudar máximo de tokens, limiar de similaridade e concorrência.
6. Gere, copie, regenere com os mesmos parâmetros e modelo, ou aprove/reprove resultados. O histórico permanece no SQLite e pode ser filtrado por lote e exportado em CSV/JSONL.

### Fita histórica

No topo, abra a **engrenagem ⚙ → Fita histórica**. O histórico tem uma página própria, sem os controles de geração. Ela lista todos os parágrafos salvos em páginas de 20 itens, com **Anteriores/Próximos**, filtro por lote e exportação CSV/JSONL. Ao clicar em um item, os detalhes abrem abaixo da lista: texto completo, botão **Ouvir**, tags dos parâmetros, prompt, modelo utilizado, data e metadados. O prompt já aparece expandido nessa página. Os botões de copiar, aprovar/reprovar e regenerar continuam disponíveis.

**Voltar ao gerador** retorna aos controles e resultados atuais sem perder os ajustes da sessão. Regenerar um item do histórico volta ao gerador usando os parâmetros e modelo desse item. A navegação também funciona com os botões voltar/avançar do navegador; recarregar na Fita histórica mantém essa página aberta. O áudio é interrompido ao trocar de página ou selecionar outro parágrafo.

### Leitura em voz alta pelo OpenRouter

Cada parágrafo exibido tem um botão **▶ Ouvir** e uma **seta ▾** logo abaixo do texto. Na seta, informe o identificador `provedor/modelo` de um modelo **TTS (síntese de voz)** disponível no OpenRouter, a voz opcional e a velocidade. Clique em **Salvar configurações de leitura**: os ajustes são compartilhados entre os parágrafos e restaurados no mesmo navegador ao reabrir a página. A leitura usa a mesma chave OpenRouter configurada no topo. O modelo de voz é independente do modelo que escreve os parágrafos.

Após salvar com sucesso, a caixa de configuração fecha automaticamente. Se algum campo estiver inválido ou o navegador impedir a gravação, ela permanece aberta e mostra o erro.

O modelo inicial é `google/gemini-3.8-flash-lite-tts`. Configurações de leitura já salvas têm prioridade; para trocar uma escolha anterior, abra a seta, informe esse identificador e salve. A disponibilidade do modelo depende do OpenRouter.

Ao selecionar um modelo Gemini TTS, o campo de voz vira um seletor com as 30 vozes listadas pelo OpenRouter, incluindo Kore, Puck, Aoede e Zephyr. Escolha a voz e clique em **Salvar configurações de leitura**. Para outros provedores, o campo continua aceitando o identificador de voz em texto.

Ao apertar **Ouvir**, o backend envia o texto do parágrafo à rota oficial `POST /api/v1/audio/speech`. Para modelos `google/gemini-…-tts`, solicita **PCM** e fornece a voz **Kore** se o campo estiver vazio. O PCM de 16 bits recebe um cabeçalho WAV em memória, preservando as amostras e a frequência/canais informados pelo provedor (padrão documentado do Gemini: 24 kHz, mono), para reprodução no navegador. Gemini TTS rejeita MP3 e exige voz explícita. Você pode escolher outra voz compatível, como `Puck` ou `Aoede`.

Para outros modelos, a requisição continua solicitando MP3; informe uma voz aceita pelo provedor, exceto quando ele documentar uma voz padrão. Modelos apenas de texto ou de chat com áudio podem não aceitar a rota TTS. A régua de velocidade atua na reprodução do navegador, sem enviar um parâmetro de velocidade ao provedor nem gerar outra chamada. Na API, `velocidade` ainda é aceito para clientes externos com modelos que o suportam; esse campo é omitido na chamada ao Gemini. Referências: [guia TTS](https://openrouter.ai/docs/guides/overview/multimodal/tts), [exemplo oficial de Gemini PCM/WAV](https://openrouter.ai/docs/cookbook/audio/two-voice-podcast) e [OpenAPI](https://openrouter.ai/openapi.json).

O botão permite pausar e continuar. Ao ouvir outro parágrafo, a leitura anterior é pausada. O áudio fica temporariamente na memória da página; repeti-lo reutiliza o áudio, inclusive ao ajustar a velocidade. Trocar texto, chave, modelo ou voz, sair do resultado ou recarregar a página descarta essa cópia. Para ouvir um texto antigo, abra-o pelo histórico. Áudios não são gravados no SQLite nem exportados.

Gerar uma nova leitura consome créditos do OpenRouter. Não há repetição automática de chamadas de áudio. Cancelar interrompe a espera na página, mas uma síntese já recebida pelo provedor ainda pode ser cobrada. Falhas de chave, saldo, rede ou configuração aparecem junto ao botão; o parágrafo gerado permanece disponível. Sem chave e modelo reais, os testes validam a integração com respostas simuladas.

### Respostas cortadas e modelos com raciocínio

O orçamento inicial padrão é **4096 tokens**. Alguns modelos gastam parte desse orçamento em raciocínio, deixando menos espaço para o parágrafo. Em **Ajustes de geração**, é possível configurar:

- **Tokens por tentativa inicial** e **Teto de tokens por tentativa** (padrão 8192). Com recuperação ligada, uma resposta que atingiu o limite gera uma nova tentativa com orçamento dobrado, respeitando o teto e o máximo de três tentativas. O teto efetivo nunca é menor que o orçamento inicial. O texto é gerado novamente, não concatenado ao trecho incompleto. Aumentar o orçamento pode aumentar o custo.
- **Aumentar tokens se a resposta for cortada**: pode ser desligado. Sem recuperação, ou quando o teto é atingido, o sistema informa como ajustar o limite em vez de gastar novas chamadas com o mesmo orçamento esgotado.
- **Raciocínio do modelo**: padrão do provedor (sem override), desativado, baixo, médio ou alto. Modelos podem não permitir controlar ou desativar raciocínio. Se o provedor rejeitar o campo com erro 400 específico, há uma tentativa sem ele, registrada como aviso. Esses controles não garantem que o modelo consiga escrever com qualquer orçamento.

O painel **Prompt e metadados** mostra cada tentativa, motivo de término, orçamento, consumo de tokens e tokens de raciocínio quando informados pelo provedor. O conteúdo dos campos separados de raciocínio não é usado como parágrafo nem salvo. Erros guardam códigos e contagens, sem copiar mensagens brutas que possam conter credenciais. Erros transitórios dentro de respostas HTTP 200 também são reconhecidos.

Se uma nova chamada falhar no provedor após uma resposta parcial, o trecho anterior e seu prompt são preservados. Histórico antigo continua legível; informações não registradas na época aparecem como indisponíveis. A opção **Formato verificado** significa validação automática estrutural, não aprovação gramatical ou editorial. A anti-repetição varia aberturas e imagens sem transformar palavras necessárias ao tema em termos proibidos.

Nenhuma chave ou modelo precisa ser configurado no ambiente da nuvem. Opcionalmente, `gerador/.env` pode definir padrões do servidor conforme `.env.example`; `OPENROUTER_API_KEY` é usada apenas quando não há chave na requisição. Não copie chaves para o código. A conexão HTTPS do backend precisa alcançar `openrouter.ai`; instalar dependências usa os registries Python e npm.

Use o mesmo navegador, perfil e endereço ao voltar. O armazenamento é separado por endereço e porta: abrir por `localhost` e por `127.0.0.1`, ou mudar de porta, usa espaços diferentes. Limpar dados do site remove as configurações; janelas privadas normalmente não as preservam após fechar. Se o navegador impedir uma gravação, a página informa a falha.

## Diversidade e limites

- `parameters.yaml` contém eixos, rótulos, pesos, frases por tamanho e capacidades por identificador de modelo. Modelos desconhecidos começam sem temperatura.
- `variar` usa ciclos embaralhados: as contagens diferem por no máximo um. Regras ajustam escolhas aleatórias. Valores fixos e a distribuição balanceada são preservados; incompatibilidades impossíveis de corrigir sem alterá-los produzem avisos.
- A semente reproduz o sorteio, a escolha de templates e o jitter; não torna o LLM determinístico.
- Anti-repetição considera a sessão da aba e gera sequencialmente. Sem ela, o lote aceita concorrência configurável, até 20 chamadas. A comparação com todos os itens já aceitos do lote continua ativa e é feita novamente após o retorno de cada chamada concorrente.
- O sistema tenta corrigir formato, idioma e similaridade até duas vezes depois da primeira resposta. Falhas persistentes ficam como `falhou`, com motivo e todas as tentativas. Textos duplicados não são aceitos como `ok`; não é possível prometer que um LLM sempre entregará a quantidade solicitada de textos válidos.
- Validação de idioma e contagem de frases são heurísticas; textos curtos, siglas e diálogos podem gerar falsos positivos. A validação estrutural não comprova que o LLM seguiu cada preferência estilística.
- Cada chamada ao provedor tem até três tentativas para falhas transitórias. Regenerações e retries podem gerar custos adicionais. Uso de tokens informado pelo provedor é acumulado nas tentativas de conteúdo; não representa uma auditoria de cobrança.
- Lotes são limitados a 100 itens. A interface acompanha o progresso sem manter a requisição de geração aberta. Recarregar a página permite acompanhar um lote ativo da mesma aba. Se o servidor reiniciar, os lotes incompletos passam a `interrompido`; itens concluídos permanecem no banco. Não há retomada automática de chamadas pendentes nem armazenamento de chaves.
- O banco padrão fica em `gerador/data/gerador.db`. Faça backup desse diretório quando precisar preservar o histórico. Não há autenticação ou isolamento de histórico por usuário; este servidor destina-se a uso local ou acesso privado.

## API

| Rota | Função |
| --- | --- |
| `GET /parametros` | Eixos, rótulos, padrões e capacidade do modelo padrão |
| `POST /configuracao` | Capacidade do modelo selecionado; não persiste a chave ou configurações globais |
| `POST /gerar` | Geração individual |
| `POST /audio/ler` | Síntese de voz; recebe `texto`, `modelo`, `voz?`, `velocidade?`, `api_key?` e retorna WAV para Gemini TTS ou MP3, sem cache |
| `POST /gerar/lote` | Lote; `202` com ID quando assíncrono ou maior que 10 |
| `GET /lotes/{id}` | Estado, progresso, itens e métricas |
| `GET /historico?limite=50&offset=0&lote_id=…` | Histórico paginado |
| `PATCH /geracoes/{id}` | `{"aprovado": true}`, `false` ou `null` |
| `GET /exportar?formato=csv\|jsonl&lote_id=…` | Exportação completa, incluindo prompts e tentativas |
| `GET /saude` | Estado da aplicação e acesso ao SQLite |

O corpo de `/gerar` aceita `parametros`, `modelo`, `api_key`, `temperatura_suportada`, `temperatura`, `seed`, `anti_repeticao`, `n_historico`, `modo_sorteio`, `sessao_id`, `max_tokens`, `recuperar_truncamento`, `teto_tokens`, `raciocinio` e `limiar_similaridade`. O lote acrescenta `n`, `estrategias`, `jitter`, `concorrencia` e `assincrono`. `tema` pertence ao objeto `parametros`. `api_key` é excluída da serialização de histórico. O OpenAPI em `/docs` descreve os limites e tipos.

## Testes

Na raiz:

```sh
.venv/bin/python -m pytest -q gerador/tests
cd gerador/frontend
npm test
npm run build
```

Os testes exercitam sorteio balanceado, regras, prompts, validação, deduplicação concorrente, retries OpenRouter, SQLite, exportação, aprovação, lotes assíncronos, preservação de credenciais e controles da interface. Chamadas externas são simuladas; os testes não gastam créditos nem comprovam a disponibilidade de um modelo real.

Para atualizar dependências Python, edite `requirements.in` e regenere o lock com `uv pip compile gerador/requirements.in --generate-hashes -o gerador/requirements.txt`. O frontend usa `package-lock.json` e `npm ci` para instalações reproduzíveis.
