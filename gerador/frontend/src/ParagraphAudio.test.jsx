import React, { useState } from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import ParagraphAudio, { storedSpeechSettings } from './ParagraphAudio.jsx';

const settings = { modelo: 'provider/tts', voz: '', velocidade: 1 };
const text = 'O jardim floresce pela manhã. As crianças brincam perto da fonte.';
const props = { text, apiKey: 'secret-test-key', serverKey: false, settings, onSettings: vi.fn() };
let createURL, revokeURL;

beforeEach(() => {
  localStorage.clear();
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockImplementation(function () { this.dispatchEvent(new Event('play')); return Promise.resolve(); });
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(function () { this.dispatchEvent(new Event('pause')); });
  vi.spyOn(HTMLMediaElement.prototype, 'load').mockImplementation(() => {});
  createURL = vi.fn(() => 'blob:audio-test'); revokeURL = vi.fn();
  vi.stubGlobal('URL', { createObjectURL: createURL, revokeObjectURL: revokeURL });
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, blob: async () => new Blob(['ID3audio'], { type:'audio/mpeg' }) })));
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it('reads the exact paragraph with the shared key; pause and replay reuse audio', async () => {
  const view = render(<ParagraphAudio {...props} />);
  fireEvent.click(screen.getByRole('button', { name: '▶ Ouvir' }));
  await screen.findByRole('button', { name: 'Ⅱ Pausar' });
  expect(fetch).toHaveBeenCalledTimes(1);
  const [path, options] = fetch.mock.calls[0];
  expect(path).toBe('/audio/ler');
  expect(JSON.parse(options.body)).toEqual({ texto:text, modelo:settings.modelo, voz:settings.voz, api_key:props.apiKey });
  fireEvent.click(screen.getByRole('button', { name: 'Ⅱ Pausar' }));
  fireEvent.click(screen.getByRole('button', { name: '▶ Ouvir' }));
  await screen.findByRole('button', { name: 'Ⅱ Pausar' });
  fireEvent.ended(view.container.querySelector('audio'));
  fireEvent.click(screen.getByRole('button', { name: '▶ Ouvir' }));
  await screen.findByRole('button', { name: 'Ⅱ Pausar' });
  expect(fetch).toHaveBeenCalledTimes(1);
  view.unmount(); expect(revokeURL).toHaveBeenCalledWith('blob:audio-test');
});

it('saves model, voice and speed and restores them on reopening', async () => {
  function Saved() {
    const [value, setValue] = useState(storedSpeechSettings);
    return <ParagraphAudio {...props} settings={value} onSettings={setValue} />;
  }
  const view = render(<Saved />);
  fireEvent.click(screen.getByRole('button', { name:'Configurar leitura' }));
  fireEvent.change(screen.getByLabelText('Modelo de voz OpenRouter'), {target:{value:'provider/speech'}});
  fireEvent.change(screen.getByLabelText('Voz (opcional)'), {target:{value:'voz-pt'}});
  fireEvent.change(screen.getByRole('slider'), {target:{value:'1.25'}});
  fireEvent.click(screen.getByRole('button', { name:'Salvar configurações de leitura' }));
  expect(screen.getByRole('status').textContent).toContain('salvas');
  expect(storedSpeechSettings()).toEqual({modelo:'provider/speech',voz:'voz-pt',velocidade:1.25});
  expect(JSON.stringify(localStorage)).not.toContain(props.apiKey);
  view.unmount(); render(<Saved />);
  fireEvent.click(screen.getByRole('button', { name:'Configurar leitura' }));
  expect(screen.getByLabelText('Modelo de voz OpenRouter').value).toBe('provider/speech');
  expect(screen.getByRole('slider').value).toBe('1.25');
});

it('requires a TTS model and key before requesting audio', () => {
  const view = render(<ParagraphAudio {...props} settings={{...settings,modelo:''}} />);
  fireEvent.click(screen.getByRole('button', { name:'▶ Ouvir' }));
  expect(screen.getByLabelText('Modelo de voz OpenRouter')).toBeTruthy();
  expect(screen.getByRole('alert').textContent).toContain('Configure');
  view.rerender(<ParagraphAudio {...props} apiKey="" />);
  fireEvent.click(screen.getByRole('button', { name:'▶ Ouvir' }));
  expect(screen.getByRole('alert').textContent).toContain('chave OpenRouter');
  expect(fetch).not.toHaveBeenCalled();
});

it('shows provider errors without breaking playback controls', async () => {
  fetch.mockResolvedValueOnce({ok:false, json:async()=>({detail:'Saldo insuficiente.'})});
  render(<ParagraphAudio {...props} />);
  fireEvent.click(screen.getByRole('button', { name:'▶ Ouvir' }));
  expect((await screen.findByRole('alert')).textContent).toBe('Saldo insuficiente.');
  expect(screen.getByRole('button', { name:'▶ Ouvir' }).disabled).toBe(false);
});

it('aborts pending requests on cancel and unmount', async () => {
  fetch.mockImplementation(() => new Promise(() => {}));
  const view = render(<ParagraphAudio {...props} />);
  fireEvent.click(screen.getByRole('button', { name:'▶ Ouvir' }));
  const signal = fetch.mock.calls[0][1].signal;
  fireEvent.click(screen.getByRole('button', { name:'Cancelar leitura' }));
  expect(signal.aborted).toBe(true);
  fireEvent.click(screen.getByRole('button', { name:'▶ Ouvir' }));
  const nextSignal = fetch.mock.calls[1][1].signal;
  view.unmount(); expect(nextSignal.aborted).toBe(true);
});

