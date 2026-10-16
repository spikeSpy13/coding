import React, { useEffect, useRef, useState } from 'react';
import { call, storedModels, saveModels, storedApiKey, saveApiKey, forgetApiKey, storedSelectedModel, saveSelectedModel } from './api.js';
import { storedSpeechSettings } from './ParagraphAudio.jsx';
import ParagraphItem from './ParagraphItem.jsx';
import HistoryPage from './HistoryPage.jsx';
import './gerador80s.css';
import './app.css';

const currentPage = () => window.location.hash === '#historico' ? 'historico' : 'gerador';
const label = (config, axis, value) => config.rotulos[axis]?.[value] || value;
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));

export default function Gerador80s() {
  const [config, setConfig] = useState(null);
  const [models, setModels] = useState(storedModels);
  const [model, setModel] = useState('');
  const [savedApiKey, setSavedApiKey] = useState(storedApiKey);
  const [apiKey, setApiKey] = useState(savedApiKey);
  const [speechSettings, setSpeechSettings] = useState(storedSpeechSettings);
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
  const [page, setPage] = useState(currentPage);
  const [menuOpen, setMenuOpen] = useState(false);
  const [historyVersion, setHistoryVersion] = useState(0);
  const menu = useRef(null);
  const gear = useRef(null);
  const [batchId, setBatchId] = useState('');
  const [progress, setProgress] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const alive = useRef(true);
  const session = useRef('');
  const modelVersion = useRef(0);

  useEffect(() => {
    function navigate() { setPage(currentPage()); setMenuOpen(false); }
    window.addEventListener('hashchange', navigate);
    return () => window.removeEventListener('hashchange', navigate);
  }, []);

  useEffect(() => {
    document.title = page === 'historico' ? 'Fita histórica · Gerador de Parágrafos' : 'Gerador de Parágrafos';
  }, [page]);

  useEffect(() => {
    if (!menuOpen) return;
    function closeOutside(event) { if (!menu.current?.contains(event.target)) setMenuOpen(false); }
    function escape(event) {
      if (event.key === 'Escape') { setMenuOpen(false); gear.current?.focus(); }
    }
    document.addEventListener('pointerdown', closeOutside);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('pointerdown', closeOutside);
      document.removeEventListener('keydown', escape);
    };
  }, [menuOpen]);

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
      if (data.modelo && !known.some(m => m.id === data.modelo)) {
        known.push({id: data.modelo, temperature: data.temperatura.suportada});
        try { saveModels(known); } catch { setError('Não foi possível salvar a lista de modelos neste navegador.'); }
      }
      setModels(known);
      const selected = storedSelectedModel();
      if (known.length) selectModel(known.some(m => m.id === selected) ? selected : known[0].id, known);
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
    try { saveSelectedModel(id); } catch { setError('Não foi possível salvar o modelo selecionado neste navegador.'); }
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
    try { saveModels(updated); } catch { setError('Não foi possível salvar o ajuste de temperatura deste modelo.'); }
  }

  function saveKey() {
    const key = apiKey.trim();
    if (!key) return;
    try {
      saveApiKey(key);
      setApiKey(key);
      setSavedApiKey(key);
      setError('');
    } catch { setError('O navegador não permitiu salvar a chave. Ela pode ser usada nesta sessão; tente permitir o armazenamento local.'); }
  }

  function forgetKey() {
    try {
      forgetApiKey();
      setApiKey('');
      setSavedApiKey('');
      setError('');
    } catch { setError('Não foi possível apagar a chave salva. Remova os dados deste site nas configurações do navegador.'); }
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
        setHistoryVersion(version => version + 1);
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
        setItems([data]); setBatchId(''); setHistoryVersion(version => version + 1);
      }
    } catch(e) { setError(e.message); }
    finally { if (alive.current) setBusy(false); }
  }

  async function approve(item, approved) {
    try {
      const updated = await call('/geracoes/' + item.id, {aprovado: approved}, 'PATCH');
      setItems(all => all.map(value => value.id === item.id ? updated : value));
      return updated;
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
      <div><p className="g80-eyebrow">Sistema de texto · Mod. 84</p><h1 className="g80-title">{page === 'historico' ? 'Fita histórica' : 'Gerador de Parágrafos'}</h1></div>
      <div className="g80-head-actions">
      {page === 'gerador' && <div className="g80-modo" role="group" aria-label="Modo de geração">
        <button aria-pressed={!batchMode} disabled={busy} onClick={() => switchMode(false)}>Individual</button>
        <button aria-pressed={batchMode} disabled={busy} onClick={() => switchMode(true)}>Lote</button>
      </div>}
      <div className="g80-menu" ref={menu}>
        <button className="g80-mini g80-gear" ref={gear} aria-label="Abrir menu" aria-expanded={menuOpen} aria-controls="navigation-menu" onClick={() => setMenuOpen(!menuOpen)}>⚙</button>
        {menuOpen && <nav className="g80-menu-links" id="navigation-menu" aria-label="Navegação principal">
          <a href="#gerador" aria-current={page === 'gerador' ? 'page' : undefined} onClick={() => setMenuOpen(false)}>Gerador</a>
          <a href="#historico" aria-current={page === 'historico' ? 'page' : undefined} onClick={() => setMenuOpen(false)}>Fita histórica</a>
        </nav>}
      </div>
      </div>
    </header>
    {error && <p role="alert" className="g80-global-error g80-erro">{error}</p>}
    {page === 'historico' ? <HistoryPage config={config} apiKey={apiKey} speechSettings={speechSettings} onSpeechSettings={setSpeechSettings}
      busy={busy} version={historyVersion} batchId={batchId} onApprove={approve}
      onRegenerate={item => { window.location.hash = 'gerador'; generate('manual', item); }} /> : <>
    <section className="g80-conexao g80-painel" aria-label="Configuração OpenRouter">
      <div className="g80-campo"><label htmlFor="api-key">Chave OpenRouter</label>
        <input id="api-key" type="password" autoComplete="off" spellCheck="false" value={apiKey} onChange={e => setApiKey(e.target.value)} placeholder={config.chave_configurada ? 'Chave do servidor disponível' : 'Cole sua chave aqui'} disabled={busy}/>
        <div className="g80-mini-acoes"><button className="g80-mini" disabled={busy || !apiKey.trim() || apiKey.trim() === savedApiKey} onClick={saveKey}>Salvar chave</button><button className="g80-mini" disabled={busy || (!apiKey && !savedApiKey)} onClick={forgetKey}>Apagar chave salva</button></div>
        <small role="status">{savedApiKey && apiKey.trim() === savedApiKey ? 'Chave salva neste navegador. Ela estará disponível ao reabrir a página.' : savedApiKey ? 'Alteração ainda não salva. Clique em Salvar chave para substituir a anterior.' : 'Clique em Salvar chave para mantê-la neste navegador após fechar a página.'}</small>
      </div>
      <div className="g80-campo"><label htmlFor="model">Modelo OpenRouter</label><div className="g80-model-row">
        <select id="model" value={model} disabled={busy} onChange={e => selectModel(e.target.value)}><option value="">Escolha um modelo</option>{models.map(m => <option key={m.id} value={m.id}>{m.id}</option>)}</select>
        <button className="g80-btn g80-plus" aria-label="Adicionar modelo" disabled={busy} onClick={() => setAdding(!adding)}>+</button>
      </div><small>A lista e o último modelo selecionado são salvos automaticamente neste navegador.</small></div>
      {adding && <form className="g80-add-model" onSubmit={addModel}>
        <label htmlFor="new-model">Identificador do modelo</label><input id="new-model" autoFocus value={newModel} onChange={e => setNewModel(e.target.value)} placeholder="provedor/modelo" maxLength={200} required/>
        <label className="g80-check"><input type="checkbox" checked={newSupports} onChange={e => setNewSupports(e.target.checked)}/>Este modelo aceita temperatura</label>
        <button className="g80-mini" type="submit">Adicionar ao seletor</button><button className="g80-mini" type="button" onClick={() => setAdding(false)}>Cancelar</button>
      </form>}
    </section>
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
          <div className={items.length > 1 ? 'g80-lista' : ''}>{items.map((item,index) => <ParagraphItem key={item.id} item={item} index={index} config={config} busy={busy} onRegenerate={value => generate('manual', value)} onApprove={approve} apiKey={apiKey} speechSettings={speechSettings} onSpeechSettings={setSpeechSettings}/>)}</div>
          {stats && <><dl className="g80-metricas"><div><dt>Aberturas únicas</dt><dd><strong>{Math.round(stats.aberturas_unicas * 100)}%</strong></dd></div><div><dt>Diversidade lexical</dt><dd><strong>{Math.round(stats.diversidade_lexical * 100)}%</strong></dd></div><div><dt>Média de palavras</dt><dd><strong>{Math.round(stats.comprimento.media)}</strong></dd></div></dl><details className="g80-details"><summary>Distribuição dos parâmetros e métricas completas</summary><pre>{JSON.stringify(stats,null,2)}</pre></details></>}
        </section>

      </div>
    </main>
    </>}
  </div>;
}
