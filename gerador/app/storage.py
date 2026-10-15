import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def now():
    return datetime.now(timezone.utc).isoformat()


class Storage:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            connection.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS lotes (
                    id TEXT PRIMARY KEY, criado_em TEXT NOT NULL, n_solicitado INTEGER NOT NULL,
                    status TEXT NOT NULL, n_ok INTEGER NOT NULL DEFAULT 0, n_processado INTEGER NOT NULL DEFAULT 0,
                    parametros_base TEXT NOT NULL, metricas TEXT, erro TEXT
                );
                CREATE TABLE IF NOT EXISTS geracoes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, lote_id TEXT, indice INTEGER,
                    sessao_id TEXT NOT NULL, criado_em TEXT NOT NULL, parametros TEXT NOT NULL,
                    modo_sorteio TEXT NOT NULL, temperatura REAL, prompt TEXT NOT NULL,
                    texto TEXT NOT NULL, status TEXT NOT NULL, motivo_falha TEXT,
                    modelo TEXT NOT NULL, tokens_entrada INTEGER, tokens_saida INTEGER,
                    aprovado INTEGER, avisos TEXT NOT NULL, tentativas TEXT NOT NULL, metadados TEXT NOT NULL,
                    FOREIGN KEY(lote_id) REFERENCES lotes(id)
                );
                CREATE INDEX IF NOT EXISTS geracoes_sessao ON geracoes(sessao_id, id);
                CREATE INDEX IF NOT EXISTS geracoes_lote ON geracoes(lote_id, indice);
            ''')

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def interrupt_batches(self):
        with self.connection() as connection:
            connection.execute("UPDATE lotes SET status='interrompido', erro='Servidor reiniciado; itens já concluídos foram preservados.' WHERE status IN ('pendente', 'processando')")

    def save(self, item):
        data = dict(item)
        data['criado_em'] = now()
        for name in ('parametros', 'avisos', 'tentativas', 'metadados'):
            data[name] = json.dumps(data[name], ensure_ascii=False)
        columns = ','.join(data)
        with self.connection() as connection:
            cursor = connection.execute(f'INSERT INTO geracoes ({columns}) VALUES ({",".join("?" for _ in data)})', list(data.values()))
            row = connection.execute('SELECT * FROM geracoes WHERE id=?', (cursor.lastrowid,)).fetchone()
        return self.decode(row)

    @staticmethod
    def decode(row):
        data = dict(row)
        data['parametros_finais'] = json.loads(data.pop('parametros'))
        for name in ('avisos', 'tentativas', 'metadados'):
            data[name] = json.loads(data[name])
        data['aprovado'] = None if data['aprovado'] is None else bool(data['aprovado'])
        return data

    def history(self, limit=50, offset=0, batch_id=None, session_id=None, ok_only=False):
        clauses, values = [], []
        for column, value in [('lote_id', batch_id), ('sessao_id', session_id)]:
            if value is not None:
                clauses.append(column + '=?')
                values.append(value)
        if ok_only:
            clauses.append("status='ok'")
        query = 'SELECT * FROM geracoes' + (' WHERE ' + ' AND '.join(clauses) if clauses else '')
        with self.connection() as connection:
            rows = connection.execute(query + ' ORDER BY id DESC LIMIT ? OFFSET ?', [*values, limit, offset]).fetchall()
        return [self.decode(row) for row in rows]

    def approve(self, item_id, approved):
        with self.connection() as connection:
            cursor = connection.execute('UPDATE geracoes SET aprovado=? WHERE id=?', (approved, item_id))
            if not cursor.rowcount:
                return None
            return self.decode(connection.execute('SELECT * FROM geracoes WHERE id=?', (item_id,)).fetchone())

    def create_batch(self, n, base):
        batch_id = str(uuid4())
        with self.connection() as connection:
            connection.execute('INSERT INTO lotes (id,criado_em,n_solicitado,status,parametros_base) VALUES (?,?,?,?,?)',
                               (batch_id, now(), n, 'pendente', json.dumps(base, ensure_ascii=False)))
        return batch_id

    def update_batch(self, batch_id, status, stats=None, error=None):
        with self.connection() as connection:
            row = connection.execute("SELECT COUNT(*) AS total, COALESCE(SUM(status='ok'),0) AS ok FROM geracoes WHERE lote_id=?", (batch_id,)).fetchone()
            connection.execute('UPDATE lotes SET status=?,n_processado=?,n_ok=?,metricas=?,erro=? WHERE id=?',
                (status, row['total'], row['ok'], json.dumps(stats, ensure_ascii=False) if stats else None, error, batch_id))

    def batch(self, batch_id):
        with self.connection() as connection:
            row = connection.execute('SELECT * FROM lotes WHERE id=?', (batch_id,)).fetchone()
            if row is None:
                return None
            data = dict(row)
            rows = connection.execute('SELECT * FROM geracoes WHERE lote_id=? ORDER BY indice', (batch_id,)).fetchall()
        data['lote_id'] = data.pop('id')
        data['parametros_base'] = json.loads(data['parametros_base'])
        data['metricas'] = json.loads(data['metricas']) if data['metricas'] else None
        data['itens'] = [self.decode(row) for row in rows]
        return data
