"""SQLite Repository 实现（基础设施层）。

- 行 → 对象映射集中在这里；服务不接触 SQL；
- registrations.save 的唯一索引冲突 → DuplicateActiveError（服务映射 DUPLICATE_ACTIVE）；
- messages.save 的 event_key 冲突 → DuplicateEventKeyError（观察者按“已通知”处理）；
- activities.created_at/updated_at 由仓储写入，不进入 Activity 实体。
"""
from __future__ import annotations

import sqlite3
from typing import List, Optional

from ..domain.entities import Activity, Message, Registration, Student, now_str, parse_dt
from ..domain.enums import PolicyType, RegistrationStatus
from ..domain.errors import DuplicateActiveError, DuplicateEventKeyError
from ..domain.value_objects import ActivityStatistics, ActivitySummary, RegistrationSummary


def _escape_like(keyword: str) -> str:
    return keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class SqliteActivityRepository:
    def __init__(self, provider):
        self.provider = provider

    def _conn(self):
        return self.provider.get()

    def find_by_id(self, activity_id: str) -> Optional[Activity]:
        row = self._conn().execute(
            "SELECT activity_id, title, category, start_at, location, capacity, policy_type "
            "FROM activities WHERE activity_id = ?",
            (activity_id,),
        ).fetchone()
        return self._to_activity(row) if row else None

    def search_summaries(self, keyword: str, now) -> List[ActivitySummary]:
        pattern = "%" + _escape_like(keyword) + "%"
        rows = self._conn().execute(
            "SELECT a.activity_id, a.title, a.category, a.start_at, a.location, a.capacity, "
            "       COUNT(CASE WHEN r.status = 'APPROVED' THEN 1 END) AS approved_count "
            "FROM activities a "
            "LEFT JOIN registrations r ON r.activity_id = a.activity_id "
            "WHERE a.title LIKE ? ESCAPE '\\' "
            "GROUP BY a.activity_id, a.title, a.category, a.start_at, a.location, a.capacity "
            "ORDER BY a.start_at ASC",
            (pattern,),
        ).fetchall()
        summaries = []
        for row in rows:
            activity_id, title, category, start_at, location, capacity, approved = row
            remaining = max(0, capacity - approved)
            if now >= parse_dt(start_at):
                display = "STARTED"
            elif remaining <= 0:
                display = "FULL"
            else:
                display = "OPEN"
            summaries.append(
                ActivitySummary(activity_id, title, category, start_at, location,
                                capacity, approved, remaining, display)
            )
        return summaries

    def save(self, activity: Activity) -> None:
        ts = now_str()
        self._conn().execute(
            "INSERT INTO activities(activity_id, title, category, start_at, location, "
            "capacity, policy_type, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (activity.activity_id, activity.title, activity.category, activity.start_at,
             activity.location, activity.capacity, activity.policy_type.value, ts, ts),
        )

    def update(self, activity: Activity) -> None:
        self._conn().execute(
            "UPDATE activities SET title=?, category=?, start_at=?, location=?, capacity=?, "
            "policy_type=?, updated_at=? WHERE activity_id=?",
            (activity.title, activity.category, activity.start_at, activity.location,
             activity.capacity, activity.policy_type.value, now_str(), activity.activity_id),
        )

    def delete(self, activity_id: str) -> None:
        self._conn().execute("DELETE FROM activities WHERE activity_id=?", (activity_id,))

    @staticmethod
    def _to_activity(row) -> Activity:
        activity_id, title, category, start_at, location, capacity, policy_type = row
        try:
            policy = PolicyType(policy_type)
        except ValueError:
            # 扩展枚举（如抽签）按原值保留；策略工厂按值查找，服务不感知具体枚举
            policy = policy_type
        return Activity(activity_id, title, category, start_at, location, capacity, policy)


