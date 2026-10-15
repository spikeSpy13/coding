import React, { useEffect, useRef, useState } from 'react';
import { call, storedModels, saveModels } from './api.js';
import './gerador80s.css';
import './app.css';

const hora = value => new Date(value).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
const label = (config, axis, value) => config.rotulos[axis]?.[value] || value;
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));

function Item({ item, index, config, busy, onRegenerate, onApprove }) {
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);
  async function copy() {
    try { await navigator.clipboard.writeText(item.texto); setCopied(true); setCopyError(false); }
    catch { setCopyError(true); }
  }
  return <article className="g80-item">
    <p className="g80-n">FAIXA {String(index + 1).padStart(2, '0')} · {item.status === 'ok' ? 'FORMATO VERIFICADO' : 'FALHOU'}</p>
    {item.status === 'ok' && <small>A verificação automática não substitui a revisão da escrita.</small>}
    <p className="g80-texto">{item.texto || 'Nenhum texto retornado.'}</p>
    {item.motivo_falha && <p className="g80-erro">{item.motivo_falha}</p>}
    <ul className="g80-chips" aria-label="Parâmetros usados">
      {Object.entries(item.parametros_finais).map(([axis, value]) => <li className="g80-chip" key={axis}><b>{config.eixos[axis]?.nome || axis}</b>{label(config, axis, value)}</li>)}
    </ul>
    {item.avisos?.map((warning, i) => <p className="g80-aviso" key={i}>! {warning}</p>)}
    <div className="g80-mini-acoes">
      <button className="g80-mini" onClick={copy}>{copied ? 'Copiado' : 'Copiar'}</button>
      <button className="g80-mini" disabled={busy} onClick={() => onRegenerate(item)}>Regenerar com os mesmos parâmetros</button>
      <button className="g80-mini" aria-pressed={item.aprovado === true} onClick={() => onApprove(item, true)}>Aprovar</button>
      <button className="g80-mini" aria-pressed={item.aprovado === false} onClick={() => onApprove(item, false)}>Reprovar</button>
    </div>
    {copyError && <p className="g80-aviso">Não foi possível copiar. Selecione o texto e copie manualmente.</p>}
    <details className="g80-details"><summary>Prompt e metadados</summary>
      <p>Modelo: {item.modelo} · Temperatura: {item.temperatura ?? 'omitida'} · Tokens: {item.tokens_entrada ?? '—'} / {item.tokens_saida ?? '—'}</p>
      <pre>{item.prompt}</pre>
      <p>{item.tentativas?.length || 1} tentativa(s) · {new Date(item.criado_em).toLocaleString('pt-BR')}</p>
      {item.tentativas?.map((attempt, i) => <details key={i}><summary>Tentativa {i + 1} · {attempt.finish_reason || attempt.tipo || 'sem diagnóstico antigo'}</summary>
        <p>Orçamento: {attempt.max_tokens ?? 'não registrado'} · Saída: {attempt.tokens_saida ?? 'não informada'} · Raciocínio: {attempt.tokens_raciocinio ?? 'não informado'}</p>
        {attempt.motivos?.map((reason, j) => <p className="g80-aviso" key={j}>{reason}</p>)}
        <pre>{attempt.texto || 'Sem texto final.'}</pre>
        {attempt.diagnostico && <pre>{JSON.stringify(attempt.diagnostico, null, 2)}</pre>}
      </details>)}
    </details>
  </article>;
}

