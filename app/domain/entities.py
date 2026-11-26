"""领域实体：只做自身状态判断与迁移，不查库、不发通知。

时间统一为本地时间，ISO-8601 字符串（精确到秒），比较时解析为 datetime
（假设 A-10：不处理时区）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Tuple

from .enums import PolicyType, RegistrationStatus
from .errors import InvalidStateError

TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"

GRADE_TEXT = {1: "大一", 2: "大二", 3: "大三", 4: "大四"}


def parse_dt(value: str) -> datetime:
    return datetime.strptime(value[:19], TIME_FORMAT)


def now_str() -> str:
    return datetime.now().strftime(TIME_FORMAT)


@dataclass
class Student:
    student_id: str
    name: str
    grade: int = 1
    email: str = ""

    def __post_init__(self) -> None:
        if self.grade not in GRADE_TEXT:
            raise ValueError(f"年级必须为 1—4，当前 {self.grade}")

    def get_id(self) -> str:
        return self.student_id

    def get_name(self) -> str:
        return self.name

    def get_grade(self) -> int:
        return self.grade

    def get_email(self) -> str:
        """演示环境没有真实邮箱字段时，按学号推导收件人。"""
        return self.email or f"{self.student_id}@campus.edu"


@dataclass
class Activity:
    activity_id: str
    title: str
    category: str
    start_at: str
    location: str
    capacity: int
    policy_type: PolicyType
    allowed_grades: Optional[Tuple[int, ...]] = None

    def __post_init__(self) -> None:
        if self.allowed_grades is not None:
            # 只做归一化（去重、排序）；范围校验在 ActivityService 中返回业务错误，
            # 避免实体构造抛异常导致路由 500。
            self.allowed_grades = tuple(sorted({int(g) for g in self.allowed_grades}))

    def is_open(self, now: datetime) -> bool:
        """活动存在（由调用方保证）且未开始。"""
        return now < parse_dt(self.start_at)

    def has_capacity(self, approved_count: int) -> bool:
        return approved_count < self.capacity

    def remaining_seats(self, approved_count: int) -> int:
        return max(0, self.capacity - approved_count)

    def can_change_policy(self, has_active: bool) -> bool:
        """有有效报名（PENDING/APPROVED）时不允许改报名方式。"""
        return not has_active

    def is_grade_allowed(self, grade: int) -> bool:
        """未配置年级限定时对所有年级开放。"""
        if self.allowed_grades is None:
            return True
        return grade in self.allowed_grades

    def grade_requirement_text(self) -> str:
        if self.allowed_grades is None:
            return "不限"
        return "、".join(GRADE_TEXT.get(g, str(g)) for g in self.allowed_grades)


@dataclass
class Registration:
    registration_id: str
    activity_id: str
    student_id: str
    status: RegistrationStatus
    created_at: str = field(default_factory=now_str)
    updated_at: str = field(default_factory=now_str)

    def is_active(self) -> bool:
        return self.status in (RegistrationStatus.PENDING, RegistrationStatus.APPROVED)

    def is_pending(self) -> bool:
        return self.status is RegistrationStatus.PENDING

    def is_owned_by(self, student_id: str) -> bool:
        return self.student_id == student_id

    def _touch(self) -> None:
        self.updated_at = now_str()

    def approve(self) -> None:
        if not self.is_pending():
            raise InvalidStateError(f"只有 PENDING 可批准，当前 {self.status.value}")
        self.status = RegistrationStatus.APPROVED
        self._touch()

    def reject(self) -> None:
        if not self.is_pending():
            raise InvalidStateError(f"只有 PENDING 可拒绝，当前 {self.status.value}")
        self.status = RegistrationStatus.REJECTED
        self._touch()

    def cancel(self) -> None:
        if not self.is_active():
            raise InvalidStateError(f"只有 PENDING/APPROVED 可取消，当前 {self.status.value}")
        self.status = RegistrationStatus.CANCELLED
        self._touch()


@dataclass
class Message:
    message_id: str
    student_id: str
    activity_id: str
    content: str
    created_at: str = field(default_factory=now_str)
    is_read: bool = False
    event_key: str = ""

    def mark_read(self) -> None:
        self.is_read = True
