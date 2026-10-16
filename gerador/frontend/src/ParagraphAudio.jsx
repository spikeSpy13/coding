import React, { useEffect, useId, useRef, useState } from 'react';

const STORAGE_KEY = 'gerador-leitura';
const DEFAULTS = { modelo: 'google/gemini-3.8-flash-lite-tts', voz: '', velocidade: 1 };
// OpenRouter /api/v1/models?output_modalities=speech, Gemini TTS supported_voices.
const GEMINI_VOICES = [
  'Zephyr', 'Puck', 'Charon', 'Kore', 'Fenrir', 'Leda', 'Orus', 'Aoede', 'Callirrhoe', 'Autonoe',
  'Enceladus', 'Iapetus', 'Umbriel', 'Algieba', 'Despina', 'Erinome', 'Algenib', 'Rasalgethi',
  'Laomedeia', 'Achernar', 'Alnilam', 'Schedar', 'Gacrux', 'Pulcherrima', 'Achird', 'Zubenelgenubi',
  'Vindemiatrix', 'Sadachbia', 'Sadaltager', 'Sulafat',
];

export function storedSpeechSettings() {
  try {
    const value = JSON.parse(localStorage.getItem(STORAGE_KEY));
    if (!value || typeof value.modelo !== 'string' || typeof value.voz !== 'string' ||
        !Number.isFinite(value.velocidade) || value.velocidade < 0.5 || value.velocidade > 2) return DEFAULTS;
    return { modelo: value.modelo.slice(0, 200), voz: value.voz.slice(0, 120), velocidade: value.velocidade };
  } catch { return DEFAULTS; }
}