class SqliteRegistrationRepository:
    def __init__(self, provider):
        self.provider = provider

    def _conn(self):
        return self.provider.get()

    def find_by_id(self, registration_id: str) -> Optional[Registration]:
        row = self._conn().execute(
            "SELECT registration_id, activity_id, student_id, status, created_at, updated_at "
            "FROM registrations WHERE registration_id = ?",
            (registration_id,),
        ).fetchone()
        return self._to_registration(row) if row else None

    def find_active(self, student_id: str, activity_id: str) -> Optional[Registration]:
        row = self._conn().execute(
            "SELECT registration_id, activity_id, student_id, status, created_at, updated_at "
            "FROM registrations "
            "WHERE student_id=? AND activity_id=? AND status IN ('PENDING','APPROVED') "
            "LIMIT 1",
            (student_id, activity_id),
        ).fetchone()
        return self._to_registration(row) if row else None

    def find_by_student(self, student_id: str) -> List[RegistrationSummary]:
        rows = self._conn().execute(
            "SELECT r.registration_id, r.student_id, s.name, r.activity_id, a.title, "
            "       r.status, r.created_at "
            "FROM registrations r "
            "JOIN students s ON s.student_id = r.student_id "
            "JOIN activities a ON a.activity_id = r.activity_id "
            "WHERE r.student_id = ? "
            "ORDER BY r.created_at DESC",
            (student_id,),
        ).fetchall()
        return [self._to_summary(row) for row in rows]

    def find_by_activity_and_status(self, activity_id: str, status: RegistrationStatus) -> List[RegistrationSummary]:
        rows = self._conn().execute(
            "SELECT r.registration_id, r.student_id, s.name, r.activity_id, a.title, "
            "       r.status, r.created_at "
            "FROM registrations r "
            "JOIN students s ON s.student_id = r.student_id "
            "JOIN activities a ON a.activity_id = r.activity_id "
            "WHERE r.activity_id = ? AND r.status = ? "
            "ORDER BY r.created_at ASC",
            (activity_id, status.value),
        ).fetchall()
        return [self._to_summary(row) for row in rows]

    def count_by_activity_and_status(self, activity_id: str, status: RegistrationStatus) -> int:
        row = self._conn().execute(
            "SELECT COUNT(*) FROM registrations WHERE activity_id=? AND status=?",
            (activity_id, status.value),
        ).fetchone()
        return int(row[0])

    def statistics(self, activity_id: str) -> Optional[ActivityStatistics]:
        row = self._conn().execute(
            "SELECT a.activity_id, a.title, a.capacity, "
            "       COALESCE(SUM(CASE WHEN r.status='APPROVED' THEN 1 ELSE 0 END),0), "
            "       COALESCE(SUM(CASE WHEN r.status='PENDING' THEN 1 ELSE 0 END),0) "
            "FROM activities a "
            "LEFT JOIN registrations r ON r.activity_id = a.activity_id "
            "WHERE a.activity_id = ? "
            "GROUP BY a.activity_id, a.title, a.capacity",
            (activity_id,),
        ).fetchone()
        if row is None:
            return None
        return ActivityStatistics(row[0], row[1], row[2], int(row[3]), int(row[4]))

    def exists_by_activity(self, activity_id: str) -> bool:
        row = self._conn().execute(
            "SELECT 1 FROM registrations WHERE activity_id=? LIMIT 1", (activity_id,)
        ).fetchone()
        return row is not None

    def exists_active_by_activity(self, activity_id: str) -> bool:
        row = self._conn().execute(
            "SELECT 1 FROM registrations WHERE activity_id=? AND status IN ('PENDING','APPROVED') LIMIT 1",
            (activity_id,),
        ).fetchone()
        return row is not None

    def save(self, registration: Registration) -> None:
        try:
            self._conn().execute(
                "INSERT INTO registrations(registration_id, activity_id, student_id, status, "
                "created_at, updated_at) VALUES (?,?,?,?,?,?)",
                (registration.registration_id, registration.activity_id, registration.student_id,
                 registration.status.value, registration.created_at, registration.updated_at),
            )
        except sqlite3.IntegrityError as exc:
            if "ux_registration_active" in str(exc):
                raise DuplicateActiveError("同一学生同一活动已存在有效报名") from exc
            raise

    def update(self, registration: Registration) -> None:
        self._conn().execute(
            "UPDATE registrations SET status=?, updated_at=? WHERE registration_id=?",
            (registration.status.value, registration.updated_at, registration.registration_id),
        )

    @staticmethod
    def _to_registration(row) -> Registration:
        registration_id, activity_id, student_id, status, created_at, updated_at = row
        return Registration(registration_id, activity_id, student_id,
                            RegistrationStatus(status), created_at, updated_at)

    @staticmethod
    def _to_summary(row) -> RegistrationSummary:
        registration_id, student_id, student_name, activity_id, activity_title, status, created_at = row
        return RegistrationSummary(registration_id, student_id, student_name,
                                   activity_id, activity_title, RegistrationStatus(status), created_at)


class SqliteMessageRepository:
    def __init__(self, provider):
        self.provider = provider

    def _conn(self):
        return self.provider.get()

    def save(self, message: Message) -> None:
        try:
            self._conn().execute(
                "INSERT INTO messages(message_id, student_id, activity_id, content, created_at, "
                "is_read, event_key) VALUES (?,?,?,?,?,?,?)",
                (message.message_id, message.student_id, message.activity_id, message.content,
                 message.created_at, 1 if message.is_read else 0, message.event_key),
            )
        except sqlite3.IntegrityError as exc:
            if "event_key" in str(exc):
                raise DuplicateEventKeyError("消息去重键冲突，视为已通知") from exc
            raise

    def find_by_student(self, student_id: str) -> List[Message]:
        rows = self._conn().execute(
            "SELECT message_id, student_id, activity_id, content, created_at, is_read, event_key "
            "FROM messages WHERE student_id=? ORDER BY created_at DESC",
            (student_id,),
        ).fetchall()
        return [self._to_message(row) for row in rows]

    def find_by_id(self, message_id: str) -> Optional[Message]:
        row = self._conn().execute(
            "SELECT message_id, student_id, activity_id, content, created_at, is_read, event_key "
            "FROM messages WHERE message_id=?",
            (message_id,),
        ).fetchone()
        return self._to_message(row) if row else None

    def update(self, message: Message) -> None:
        self._conn().execute(
            "UPDATE messages SET is_read=? WHERE message_id=?",
            (1 if message.is_read else 0, message.message_id),
        )

    def exists_by_event_key(self, event_key: str) -> bool:
        row = self._conn().execute(
            "SELECT 1 FROM messages WHERE event_key=? LIMIT 1", (event_key,)
        ).fetchone()
        return row is not None

    @staticmethod
    def _to_message(row) -> Message:
        message_id, student_id, activity_id, content, created_at, is_read, event_key = row
        return Message(message_id, student_id, activity_id, content, created_at,
                       bool(is_read), event_key)


class SqliteStudentRepository:
    def __init__(self, provider):
        self.provider = provider

    def find_by_id(self, student_id: str) -> Optional[Student]:
        row = self.provider.get().execute(
            "SELECT student_id, name FROM students WHERE student_id=?", (student_id,)
        ).fetchone()
        return Student(row[0], row[1]) if row else None

    def all(self) -> List[Student]:
        rows = self.provider.get().execute("SELECT student_id, name FROM students ORDER BY student_id").fetchall()
        return [Student(r[0], r[1]) for r in rows]
