"""界面层控制器：只做参数绑定、角色/会话数据透传、调用服务、组装页面模型。

不写业务规则，不直接访问 Repository。角色校验在路由层完成。
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from ..domain.entities import Activity
from ..domain.enums import ApprovalDecision
from ..domain.errors import NotFoundError
from ..domain.value_objects import (
    ActivityResult,
    ActivityStatistics,
    ActivitySummary,
    EmailLog,
    RegistrationResult,
    RegistrationSummary,
)


class ActivityController:
    def __init__(self, activity_service, registration_service, statistics_service):
        self.activity_service = activity_service
        self.registration_service = registration_service
        self.statistics_service = statistics_service

    def list(self, keyword: str) -> List[ActivitySummary]:
        return self.activity_service.search(keyword)

    def get(self, activity_id: str) -> Optional[Activity]:
        return self.activity_service.find_by_id(activity_id)

    def detail(self, activity_id: str, student_id: str) -> dict:
        """只读组合：活动 + 当前学生报名 + 统计；不存在则 404。"""
        activity: Optional[Activity] = self.activity_service.find_by_id(activity_id)
        if activity is None:
            raise NotFoundError("活动不存在或已被删除")
        my_registration = self.registration_service.find_active(student_id, activity_id)
        statistics: ActivityStatistics = self.statistics_service.for_activity(activity_id)
        now = datetime.now()
        has_started = not activity.is_open(now)
        grade_message = self.registration_service.check_eligibility(student_id, activity_id) or ""
        can_register = (
            activity.is_open(now)
            and statistics.get_remaining_seats() > 0
            and my_registration is None
            and not grade_message
        )
        return {
            "activity": activity,
            "my_registration": my_registration,
            "statistics": statistics,
            "can_register": can_register,
            "has_started": has_started,
            "grade_message": grade_message,
        }

    def create(self, admin_id: str, activity: Activity) -> ActivityResult:
        return self.activity_service.create(admin_id, activity)

    def update(self, admin_id: str, activity_id: str, activity: Activity) -> ActivityResult:
        return self.activity_service.update(admin_id, activity_id, activity)

    def delete(self, admin_id: str, activity_id: str) -> ActivityResult:
        return self.activity_service.delete(admin_id, activity_id)


class RegistrationController:
    def __init__(self, registration_service):
        self.registration_service = registration_service

    def submit(self, student_id: str, activity_id: str) -> RegistrationResult:
        return self.registration_service.submit(student_id, activity_id)

    def cancel(self, student_id: str, registration_id: str) -> RegistrationResult:
        return self.registration_service.cancel(student_id, registration_id)

    def my_registrations(self, student_id: str) -> List[RegistrationSummary]:
        return self.registration_service.list_by_student(student_id)


class ApprovalController:
    def __init__(self, registration_service):
        self.registration_service = registration_service

    def pending_list(self, admin_id: str, activity_id: str) -> List[RegistrationSummary]:
        return self.registration_service.list_pending(activity_id)

    def approve(self, admin_id: str, registration_id: str) -> RegistrationResult:
        return self.registration_service.review(admin_id, registration_id, ApprovalDecision.APPROVE)

    def reject(self, admin_id: str, registration_id: str, reason: str) -> RegistrationResult:
        return self.registration_service.review(admin_id, registration_id, ApprovalDecision.REJECT, reason)


class NotificationController:
    def __init__(self, notification_service):
        self.notification_service = notification_service

    def list(self, student_id: str):
        return self.notification_service.list_by_student(student_id)

    def mark_read(self, student_id: str, message_id: str) -> bool:
        return self.notification_service.mark_read(student_id, message_id)


class StatisticsController:
    def __init__(self, statistics_service):
        self.statistics_service = statistics_service

    def view(self, admin_id: str, activity_id: str) -> ActivityStatistics:
        return self.statistics_service.for_activity(activity_id)


class EmailLogController:
    """管理员查看模拟邮件记录；只读。"""

    def __init__(self, email_log_service):
        self.email_log_service = email_log_service

    def list(self, admin_id: str) -> List[EmailLog]:
        return self.email_log_service.list_all()
