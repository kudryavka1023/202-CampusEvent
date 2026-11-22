"""领域实体：只做自身状态判断与迁移，不查库、不发通知。

时间统一为本地时间，ISO-8601 字符串（精确到秒），比较时解析为 datetime
（假设 A-10：不处理时区）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .enums import PolicyType, RegistrationStatus
from .errors import InvalidStateError

TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"


def parse_dt(value: str) -> datetime:
    return datetime.strptime(value[:19], TIME_FORMAT)


def now_str() -> str:
    return datetime.now().strftime(TIME_FORMAT)


@dataclass
class Student:
    student_id: str
    name: str

    def get_id(self) -> str:
        return self.student_id

    def get_name(self) -> str:
        return self.name


@dataclass
class Activity:
    activity_id: str
    title: str
    category: str
    start_at: str
    location: str
    capacity: int
    policy_type: PolicyType

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
