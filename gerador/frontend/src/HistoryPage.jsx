import React, { useEffect, useRef, useState } from 'react';
import { call } from './api.js';
import ParagraphItem from './ParagraphItem.jsx';

const PAGE_SIZE = 20;
const date = value => new Date(value).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });

export default function HistoryPage({ config, apiKey, speechSettings, onSpeechSettings, busy, version, batchId, onApprove, onRegenerate }) {
  const [rows, setRows] = useState([]);
  const [selected, setSelected] = useState(null);
  const [filter, setFilter] = useState('');
  const [query, setQuery] = useState({ lote: '', offset: 0 });
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const detail = useRef(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError('');
    const params = new URLSearchParams({ limite: String(PAGE_SIZE + 1), offset: String(query.offset) });
    if (query.lote) params.set('lote_id', query.lote);
    call('/historico?' + params, undefined, 'GET', controller.signal).then(data => {
      if (controller.signal.aborted) return;
      setRows(data.slice(0, PAGE_SIZE)); setHasMore(data.length > PAGE_SIZE);
      setSelected(current => data.find(item => item.id === current?.id) || current);
    }).catch(e => {
      if (!controller.signal.aborted) { setError(e.message); setRows([]); setHasMore(false); }
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [query, version, retry]);

  useEffect(() => {
    if (selected) {
      detail.current?.focus({ preventScroll: true });
      detail.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
    }
  }, [selected?.id]);

  function changePage(lote, offset = 0) {
    setSelected(null);
    setQuery({ lote: lote.trim(), offset });
  }

  async function approve(item, approved) {
    const updated = await onApprove(item, approved);
    if (updated) {
      setRows(all => all.map(value => value.id === item.id ? updated : value));
      setSelected(current => current?.id === item.id ? updated : current);
    }
  }

  async function download(format) {
    try {
      setError('');
      const params = new URLSearchParams({ formato: format });
      if (query.lote) params.set('lote_id', query.lote);
      const response = await fetch('/exportar?' + params);
      if (!response.ok) throw new Error('Não foi possível exportar o histórico.');
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement('a');
      anchor.href = url; anchor.download = `paragrafos.${format}`; anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { setError(e.message); }
  }

  return <main className="g80-history-page" aria-label="Fita histórica">
    <div className="g80-history-heading"><a className="g80-mini" href="#gerador">← Voltar ao gerador</a>
      <p>Selecione um parágrafo para ler, ouvir e consultar como ele foi criado.</p>
    </div>
    {busy && <p role="status">A geração continua em andamento. Você pode consultar os parágrafos já salvos.</p>}
    <section className="g80-painel g80-fita" aria-label="Lista de parágrafos">
      <h2>Parágrafos salvos</h2>
      <form className="g80-history-tools" onSubmit={e => { e.preventDefault(); changePage(filter); }}>
        <label htmlFor="history-filter">Filtrar por ID do lote</label>
        <input id="history-filter" type="text" value={filter} onChange={e => setFilter(e.target.value)} placeholder="Todos os lotes" />
        <button className="g80-mini" disabled={loading}>Filtrar</button>
        {query.lote && <button className="g80-mini" type="button" onClick={() => { setFilter(''); changePage(''); }}>Todos os parágrafos</button>}
        {batchId && <button className="g80-mini" type="button" onClick={() => { setFilter(batchId); changePage(batchId); }}>Lote atual</button>}
      </form>
      <div className="g80-mini-acoes"><button className="g80-mini" onClick={() => download('csv')}>Exportar CSV</button><button className="g80-mini" onClick={() => download('jsonl')}>Exportar JSONL</button></div>
      {error && <div role="alert" className="g80-erro">{error} <button className="g80-mini" onClick={() => setRetry(value => value + 1)}>Tentar novamente</button></div>}
      {loading ? <p role="status">Carregando histórico…</p> : !rows.length ? <p className="g80-vazio">Nenhum parágrafo encontrado.</p> :
        <ol start={query.offset + 1} aria-label="Parágrafos salvos">{rows.map(item => <li key={item.id}>
          <button aria-expanded={selected?.id === item.id} aria-controls={selected?.id === item.id ? 'history-detail' : undefined} onClick={() => setSelected(item)}>
            <span className="g80-hora">#{item.id} · {date(item.criado_em)} · {item.status === 'ok' ? 'OK' : 'FALHOU'}{item.aprovado === true ? ' ✓' : item.aprovado === false ? ' ✕' : ''}</span>
            <span className="g80-resumo">{item.texto || item.motivo_falha}</span>
          </button>
        </li>)}</ol>}
      <div className="g80-history-pagination">
        <button className="g80-mini" disabled={loading || !query.offset} onClick={() => changePage(query.lote, Math.max(0, query.offset - PAGE_SIZE))}>Anteriores</button>
        <span>{!loading && rows.length ? `Exibindo ${query.offset + 1}–${query.offset + rows.length}` : ''}</span>
        <button className="g80-mini" disabled={loading || !hasMore} onClick={() => changePage(query.lote, query.offset + PAGE_SIZE)}>Próximos</button>
      </div>
    </section>
    {selected && <section className="g80-crt g80-history-detail" id="history-detail" ref={detail} tabIndex={-1} aria-label="Detalhes do parágrafo">
      <h2>Parágrafo #{selected.id}</h2>
      <ParagraphItem key={selected.id} item={selected} index={selected.id - 1} config={config} busy={busy}
        apiKey={apiKey} speechSettings={speechSettings} onSpeechSettings={onSpeechSettings}
        onApprove={approve} onRegenerate={onRegenerate} expandedMetadata />
    </section>}
  </main>;
}
