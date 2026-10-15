export async function call(path, body, method = body === undefined ? 'GET' : 'POST', signal) {
  const response = await fetch(path, {
    method, signal,
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) {
    const detail = data.detail;
    throw new Error(Array.isArray(detail) ? detail.map(d => `${d.loc.slice(1).join('.')}: ${d.msg}`).join('; ') : detail || 'Não foi possível concluir a operação.');
  }
  return data;
}

export function storedModels() {
  try {
    const models = JSON.parse(localStorage.getItem('gerador-modelos') || '[]');
    return Array.isArray(models) ? models.filter(m => m && typeof m.id === 'string' && m.id.length <= 200 && !/\s/.test(m.id) && m.id.includes('/') && !m.id.startsWith('sk-')).slice(0, 100).map(m => ({id: m.id, temperature: m.temperature === true})) : [];
  } catch { return []; }
}

export function saveModels(models) {
  localStorage.setItem('gerador-modelos', JSON.stringify(models.map(({ id, temperature }) => ({ id, temperature }))));
}

export function storedApiKey() {
  try { return localStorage.getItem('gerador-openrouter-key') || ''; }
  catch { return ''; }
}

export function saveApiKey(key) {
  localStorage.setItem('gerador-openrouter-key', key.trim());
}

export function forgetApiKey() {
  localStorage.removeItem('gerador-openrouter-key');
}

export function storedSelectedModel() {
  try { return localStorage.getItem('gerador-modelo-selecionado') || ''; }
  catch { return ''; }
}

export function saveSelectedModel(model) {
  localStorage.setItem('gerador-modelo-selecionado', model);
}
