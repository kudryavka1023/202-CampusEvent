"""SQLite 连接提供者与建表/索引/轻量迁移。

- 线程本地连接，每线程独立（请求/测试线程互不影响）；
- PRAGMA foreign_keys / WAL / busy_timeout；
- 部分唯一索引 ux_registration_active 是“同一学生同一活动最多一条有效报名”的最终防线；
- messages.event_key UNIQUE 保证站内通知幂等；
- email_log.event_key UNIQUE 保证模拟邮件幂等；
- 旧库启动时用 PRAGMA table_info + ALTER TABLE 补列，不清空数据。
"""
from __future__ import annotations

import sqlite3
import threading

DDL = """
CREATE TABLE IF NOT EXISTS students (
    student_id TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    grade      INTEGER NOT NULL DEFAULT 1 CHECK (grade BETWEEN 1 AND 4),
    email      TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS activities (
    activity_id TEXT PRIMARY KEY,
    title       TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 100),
    category    TEXT NOT NULL,
    start_at    TEXT NOT NULL,
    location    TEXT NOT NULL,
    capacity    INTEGER NOT NULL CHECK (capacity > 0),
    policy_type TEXT NOT NULL CHECK (policy_type IN ('DIRECT','APPROVAL')),
    allowed_grades TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS registrations (
    registration_id TEXT PRIMARY KEY,
    activity_id     TEXT NOT NULL REFERENCES activities(activity_id) ON DELETE RESTRICT,
    student_id      TEXT NOT NULL REFERENCES students(student_id) ON DELETE RESTRICT,
    status          TEXT NOT NULL CHECK (status IN ('PENDING','APPROVED','REJECTED','CANCELLED')),
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    message_id  TEXT PRIMARY KEY,
    student_id  TEXT NOT NULL REFERENCES students(student_id) ON DELETE RESTRICT,
    activity_id TEXT NOT NULL REFERENCES activities(activity_id) ON DELETE RESTRICT,
    content     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    is_read     INTEGER NOT NULL DEFAULT 0 CHECK (is_read IN (0,1)),
    event_key   TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS email_log (
    email_id        TEXT PRIMARY KEY,
    event_key       TEXT NOT NULL UNIQUE,
    registration_id TEXT NOT NULL,
    student_id      TEXT NOT NULL REFERENCES students(student_id) ON DELETE RESTRICT,
    recipient       TEXT NOT NULL,
    subject         TEXT NOT NULL,
    content         TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('SENT','FAILED')),
    error           TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_registration_active
    ON registrations(activity_id, student_id)
    WHERE status IN ('PENDING','APPROVED');

CREATE INDEX IF NOT EXISTS ix_registration_activity_status
    ON registrations(activity_id, status);

CREATE INDEX IF NOT EXISTS ix_registration_student_created
    ON registrations(student_id, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_message_student_created
    ON messages(student_id, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_email_log_created
    ON email_log(created_at DESC);
"""

# 演示账号覆盖 1—4 年级，便于 CR-01 验收。
DEMO_STUDENTS = [
    ("stu_demo1", "张三", 2, "zhangsan@campus.edu"),
    ("stu_demo2", "李四", 3, "lisi@campus.edu"),
    ("stu_demo3", "王五", 1, "wangwu@campus.edu"),
    ("stu_demo4", "赵六", 4, "zhaoliu@campus.edu"),
]


def _table_columns(conn: sqlite3.Connection, table: str):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


class ConnectionProvider:
    """线程本地 SQLite 连接；close_all() 用于请求 teardown / 重启模拟（C10）。"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._local = threading.local()

    def get(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path, timeout=5.0, check_same_thread=False)
            conn.isolation_level = None  # 手动 BEGIN/COMMIT
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA busy_timeout = 5000")
            self._local.conn = conn
        return conn

    def close_all(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            finally:
                self._local.conn = None

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        if column not in _table_columns(conn, table):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """baseline-v1 → change-v2 的增量迁移；可重复执行。"""
        self._ensure_column(conn, "students", "grade", "grade INTEGER NOT NULL DEFAULT 1")
        self._ensure_column(conn, "students", "email", "email TEXT NOT NULL DEFAULT ''")
        self._ensure_column(conn, "activities", "allowed_grades", "allowed_grades TEXT")

    def initialize(self, allowed_policy_types=("DIRECT", "APPROVAL")) -> None:
        """建表、索引、迁移、演示学生种子；重启后数据仍在（幂等）。

        allowed_policy_types 用于生成 activities.policy_type 的 CHECK；
        扩展新报名方式（如抽签）时只需在此注册枚举值并注册策略实现。
        """
        check_values = ", ".join(
            f"'{getattr(p, 'value', p)}'" for p in allowed_policy_types
        )
        ddl = DDL.replace(
            "CHECK (policy_type IN ('DIRECT','APPROVAL'))",
            f"CHECK (policy_type IN ({check_values}))",
        )
        conn = self.get()
        conn.executescript(ddl)
        self._migrate(conn)
        for student_id, name, grade, email in DEMO_STUDENTS:
            conn.execute(
                "INSERT OR IGNORE INTO students(student_id, name, grade, email) "
                "VALUES (?, ?, ?, ?)",
                (student_id, name, grade, email),
            )
            # 旧库补列后 email 为空，回填演示账号年级/邮箱；不覆盖用户已改数据。
            conn.execute(
                "UPDATE students SET grade=?, email=? WHERE student_id=? AND email=''",
                (grade, email, student_id),
            )
