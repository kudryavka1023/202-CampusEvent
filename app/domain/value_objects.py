"""值对象与结果对象：跨层传值，不承载行为以外的状态。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Tuple

from .enums import EmailStatus, RegistrationEventType, RegistrationStatus
from .entities import Activity, Registration, Student, now_str, parse_dt


@dataclass
class RegistrationContext:
    """策略与资格规则需要的完整输入；规则只读，不查库。"""

    student_id: str
    activity: Activity
    now: datetime
    approved_count: int
    student: Optional[Student] = None

    def get_activity(self) -> Activity:
        return self.activity

    def get_approved_count(self) -> int:
        return self.approved_count

    def get_now(self) -> datetime:
        return self.now

    def get_student(self) -> Optional[Student]:
        return self.student


@dataclass
class EligibilityViolation:
    """资格规则返回的失败原因；error_code 与 SRS 错误码一致。"""

    error_code: str
    message: str


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
    allowed_grades: Optional[Tuple[int, ...]] = None

    def is_full(self) -> bool:
        return self.remaining_seats <= 0

    def is_open(self, now: datetime) -> bool:
        return now < parse_dt(self.start_at)

    def grade_requirement_text(self) -> str:
        from .entities import GRADE_TEXT

        if self.allowed_grades is None:
            return "不限"
        return "、".join(GRADE_TEXT.get(g, str(g)) for g in self.allowed_grades)


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


@dataclass
class EmailMessage:
    """邮件发送请求：发送器只负责投递，不查库、不拼业务规则。"""

    event_key: str
    registration_id: str
    student_id: str
    recipient: str
    subject: str
    content: str


@dataclass
class EmailLog:
    """模拟邮件发送记录：收件人、主题、内容、状态、时间。"""

    email_id: str
    event_key: str
    registration_id: str
    student_id: str
    recipient: str
    subject: str
    content: str
    status: EmailStatus
    error: str = ""
    created_at: str = field(default_factory=now_str)
