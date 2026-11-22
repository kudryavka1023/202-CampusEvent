"""事务管理器：write=True 时 BEGIN IMMEDIATE（写事务串行化），否则 BEGIN。"""
from __future__ import annotations

from contextlib import contextmanager


class TransactionManager:
    def __init__(self, provider):
        self.provider = provider

    @contextmanager
    def transaction(self, write: bool):
        conn = self.provider.get()
        conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        try:
            yield conn
        except Exception:
            conn.execute("ROLLBACK")
            raise
        else:
            conn.execute("COMMIT")
