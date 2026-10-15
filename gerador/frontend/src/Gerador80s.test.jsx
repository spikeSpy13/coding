import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Gerador80s from './Gerador80s.jsx';

const config = {
  eixos: {tipo_texto: {nome:'Tipo de texto', camada:1, valores:['descricao']}, tamanho:{nome:'Tamanho',camada:2,valores:['curto']},ousadia:{nome:'Ousadia',camada:3,valores:['equilibrada'],padrao:'equilibrada'}},
  rotulos: {tipo_texto:{descricao:'Descrição'},tamanho:{curto:'Curto'},ousadia:{equilibrada:'Equilibrada'}},
  temperatura: {suportada:false,min:0,max:1,padrao:1,jitter_lote:0.15},
  modelo:'', chave_configurada:false, padroes:{max_tokens:4096,concorrencia:5,limiar_similaridade:0.4},
};
const item = {id:1, texto:'O jardim floresce todas as manhãs. As crianças brincam perto da fonte.',
  parametros_finais:{tipo_texto:'descricao',tamanho:'curto',ousadia:'equilibrada',tema:'jardim'},
  modelo:'provider/test',temperatura:null,status:'ok',avisos:[],prompt:'Prompt salvo',criado_em:'2026-10-15T12:00:00Z',metadados:{modelo_solicitado:'provider/test'}};
let requests, generated;

beforeEach(() => {
  localStorage.clear(); sessionStorage.clear(); requests=[]; generated=[];
  vi.stubGlobal('fetch',vi.fn(async (path, options={}) => {
    requests.push({path,options});
    let data;
    if(path==='/parametros') data=config;
    else if(path==='/configuracao') data={...config, modelo:JSON.parse(options.body).modelo};
    else if(path.startsWith('/historico')) data=generated;
    else if(path==='/gerar') {data=item;generated=[item];}
    else if(path==='/gerar/lote') data={lote_id:'batch-1',status:'pendente'};
    else if(path==='/lotes/batch-1') data={lote_id:'batch-1',status:'concluido',n_processado:1,n_solicitado:1,n_ok:1,itens:[item],metricas:null};
    else if(path==='/geracoes/1') data={...item,aprovado:JSON.parse(options.body).aprovado};
    else throw new Error('Unexpected path '+path);
    return {ok:true,json:async()=>data};
  }));
});
afterEach(() => {cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();});

async function setupModel(user) {
  await screen.findByLabelText('Chave OpenRouter');
  await user.type(screen.getByLabelText('Chave OpenRouter'),'private-key-test');
  await user.click(screen.getByRole('button',{name:'Adicionar modelo'}));
  await user.type(screen.getByLabelText('Identificador do modelo'),'provider/test');
  await user.click(screen.getByRole('button',{name:'Adicionar ao seletor'}));
  await waitFor(() => expect(screen.getByLabelText('Modelo OpenRouter').value).toBe('provider/test'));
}

