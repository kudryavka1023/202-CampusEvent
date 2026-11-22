"""值对象与结果对象：跨层传值，不承载行为以外的状态。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .enums import RegistrationEventType, RegistrationStatus
from .entities import Activity, Registration, now_str, parse_dt


@dataclass
class RegistrationContext:
    """策略需要的完整输入；策略只读，不查库。"""

    student_id: str
    activity: Activity
    now: datetime
    approved_count: int

    def get_activity(self) -> Activity:
        return self.activity

    def get_approved_count(self) -> int:
        return self.approved_count

    def get_now(self) -> datetime:
        return self.now


@dataclass
class RegistrationEvent:
    """领域事件：通知所需最小事实 + 幂等键。"""

    event_id: str
    registration_id: str
    activity_id: str
    student_id: str
    type: RegistrationEventType
    status: RegistrationStatus
    reason: Optional[str] = None
    occurred_at: str = field(default_factory=now_str)

    def event_key(self) -> str:
        return f"{self.registration_id}:{self.type.value}"


@dataclass
class RegistrationResult:
    success: bool
    registration: Optional[Registration] = None
    error_code: str = ""
    message: str = ""

    def is_success(self) -> bool:
        return self.success

    @classmethod
    def ok(cls, registration: Registration) -> "RegistrationResult":
        return cls(success=True, registration=registration)

    @classmethod
    def fail(cls, error_code: str, message: str = "") -> "RegistrationResult":
        return cls(success=False, error_code=error_code, message=message)


@dataclass
class ActivityResult:
    success: bool
    activity: Optional[Activity] = None
    error_code: str = ""
    message: str = ""

    def is_success(self) -> bool:
        return self.success

    @classmethod
    def ok(cls, activity: Activity) -> "ActivityResult":
        return cls(success=True, activity=activity)

    @classmethod
    def fail(cls, error_code: str, message: str = "") -> "ActivityResult":
        return cls(success=False, error_code=error_code, message=message)


@dataclass
class ActivitySummary:
    """活动列表读模型：实体字段 + 聚合计数 + 展示状态。"""

    activity_id: str
    title: str
    category: str
    start_at: str
    location: str
    capacity: int
    approved_count: int
    remaining_seats: int
    display_status: str

    def is_full(self) -> bool:
        return self.remaining_seats <= 0

    def is_open(self, now: datetime) -> bool:
        return now < parse_dt(self.start_at)


@dataclass
class ActivityStatistics:
    """统计页读模型：活动名称、容量、已通过/待审核/剩余，同一快照。"""

    activity_id: str
    activity_title: str
    capacity: int
    approved_count: int
    pending_count: int

    def get_remaining_seats(self) -> int:
        return max(0, self.capacity - self.approved_count)


@dataclass
class RegistrationSummary:
    """报名列表读模型：学生姓名/活动名称 + 状态 + 提交时间（一条 JOIN 查询）。"""

    registration_id: str
    student_id: str
    student_name: str
    activity_id: str
    activity_title: str
    status: RegistrationStatus
    created_at: str

    def is_pending(self) -> bool:
        return self.status is RegistrationStatus.PENDING
