import React, { useState } from 'react';
import ParagraphAudio from './ParagraphAudio.jsx';

const label = (config, axis, value) => config.rotulos[axis]?.[value] || value;

export default function ParagraphItem({ item, index, config, busy, onRegenerate, onApprove, apiKey, speechSettings, onSpeechSettings, expandedMetadata = false }) {
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
    <ParagraphAudio text={item.texto || ''} apiKey={apiKey} serverKey={config.chave_configurada} settings={speechSettings} onSettings={onSpeechSettings} />
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
    <details className="g80-details" open={expandedMetadata}><summary>Prompt e metadados</summary>
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

