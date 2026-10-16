import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import HistoryPage from './HistoryPage.jsx';

const rows=Array.from({length:23},(_,i)=>({id:i+1,texto:`Texto salvo ${i+1}. Outro período.`,parametros_finais:{tema:`tema ${i+1}`},prompt:`Prompt ${i+1}`,modelo:`provider/model-${i+1}`,status:'ok',criado_em:'2026-10-16T12:00:00Z',avisos:[]}));
const props={config:{eixos:{},rotulos:{},chave_configurada:false},apiKey:'test-key',speechSettings:{modelo:'provider/tts',voz:'',velocidade:1},onSpeechSettings:vi.fn(),busy:false,version:0,batchId:'batch-1',onApprove:vi.fn(),onRegenerate:vi.fn()};
beforeEach(()=>{
  vi.spyOn(HTMLMediaElement.prototype,'pause').mockImplementation(()=>{});
  vi.spyOn(HTMLMediaElement.prototype,'load').mockImplementation(()=>{});
  vi.stubGlobal('fetch',vi.fn(async path=>{
    const query=new URLSearchParams(path.split('?')[1]);
    const offset=Number(query.get('offset'));
    return {ok:true,json:async()=>query.get('lote_id') ? [rows[22]] : rows.slice(offset,offset+Number(query.get('limite')))};
  }));
});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();});

it('pages through all paragraphs and opens full details below the list',async()=>{
  render(<HistoryPage {...props}/>);
  const list=await screen.findByRole('list',{name:'Parágrafos salvos'});
  expect(within(list).getAllByRole('button')).toHaveLength(20);
  fireEvent.click(screen.getByRole('button',{name:'Próximos'}));
  await screen.findByText('Exibindo 21–23');
  expect(within(screen.getByRole('list',{name:'Parágrafos salvos'})).getAllByRole('button')).toHaveLength(3);
  expect(screen.getByRole('button',{name:'Próximos'}).disabled).toBe(true);
  fireEvent.click(screen.getByRole('button',{name:/Texto salvo 21\./}));
  const detail=screen.getByRole('region',{name:'Detalhes do parágrafo'});
  expect(within(detail).getByText('Prompt 21').closest('details').open).toBe(true);
  expect(detail.textContent).toContain('provider/model-21');
  expect(within(detail).getByRole('list',{name:'Parâmetros usados'}).textContent).toContain('tema 21');
  expect(within(detail).getByRole('button',{name:'▶ Ouvir'})).toBeTruthy();
  expect(document.activeElement).toBe(detail);
  fireEvent.click(screen.getByRole('button',{name:'Anteriores'}));
  await screen.findByText('Exibindo 1–20');
  expect(screen.queryByRole('region',{name:'Detalhes do parágrafo'})).toBeNull();
});

it('filters by batch and returns to all saved paragraphs',async()=>{
  render(<HistoryPage {...props}/>);
  await screen.findByRole('list',{name:'Parágrafos salvos'});
  fireEvent.change(screen.getByLabelText('Filtrar por ID do lote'),{target:{value:'batch-2'}});
  fireEvent.click(screen.getByRole('button',{name:'Filtrar',exact:true}));
  await screen.findByText('Exibindo 1–1');
  expect(fetch.mock.calls.at(-1)[0]).toContain('lote_id=batch-2');
  fireEvent.click(screen.getByRole('button',{name:'Todos os parágrafos'}));
  await screen.findByText('Exibindo 1–20');
  expect(fetch.mock.calls.at(-1)[0]).not.toContain('lote_id');
});

it('shows a loading failure and lets the user retry',async()=>{
  fetch.mockRejectedValueOnce(new Error('Falha de conexão.'));
  render(<HistoryPage {...props}/>);
  expect((await screen.findByRole('alert')).textContent).toContain('Falha de conexão.');
  fireEvent.click(screen.getByRole('button',{name:'Tentar novamente'}));
  await screen.findByRole('list',{name:'Parágrafos salvos'});
  expect(screen.queryByRole('alert')).toBeNull();
});

it('exports the applied filter rather than an unsent draft',async()=>{
  const click=vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});
  vi.stubGlobal('URL',{createObjectURL:vi.fn(()=>'blob:export'),revokeObjectURL:vi.fn()});
  render(<HistoryPage {...props}/>);
  await screen.findByRole('list',{name:'Parágrafos salvos'});
  fireEvent.click(screen.getByRole('button',{name:'Lote atual'}));
  await screen.findByText('Exibindo 1–1');
  fireEvent.change(screen.getByLabelText('Filtrar por ID do lote'),{target:{value:'unsent'}});
  fetch.mockResolvedValueOnce({ok:true,blob:async()=>new Blob(['{}'])});
  fireEvent.click(screen.getByRole('button',{name:'Exportar JSONL'}));
  await waitFor(()=>expect(click).toHaveBeenCalled());
  expect(fetch.mock.calls.at(-1)[0]).toBe('/exportar?formato=jsonl&lote_id=batch-1');
});
