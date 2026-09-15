"""Parameterized DB access. Runtime never creates schemas."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from src.config import settings

class DB:
    def __init__(self, url=None): self.url = url or settings.database_url
    @contextmanager
    def connect(self):
        if self.url.startswith('sqlite:///'):
            path = self.url[len('sqlite:///'):]
            if path != ':memory:': Path(path).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(path, timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA foreign_keys=ON')
            conn.execute('PRAGMA busy_timeout=10000')
        else:
            import psycopg
            from psycopg.rows import dict_row
            conn = psycopg.connect(self.url, row_factory=dict_row, connect_timeout=10)
        try:
            if not self.url.startswith('sqlite:///'):
                conn.execute("SET LOCAL statement_timeout = '10000ms'")
                conn.execute("SET LOCAL lock_timeout = '5000ms'")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback(); raise
        finally: conn.close()
    def execute(self, conn, sql, params=()):
        # All SQL is developer-authored. No model or user SQL is accepted.
        if not self.url.startswith('sqlite:///'): sql = sql.replace('?', '%s')
        return conn.execute(sql, params)
    def rows(self, sql, params=()):
        with self.connect() as conn:
            return [dict(r) for r in self.execute(conn,sql,params).fetchall()]
    def initialize(self):
        """Explicit administrative operation; do not call on API startup."""
        schema = Path(__file__).resolve().parent.parent/'sql/schema.sql'
        with self.connect() as conn:
            for statement in schema.read_text().split(';'):
                if statement.strip(): self.execute(conn,statement)
    def verify(self):
        with self.connect() as conn:
            for table in ['eail_documents','eail_chunks','eail_ingestion','eail_facts','eail_actions','eail_tasks']:
                self.execute(conn, f'SELECT 1 FROM {table} LIMIT 1')
db = DB()