it('stops another player before reading the next paragraph', async () => {
  render(<><ParagraphAudio {...props} /><ParagraphAudio {...props} text="Outro parágrafo." /></>);
  const players = screen.getAllByRole('region', { name:'Leitura do parágrafo' });
  fireEvent.click(within(players[0]).getByRole('button', { name:'▶ Ouvir' }));
  await within(players[0]).findByRole('button', { name:'Ⅱ Pausar' });
  fireEvent.click(within(players[1]).getByRole('button', { name:'▶ Ouvir' }));
  await within(players[1]).findByRole('button', { name:'Ⅱ Pausar' });
  expect(within(players[0]).getByRole('button', { name:'▶ Ouvir' })).toBeTruthy();
});

it('discards cached audio when voice settings change', async () => {
  const view = render(<ParagraphAudio {...props} />);
  fireEvent.click(screen.getByRole('button', { name:'▶ Ouvir' }));
  await screen.findByRole('button', { name:'Ⅱ Pausar' });
  view.rerender(<ParagraphAudio {...props} settings={{...settings,voz:'other'}} />);
  expect(revokeURL).toHaveBeenCalledWith('blob:audio-test');
  fireEvent.click(screen.getByRole('button', { name:'▶ Ouvir' }));
  await screen.findByRole('button', { name:'Ⅱ Pausar' });
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(JSON.parse(fetch.mock.calls[1][1].body).voz).toBe('other');
});

it('keeps fetched audio when the browser initially blocks autoplay', async () => {
  HTMLMediaElement.prototype.play.mockRejectedValueOnce(new DOMException('blocked','NotAllowedError'));
  render(<ParagraphAudio {...props} />);
  fireEvent.click(screen.getByRole('button', { name:'▶ Ouvir' }));
  await waitFor(() => expect(screen.getByRole('status').textContent).toContain('Áudio pronto'));
  fireEvent.click(screen.getByRole('button', { name:'▶ Ouvir' }));
  await screen.findByRole('button', { name:'Ⅱ Pausar' });
  expect(fetch).toHaveBeenCalledTimes(1);
});

it('rejects corrupted persisted settings', () => {
  localStorage.setItem('gerador-leitura','{"modelo":4}');
  expect(storedSpeechSettings()).toEqual({modelo:'google/gemini-3.8-flash-lite-tts',voz:'',velocidade:1});
});

it('changes playback speed locally without another paid synthesis request', async () => {
  const view = render(<ParagraphAudio {...props} settings={{...settings,modelo:'google/gemini-3.8-flash-lite-tts'}} />);
  fireEvent.click(screen.getByRole('button', {name:'▶ Ouvir'}));
  await screen.findByRole('button', {name:'Ⅱ Pausar'});
  view.rerender(<ParagraphAudio {...props} settings={{...settings,modelo:'google/gemini-3.8-flash-lite-tts',velocidade:1.5}} />);
  expect(view.container.querySelector('audio').playbackRate).toBe(1.5);
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(JSON.parse(fetch.mock.calls[0][1].body)).not.toHaveProperty('velocidade');
  expect(revokeURL).not.toHaveBeenCalled();
});

it('offers the Gemini voice selector, persists the choice and sends it to speech', async () => {
  function Saved() {
    const [value,setValue] = useState(storedSpeechSettings);
    return <ParagraphAudio {...props} settings={value} onSettings={setValue} />;
  }
  const view = render(<Saved />);
  fireEvent.click(screen.getByRole('button', {name:'Configurar leitura'}));
  const voice = screen.getByRole('combobox', {name:'Voz (opcional)'});
  expect(within(voice).getAllByRole('option')).toHaveLength(31);
  expect(within(voice).getByRole('option', {name:'Aoede',exact:true})).toBeTruthy();
  fireEvent.change(voice,{target:{value:'Puck'}});
  fireEvent.click(screen.getByRole('button', {name:'Salvar configurações de leitura'}));
  view.unmount(); render(<Saved />);
  fireEvent.click(screen.getByRole('button', {name:'Configurar leitura'}));
  expect(screen.getByRole('combobox', {name:'Voz (opcional)'}).value).toBe('Puck');
  fireEvent.click(screen.getByRole('button', {name:'▶ Ouvir'}));
  await screen.findByRole('button', {name:'Ⅱ Pausar'});
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toMatchObject({modelo:'google/gemini-3.8-flash-lite-tts',voz:'Puck'});
});

it('uses a free voice field for other providers and preserves a previously saved voice', () => {
  render(<ParagraphAudio {...props} settings={{...settings,modelo:'google/gemini-3.8-flash-lite-tts',voz:'FutureVoice'}} />);
  fireEvent.click(screen.getByRole('button', {name:'Configurar leitura'}));
  expect(screen.getByRole('combobox', {name:'Voz (opcional)'}).value).toBe('FutureVoice');
  fireEvent.change(screen.getByLabelText('Modelo de voz OpenRouter'),{target:{value:'provider/tts'}});
  expect(screen.queryByRole('combobox', {name:'Voz (opcional)'})).toBeNull();
  expect(screen.getByRole('textbox', {name:'Voz (opcional)'}).value).toBe('FutureVoice');
});