export default function ParagraphAudio({ text, apiKey, serverKey, settings, onSettings }) {
  const id = useId();
  const audio = useRef(null);
  const url = useRef(null);
  const request = useRef(null);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(settings);
  const [loading, setLoading] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const gemini = draft.modelo.trim().startsWith('google/gemini-') && draft.modelo.includes('-tts');

  useEffect(() => { setDraft(settings); }, [settings]);
  useEffect(() => { audio.current.playbackRate = settings.velocidade; }, [settings.velocidade]);

  useEffect(() => {
    const element = audio.current;
    function stop(event) {
      if (event.detail === id) return;
      request.current?.abort();
      request.current = null;
      element.pause();
      setPlaying(false); setLoading(false);
    }
    window.addEventListener('gerador-audio-play', stop);
    setLoading(false); setPlaying(false);
    return () => {
      window.removeEventListener('gerador-audio-play', stop);
      request.current?.abort();
      request.current = null;
      element.pause();
      element.removeAttribute('src');
      element.load();
      if (url.current) URL.revokeObjectURL(url.current);
      url.current = null;
    };
  }, [text, apiKey, settings.modelo, settings.voz, id]);

  function save() {
    const next = { modelo: draft.modelo.trim(), voz: draft.voz.trim(), velocidade: Number(draft.velocidade) };
    if (!next.modelo.includes('/') || /\s/.test(next.modelo) || next.modelo.startsWith('sk-')) {
      setError('Informe o identificador provedor/modelo de síntese de voz.'); return;
    }
    onSettings(next);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      setNotice('Configurações de leitura salvas neste navegador.'); setError('');
    } catch {
      setError('Não foi possível salvar neste navegador. Os ajustes valem para esta sessão.');
    }
  }

  function cancel() {
    request.current?.abort(); request.current = null; setLoading(false);
  }

  async function play() {
    if (playing) { audio.current.pause(); setPlaying(false); return; }
    if (!settings.modelo) { setOpen(true); setError('Configure o modelo de voz na seta e salve os ajustes.'); return; }
    if (!apiKey.trim() && !serverKey) { setError('Informe sua chave OpenRouter no topo da página.'); return; }
    window.dispatchEvent(new CustomEvent('gerador-audio-play', { detail: id }));
    setError(''); setNotice('');
    const controller = new AbortController();
    request.current = controller;
    try {
      if (!url.current) {
        setLoading(true);
        const response = await fetch('/audio/ler', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: controller.signal,
          body: JSON.stringify({ texto: text, modelo: settings.modelo, voz: settings.voz, api_key: apiKey.trim() || undefined }),
        });
        if (!response.ok) {
          const data = await response.json().catch(() => ({}));
          throw new Error(typeof data.detail === 'string' ? data.detail : 'Não foi possível gerar a leitura. Confira a configuração do modelo.');
        }
        const blob = await response.blob();
        if (controller.signal.aborted) return;
        url.current = URL.createObjectURL(blob);
        audio.current.src = url.current;
      }
      if (controller.signal.aborted) return;
      setLoading(false);
      audio.current.playbackRate = settings.velocidade;
      try { await audio.current.play(); }
      catch (e) {
        if (!controller.signal.aborted) {
          if (e.name === 'NotAllowedError') setNotice('Áudio pronto. Toque em Ouvir para iniciar.');
          else setError('O navegador não conseguiu reproduzir este áudio.');
        }
      }
    } catch (e) {
      if (!controller.signal.aborted) setError(e instanceof TypeError ? 'Não foi possível conectar para gerar a leitura.' : e.message);
    } finally {
      if (request.current === controller) { request.current = null; setLoading(false); }
    }
  }

  return <section className="g80-audio" aria-label="Leitura do parágrafo">
    <div className="g80-mini-acoes">
      <button className="g80-mini" disabled={loading || !text.trim()} onClick={play}>
        {loading ? 'Gerando áudio…' : playing ? 'Ⅱ Pausar' : '▶ Ouvir'}
      </button>
      <button className="g80-mini" aria-label="Configurar leitura" aria-expanded={open} aria-controls={`${id}-settings`} onClick={() => setOpen(!open)}>{open ? '▴' : '▾'}</button>
      {loading && <button className="g80-mini" onClick={cancel}>Cancelar leitura</button>}
    </div>
    <audio ref={audio} preload="none" onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)}
      onError={() => setError('Não foi possível reproduzir o áudio recebido. Confira o modelo de voz.')} />
    {open && <div className="g80-audio-config" id={`${id}-settings`}>
      <p>A leitura usa a mesma chave OpenRouter da página. Escolha um modelo de síntese de voz (TTS).</p>
      <div className="g80-campos">
        <label className="g80-campo">Modelo de voz OpenRouter
          <input value={draft.modelo} maxLength={200} placeholder="provedor/modelo-tts" autoComplete="off" onChange={e => setDraft({ ...draft, modelo: e.target.value })} />
        </label>
        <label className="g80-campo">Voz (opcional)
          {gemini ? <select value={draft.voz} onChange={e => setDraft({ ...draft, voz: e.target.value })}>
            <option value="">Kore (padrão)</option>
            {draft.voz && !GEMINI_VOICES.includes(draft.voz) && <option value={draft.voz}>{draft.voz} (configurada anteriormente)</option>}
            {GEMINI_VOICES.map(voice => <option key={voice} value={voice}>{voice}</option>)}
          </select> : <input value={draft.voz} maxLength={120} placeholder="Voz do provedor" onChange={e => setDraft({ ...draft, voz: e.target.value })} />}
        </label>
        <label className="g80-campo">Velocidade de reprodução: {draft.velocidade}×
          <input type="range" min="0.5" max="2" step="0.05" value={draft.velocidade} onChange={e => setDraft({ ...draft, velocidade: Number(e.target.value) })} />
        </label>
      </div>
      <small>No Gemini TTS, voz vazia usa Kore; você também pode escolher Puck, Aoede ou outra voz compatível. Outros modelos usam as vozes do respectivo provedor. A velocidade é ajustada no navegador. Gerar áudio utiliza créditos do OpenRouter.</small>
      <button className="g80-mini" onClick={save}>Salvar configurações de leitura</button>
    </div>}
    {loading && <p role="status">Preparando a leitura do parágrafo…</p>}
    {notice && <p role="status">{notice}</p>}
    {error && <p className="g80-erro" role="alert">{error}</p>}
  </section>;
}
