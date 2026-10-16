import { defineConfig } from 'vite';

export default defineConfig({
  server: { proxy: Object.fromEntries(['/parametros', '/configuracao', '/gerar', '/lotes', '/historico', '/geracoes', '/exportar', '/saude', '/audio'].map(path => [path, 'http://127.0.0.1:8001'])) },
  test: { environment: 'jsdom', globals: true },
});