describe('Interface real', () => {
  it('sends configurable truncation recovery and reasoning settings',async () => {
    const user=userEvent.setup();render(<Gerador80s/>);await setupModel(user);
    await user.click(screen.getByText('Ajustes de geração'));
    expect(screen.getByLabelText('Tokens por tentativa inicial').value).toBe('4096');
    await user.selectOptions(screen.getByLabelText('Raciocínio do modelo'),'baixo');
    fireEvent.change(screen.getByLabelText('Teto de tokens por tentativa'),{target:{value:'6144'}});
    await user.click(screen.getByRole('button',{name:'Gerar',exact:true}));
    await waitFor(()=>expect(requests.some(r=>r.path==='/gerar')).toBe(true));
    const body=JSON.parse(requests.find(r=>r.path==='/gerar').options.body);
    expect(body.max_tokens).toBe(4096);
    expect(body.teto_tokens).toBe(6144);
    expect(body.recuperar_truncamento).toBe(true);
    expect(body.raciocinio).toBe('baixo');
  });
  it('adds models, sends credentials only in the body, and regenerates fixed parameters',async () => {
    const user=userEvent.setup(); render(<Gerador80s/>);
    await setupModel(user);
    expect(requests.some(r=>r.path==='/gerar')).toBe(false);
    expect(JSON.stringify(localStorage)).not.toContain('private-key-test');
    await user.click(screen.getByRole('button',{name:'Gerar',exact:true}));
    await screen.findByText(item.texto,{selector:'.g80-texto'});
    let sent=requests.find(r=>r.path==='/gerar');
    expect(JSON.parse(sent.options.body).api_key).toBe('private-key-test');
    expect(JSON.parse(sent.options.body)).not.toHaveProperty('temperatura');
    expect(requests.every(r=>!r.path.includes('private-key-test'))).toBe(true);
    await user.click(screen.getByRole('button',{name:'Regenerar com os mesmos parâmetros'}));
    await waitFor(()=>expect(requests.filter(r=>r.path==='/gerar')).toHaveLength(2));
    sent=requests.filter(r=>r.path==='/gerar')[1];
    expect(JSON.parse(sent.options.body).parametros).toEqual(item.parametros_finais);
    await user.click(screen.getByRole('button',{name:'Aprovar',exact:true}));
    await waitFor(()=>expect(screen.getByRole('button',{name:'Aprovar',exact:true}).getAttribute('aria-pressed')).toBe('true'));
  });

  it('shows a ruler only for enabled models and sends its chosen value',async () => {
    const user=userEvent.setup();render(<Gerador80s/>);await setupModel(user);
    expect(screen.queryByRole('slider')).toBeNull();
    await user.click(screen.getByLabelText('Habilitar temperatura para este modelo'));
    fireEvent.change(screen.getByRole('slider',{name:'Temperatura'}),{target:{value:'0.35'}});
    await user.click(screen.getByRole('button',{name:'Gerar',exact:true}));
    await waitFor(()=>expect(requests.some(r=>r.path==='/gerar')).toBe(true));
    const body=JSON.parse(requests.find(r=>r.path==='/gerar').options.body);
    expect(body.temperatura).toBe(0.35);
    expect(body.temperatura_suportada).toBe(true);
  });

  it('keeps model list but does not persist an unsaved key',async () => {
    const user=userEvent.setup(); const first=render(<Gerador80s/>);await setupModel(user);
    first.unmount();render(<Gerador80s/>);
    await screen.findByLabelText('Chave OpenRouter');
    expect(screen.getByLabelText('Chave OpenRouter').value).toBe('');
    expect(await screen.findByRole('option',{name:'provider/test'})).toBeTruthy();
    await user.click(screen.getByRole('button',{name:'Gerar',exact:true}));
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(requests.some(r=>r.path==='/gerar')).toBe(false);
  });

  it('restores the saved key, all models, last selection, and temperature capability',async () => {
    const user=userEvent.setup();const first=render(<Gerador80s/>);await setupModel(user);
    await user.click(screen.getByRole('button',{name:'Salvar chave',exact:true}));
    await user.click(screen.getByRole('button',{name:'Adicionar modelo',exact:true}));
    await user.type(screen.getByLabelText('Identificador do modelo'),'another/model');
    await user.click(screen.getByLabelText('Este modelo aceita temperatura'));
    await user.click(screen.getByRole('button',{name:'Adicionar ao seletor',exact:true}));
    first.unmount();render(<Gerador80s/>);
    await screen.findByLabelText('Chave OpenRouter');
    expect(screen.getByLabelText('Chave OpenRouter').value).toBe('private-key-test');
    await waitFor(()=>expect(screen.getByLabelText('Modelo OpenRouter').value).toBe('another/model'));
    expect(screen.getByRole('option',{name:'provider/test'})).toBeTruthy();
    expect(screen.getByRole('option',{name:'another/model'})).toBeTruthy();
    expect(screen.getByRole('slider',{name:'Temperatura'})).toBeTruthy();
    expect(screen.getByText('Chave salva neste navegador. Ela estará disponível ao reabrir a página.')).toBeTruthy();
    expect(requests.every(r=>!r.path.includes('private-key-test'))).toBe(true);
  });

  it('removes the saved key without deleting models',async () => {
    const user=userEvent.setup();const first=render(<Gerador80s/>);await setupModel(user);
    await user.click(screen.getByRole('button',{name:'Salvar chave',exact:true}));
    await user.click(screen.getByRole('button',{name:'Apagar chave salva',exact:true}));
    first.unmount();render(<Gerador80s/>);
    await screen.findByLabelText('Chave OpenRouter');
    expect(screen.getByLabelText('Chave OpenRouter').value).toBe('');
    expect(localStorage.getItem('gerador-openrouter-key')).toBeNull();
    expect(screen.getByRole('option',{name:'provider/test'})).toBeTruthy();
  });

  it('reports failed persistence instead of claiming the key was saved',async () => {
    const user=userEvent.setup();render(<Gerador80s/>);await setupModel(user);
    const original=Storage.prototype.setItem;
    vi.spyOn(Storage.prototype,'setItem').mockImplementation(function(key,value) {
      if(key==='gerador-openrouter-key') throw new DOMException('Quota exceeded','QuotaExceededError');
      return original.call(this,key,value);
    });
    await user.click(screen.getByRole('button',{name:'Salvar chave',exact:true}));
    expect((await screen.findByRole('alert')).textContent).toContain('não permitiu salvar a chave');
    expect(screen.queryByText('Chave salva neste navegador. Ela estará disponível ao reabrir a página.')).toBeNull();
  });

  it('polls batch completion and offers vary only in batch mode',async () => {
    const user=userEvent.setup(); render(<Gerador80s/>);await setupModel(user);
    expect(screen.queryAllByRole('option',{name:'Variar no lote'})).toHaveLength(0);
    await user.click(screen.getByRole('button',{name:'Lote',exact:true}));
    expect(screen.getAllByRole('option',{name:'Variar no lote'})).toHaveLength(3);
    await user.click(screen.getByRole('button',{name:'Gerar lote'}));
    await screen.findByText('1 de 1 · 1 validados');
    expect(requests.some(r=>r.path==='/lotes/batch-1')).toBe(true);
    expect(sessionStorage.getItem('gerador-lote-ativo')).toBeNull();
  });
});