export default function Gerador80s() {
  const [config, setConfig] = useState(null);
  const [models, setModels] = useState(storedModels);
  const [model, setModel] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [newModel, setNewModel] = useState('');
  const [newSupports, setNewSupports] = useState(false);
  const [adding, setAdding] = useState(false);
  const [supports, setSupports] = useState(false);
  const [temperature, setTemperature] = useState(1);
  const [values, setValues] = useState({});
  const [theme, setTheme] = useState('');
  const [batchMode, setBatchMode] = useState(false);
  const [n, setN] = useState(6);
  const [anti, setAnti] = useState(true);
  const [nHistory, setNHistory] = useState(10);
  const [jitter, setJitter] = useState(false);
  const [seed, setSeed] = useState('');
  const [maxTokens, setMaxTokens] = useState(4096);
  const [recoverTruncation, setRecoverTruncation] = useState(true);
  const [tokenCeiling, setTokenCeiling] = useState(8192);
  const [reasoning, setReasoning] = useState('automatico');
  const [concurrency, setConcurrency] = useState(5);
  const [threshold, setThreshold] = useState(0.4);
  const [items, setItems] = useState([]);
  const [stats, setStats] = useState(null);
  const [history, setHistory] = useState([]);
  const [filter, setFilter] = useState('');
  const [offset, setOffset] = useState(0);
  const [batchId, setBatchId] = useState('');
  const [progress, setProgress] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const alive = useRef(true);
  const session = useRef('');
  const modelVersion = useRef(0);

  useEffect(() => {
    alive.current = true;
    session.current = sessionStorage.getItem('gerador-sessao') || crypto.randomUUID();
    sessionStorage.setItem('gerador-sessao', session.current);
    call('/parametros').then(data => {
      if (!alive.current) return;
      setConfig(data);
      setValues(Object.fromEntries(Object.entries(data.eixos).map(([key, axis]) => [key, axis.padrao || 'aleatorio'])));
      setMaxTokens(data.padroes.max_tokens); setConcurrency(data.padroes.concorrencia); setThreshold(data.padroes.limiar_similaridade);
      const known = storedModels();
      if (data.modelo && !known.some(m => m.id === data.modelo)) known.push({id: data.modelo, temperature: data.temperatura.suportada});
      setModels(known);
      if (known.length) selectModel(known[0].id, known);
      refreshHistory();
      const pending = sessionStorage.getItem('gerador-lote-ativo');
      if (pending) {
        setBusy(true);
        followBatch(pending).catch(e => { if (alive.current) setError(e.message); }).finally(() => { if (alive.current) setBusy(false); });
      }
    }).catch(e => setError(e.message));
    return () => { alive.current = false; };
  }, []);

  async function selectModel(id, list = models) {
    setModel(id);
    const version = ++modelVersion.current;
    const support = list.find(m => m.id === id)?.temperature ?? false;
    setSupports(support);
    if (!id) return;
    try {
      const data = await call('/configuracao', {modelo: id, temperatura_suportada: support});
      if (version !== modelVersion.current || !alive.current) return;
      setConfig(data);
      setTemperature(data.temperatura.padrao);
    } catch(e) { setError(e.message); }
  }

  function addModel(event) {
    event.preventDefault();
    const id = newModel.trim();
    if (!id.includes('/') || /\s/.test(id) || id.startsWith('sk-') || id.length > 200) {
      setError('Informe o identificador provedor/modelo. A chave pertence ao campo Chave OpenRouter.'); return;
    }
    const updated = [...models.filter(m => m.id !== id), {id, temperature: newSupports}];
    if (updated.length > 100) { setError('Limite de 100 modelos salvos.'); return; }
    setModels(updated);
    try { saveModels(updated); } catch { setError('O navegador não permitiu salvar a lista; o modelo pode ser usado nesta sessão.'); }
    selectModel(id, updated);
    setAdding(false); setNewModel(''); setNewSupports(false);
  }

  function changeSupport(value) {
    setSupports(value);
    const updated = models.map(m => m.id === model ? {...m, temperature: value} : m);
    setModels(updated);
    try { saveModels(updated); } catch { /* The selection still works in memory. */ }
  }

  function body(mode = 'parcial', item = null) {
    if (!model && !item) throw new Error('Adicione um modelo pelo botão +.');
    if (!apiKey.trim() && !config.chave_configurada) throw new Error('Informe sua chave OpenRouter no campo da página.');
    return {
      modelo: item?.metadados?.modelo_solicitado || item?.modelo || model,
      api_key: apiKey.trim() || undefined,
      parametros: item ? item.parametros_finais : {...values, tema: theme.trim() || 'aleatorio'},
      temperatura_suportada: item ? item.temperatura !== null : supports,
      ...(item ? (item.temperatura === null ? {} : {temperatura: item.temperatura}) : supports ? {temperatura: temperature} : {}),
      seed: seed === '' ? null : Number(seed),
      anti_repeticao: anti, n_historico: nHistory, modo_sorteio: mode,
      max_tokens: maxTokens, limiar_similaridade: threshold, sessao_id: session.current,
      recuperar_truncamento: recoverTruncation, teto_tokens: Math.max(maxTokens, tokenCeiling), raciocinio: reasoning,
    };
  }

  async function refreshHistory(lote = filter, position = offset) {
    try {
      const query = new URLSearchParams({limite: '20', offset: String(position)});
      if (lote.trim()) query.set('lote_id', lote.trim());
      const data = await call('/historico?' + query);
      if (alive.current) setHistory(data);
    } catch(e) { if (alive.current) setError(e.message); }
  }

  async function followBatch(id) {
    setBatchId(id);
    while (alive.current) {
      const data = await call('/lotes/' + encodeURIComponent(id));
      if (!alive.current) return;
      setItems(data.itens); setStats(data.metricas);
      setProgress(`${data.n_processado} de ${data.n_solicitado} · ${data.n_ok} validados`);
      if (!['pendente', 'processando'].includes(data.status)) {
        sessionStorage.removeItem('gerador-lote-ativo');
        if (data.erro) setError(data.erro);
        await refreshHistory();
        return;
      }
      await wait(1000);
    }
  }

  async function generate(mode = 'parcial', item = null) {
    setError('');
    let payload;
    try { payload = body(mode, item); } catch(e) { setError(e.message); return; }
    setBusy(true); setStats(null); setProgress('');
    try {
      if (batchMode && !item) {
        const data = await call('/gerar/lote', {...payload, n, jitter: supports && jitter, concorrencia: concurrency, assincrono: true});
        sessionStorage.setItem('gerador-lote-ativo', data.lote_id);
        await followBatch(data.lote_id);
      } else {
        const data = await call('/gerar', payload);
        setItems([data]); setBatchId(''); await refreshHistory();
      }
    } catch(e) { setError(e.message); }
    finally { if (alive.current) setBusy(false); }
  }

  async function approve(item, approved) {
    try {
      const updated = await call('/geracoes/' + item.id, {aprovado: approved}, 'PATCH');
      setItems(all => all.map(value => value.id === item.id ? updated : value));
      setHistory(all => all.map(value => value.id === item.id ? updated : value));
    } catch(e) { setError(e.message); }
  }

  async function download(format) {
    try {
      const query = new URLSearchParams({formato: format});
      if (filter.trim()) query.set('lote_id', filter.trim());
      const response = await fetch('/exportar?' + query);
      if (!response.ok) throw new Error('Não foi possível exportar o histórico.');
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement('a'); anchor.href = url; anchor.download = `paragrafos.${format}`; anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch(e) { setError(e.message); }
  }

  function switchMode(batch) {
    setBatchMode(batch);
    if (!batch) setValues(current => Object.fromEntries(Object.entries(current).map(([k,v]) => [k, v === 'variar' ? 'aleatorio' : v])));
  }

  function axis(name) {
    const def = config.eixos[name];
    return <div className="g80-campo" key={name}>
      <label htmlFor={'p-' + name}>{def.nome}</label>
      <select id={'p-' + name} value={values[name] || 'aleatorio'} disabled={busy} className={['aleatorio','variar'].includes(values[name]) ? 'is-auto' : ''} onChange={e => setValues(v => ({...v, [name]: e.target.value}))}>
        <option value="aleatorio">Aleatório</option>
        {batchMode && <option value="variar">Variar no lote</option>}
        <optgroup label="Valor fixo">{def.valores.map(value => <option key={value} value={value}>{label(config, name, value)}</option>)}</optgroup>
      </select>
    </div>;
  }

  if (!config) return <main className="g80"><h1>Gerador de Parágrafos</h1><p role="status">{error || 'Carregando controles…'}</p>{error && <button onClick={() => location.reload()}>Tentar novamente</button>}</main>;

  return <div className="g80">
    <div className="g80-sun" aria-hidden="true"/><div className="g80-floor" aria-hidden="true"/>
    <header className="g80-head">
      <div><p className="g80-eyebrow">Sistema de texto · Mod. 84</p><h1 className="g80-title">Gerador de Parágrafos</h1></div>
      <div className="g80-modo" role="group" aria-label="Modo de geração">
        <button aria-pressed={!batchMode} disabled={busy} onClick={() => switchMode(false)}>Individual</button>
        <button aria-pressed={batchMode} disabled={busy} onClick={() => switchMode(true)}>Lote</button>
      </div>
    </header>
    <section className="g80-conexao g80-painel" aria-label="Configuração OpenRouter">
      <div className="g80-campo"><label htmlFor="api-key">Chave OpenRouter</label>
        <div className="g80-model-row"><input id="api-key" type="password" autoComplete="off" spellCheck="false" value={apiKey} onChange={e => setApiKey(e.target.value)} placeholder={config.chave_configurada ? 'Chave do servidor disponível' : 'Cole sua chave aqui'} disabled={busy}/><button className="g80-mini" disabled={busy || !apiKey} onClick={() => setApiKey('')}>Limpar</button></div>
        <small>A chave fica apenas nesta página enquanto ela estiver aberta.</small>
      </div>
      <div className="g80-campo"><label htmlFor="model">Modelo OpenRouter</label><div className="g80-model-row">
        <select id="model" value={model} disabled={busy} onChange={e => selectModel(e.target.value)}><option value="">Escolha um modelo</option>{models.map(m => <option key={m.id} value={m.id}>{m.id}</option>)}</select>
        <button className="g80-btn g80-plus" aria-label="Adicionar modelo" disabled={busy} onClick={() => setAdding(!adding)}>+</button>
      </div><small>Adicione o identificador provedor/modelo pelo botão +.</small></div>
      {adding && <form className="g80-add-model" onSubmit={addModel}>
        <label htmlFor="new-model">Identificador do modelo</label><input id="new-model" autoFocus value={newModel} onChange={e => setNewModel(e.target.value)} placeholder="provedor/modelo" maxLength={200} required/>
        <label className="g80-check"><input type="checkbox" checked={newSupports} onChange={e => setNewSupports(e.target.checked)}/>Este modelo aceita temperatura</label>
        <button className="g80-mini" type="submit">Adicionar ao seletor</button><button className="g80-mini" type="button" onClick={() => setAdding(false)}>Cancelar</button>
      </form>}
    </section>
    {error && <p role="alert" className="g80-global-error g80-erro">{error}</p>}
    <main className="g80-grid">
      <section className="g80-painel" aria-label="Painel de controle">
        {[1,2].map(layer => <div className="g80-canal" key={layer}>
          <h2 className="g80-canal-h"><i className="g80-led" aria-hidden="true"/>Canal {layer}<span>· {layer === 1 ? 'Conteúdo e voz' : 'Estrutura'}</span></h2>
          <div className="g80-campos">{Object.keys(config.eixos).filter(name => config.eixos[name].camada === layer).map(axis)}</div>
        </div>)}
        <div className="g80-canal"><h2 className="g80-canal-h"><i className="g80-led" aria-hidden="true"/>Canal 3 <span>· Controle</span></h2>
          <div className="g80-campos">
            <div className="g80-campo g80-campo--largo"><label htmlFor="p-tema">Tema (opcional)</label><input id="p-tema" type="text" value={theme} maxLength={2000} placeholder="Em branco: o modelo escolhe" disabled={busy} onChange={e => setTheme(e.target.value)}/></div>
            {Object.keys(config.eixos).filter(name => config.eixos[name].camada === 3).map(axis)}
            <div className="g80-campo"><label htmlFor="p-seed">Semente (opcional)</label><input id="p-seed" type="number" step="1" value={seed} onChange={e => setSeed(e.target.value)} disabled={busy}/></div>
            <div className="g80-campo g80-campo--largo"><label className="g80-check"><input type="checkbox" checked={supports} disabled={busy || !model} onChange={e => changeSupport(e.target.checked)}/>Habilitar temperatura para este modelo</label><small>Ative somente se o modelo aceitar esse ajuste.</small></div>
            {supports && <div className="g80-campo g80-campo--largo">
              <label htmlFor="p-temp">Temperatura</label><div className="g80-fader"><input id="p-temp" type="range" min={config.temperatura.min} max={config.temperatura.max} step="0.05" value={temperature} disabled={busy} onChange={e => setTemperature(Number(e.target.value))}/><output htmlFor="p-temp">{temperature.toFixed(2)}</output></div>
              <div className="g80-escala" aria-hidden="true">{[0,1,2,3,4].map(i => <span key={i}>{(config.temperatura.min + (config.temperatura.max - config.temperatura.min) * i / 4).toFixed(2)}</span>)}</div>
            </div>}
            <div className="g80-campo g80-campo--largo g80-inline"><label className="g80-check"><input type="checkbox" checked={anti} disabled={busy} onChange={e => setAnti(e.target.checked)}/>Anti-repetição</label><label htmlFor="p-hist">Últimos</label><input id="p-hist" type="number" min="0" max="100" value={nHistory} disabled={busy || !anti} onChange={e => setNHistory(Number(e.target.value))}/></div>
            {batchMode && <div className="g80-campo g80-campo--largo g80-inline"><label htmlFor="p-n">Parágrafos no lote</label><input id="p-n" type="number" min="1" max="100" value={n} disabled={busy} onChange={e => setN(Number(e.target.value))}/>{supports && <label className="g80-check"><input type="checkbox" checked={jitter} disabled={busy} onChange={e => setJitter(e.target.checked)}/>Variar temperatura por item</label>}</div>}
          </div>
          <details className="g80-details"><summary>Ajustes de geração</summary><div className="g80-campos">
            <div className="g80-campo"><label htmlFor="p-tokens">Tokens por tentativa inicial</label><input id="p-tokens" type="number" min="100" max="16000" value={maxTokens} disabled={busy} onChange={e => setMaxTokens(Number(e.target.value))}/><small>Em alguns modelos, inclui raciocínio e texto final.</small></div>
            <div className="g80-campo"><label htmlFor="p-reasoning">Raciocínio do modelo</label><select id="p-reasoning" value={reasoning} disabled={busy} onChange={e => setReasoning(e.target.value)}><option value="automatico">Padrão do provedor</option><option value="desativado">Desativado, se permitido</option><option value="baixo">Baixo</option><option value="medio">Médio</option><option value="alto">Alto</option></select><small>Modelos podem ignorar ou rejeitar este ajuste.</small></div>
            <div className="g80-campo g80-campo--largo"><label className="g80-check"><input type="checkbox" checked={recoverTruncation} disabled={busy} onChange={e => setRecoverTruncation(e.target.checked)}/>Aumentar tokens se a resposta for cortada</label><small>Até três tentativas no total. Aumentar o orçamento pode aumentar o custo.</small></div>
            {recoverTruncation && <div className="g80-campo"><label htmlFor="p-ceiling">Teto de tokens por tentativa</label><input id="p-ceiling" type="number" min={maxTokens} max="16000" value={Math.max(maxTokens,tokenCeiling)} disabled={busy} onChange={e => setTokenCeiling(Number(e.target.value))}/></div>}
            <div className="g80-campo"><label htmlFor="p-sim">Limiar de similaridade</label><input id="p-sim" type="number" min="0" max="1" step="0.05" value={threshold} disabled={busy} onChange={e => setThreshold(Number(e.target.value))}/></div>
            {batchMode && <div className="g80-campo"><label htmlFor="p-con">Chamadas simultâneas</label><input id="p-con" type="number" min="1" max="20" value={concurrency} disabled={busy || anti} onChange={e => setConcurrency(Number(e.target.value))}/><small>{anti ? 'Anti-repetição usa geração sequencial.' : 'A deduplicação continua ativa no lote.'}</small></div>}
          </div></details>
          <div className="g80-acoes"><button className="g80-btn" disabled={busy} onClick={() => generate()}>{batchMode ? 'Gerar lote' : 'Gerar'}</button><button className="g80-btn g80-btn--magenta" disabled={busy} onClick={() => generate('surpreenda_me')}>Surpreenda-me</button></div>
        </div>
      </section>
      <div className="g80-saida">
        <section className="g80-crt" aria-label="Resultado" aria-busy={busy}>
          <p className="g80-status" role="status"><span className={busy ? 'g80-ocupado' : ''}>{busy ? 'Gerando…' : 'Pronto'}</span><span>{progress || `${items.length} parágrafo(s)`}</span></p>
          {batchId && <p className="g80-batch-id">Lote: {batchId}</p>}
          {!items.length && <p className="g80-vazio">Escolha o modelo, ajuste os parâmetros e aperte Gerar.</p>}
          <div className={items.length > 1 ? 'g80-lista' : ''}>{items.map((item,index) => <Item key={item.id} item={item} index={index} config={config} busy={busy} onRegenerate={value => generate('manual', value)} onApprove={approve}/>)}</div>
          {stats && <><dl className="g80-metricas"><div><dt>Aberturas únicas</dt><dd><strong>{Math.round(stats.aberturas_unicas * 100)}%</strong></dd></div><div><dt>Diversidade lexical</dt><dd><strong>{Math.round(stats.diversidade_lexical * 100)}%</strong></dd></div><div><dt>Média de palavras</dt><dd><strong>{Math.round(stats.comprimento.media)}</strong></dd></div></dl><details className="g80-details"><summary>Distribuição dos parâmetros e métricas completas</summary><pre>{JSON.stringify(stats,null,2)}</pre></details></>}
        </section>
        <section className="g80-painel g80-fita" aria-label="Histórico"><h2>Fita · Histórico</h2>
          <form className="g80-history-tools" onSubmit={e => {e.preventDefault(); setOffset(0); refreshHistory(filter,0);}}><label htmlFor="history-filter">Filtrar por ID do lote</label><input id="history-filter" type="text" value={filter} onChange={e => setFilter(e.target.value)} placeholder="Todos os lotes"/><button className="g80-mini">Filtrar</button>{batchId && <button className="g80-mini" type="button" onClick={() => {setFilter(batchId);setOffset(0);refreshHistory(batchId,0);}}>Lote atual</button>}</form>
          <div className="g80-mini-acoes"><button className="g80-mini" onClick={() => download('csv')}>Exportar CSV</button><button className="g80-mini" onClick={() => download('jsonl')}>Exportar JSONL</button></div>
          {!history.length ? <p className="g80-vazio">Nenhum parágrafo encontrado.</p> : <ol>{history.map(item => <li key={item.id}><button disabled={busy} onClick={() => {setItems([item]);setStats(null);setProgress('');setBatchId(item.lote_id || '');}}><span className="g80-hora">{hora(item.criado_em)} · {item.status === 'ok' ? 'OK' : 'FALHOU'}{item.aprovado === true ? ' ✓' : item.aprovado === false ? ' ✕' : ''}</span><span className="g80-resumo">{item.texto || item.motivo_falha}</span></button></li>)}</ol>}
          <div className="g80-mini-acoes"><button className="g80-mini" disabled={!offset} onClick={() => {const next=Math.max(0,offset-20);setOffset(next);refreshHistory(filter,next);}}>Anteriores</button><button className="g80-mini" disabled={history.length<20} onClick={() => {const next=offset+20;setOffset(next);refreshHistory(filter,next);}}>Próximos</button></div>
        </section>
      </div>
    </main>
  </div>;
}
