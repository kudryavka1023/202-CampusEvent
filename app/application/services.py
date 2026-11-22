"""应用服务层：用例协调、公共规则、事务边界、事件发布。

- 预期业务失败用结果对象返回（不抛异常穿过层边界）；
- 查询“不存在”用 NotFoundError（路由层转 404）；
- 写事务用 TransactionManager.transaction(write=True)；事件在提交后发布；
- 公共规则集中在 RegistrationService + Activity；策略只决定初始状态。
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional

from ..domain.entities import Activity, Registration, parse_dt
from ..domain.enums import ApprovalDecision, RegistrationEventType, RegistrationStatus
from ..domain.errors import (
    ALREADY_HANDLED,
    ACTIVITY_CLOSED,
    ACTIVITY_HAS_REGISTRATIONS,
    CAPACITY_BELOW_APPROVED,
    DUPLICATE_ACTIVE,
    INVALID_STATE,
    NOT_FOUND,
    PERSISTENCE_ERROR,
    POLICY_IMMUTABLE,
    POLICY_NOT_CONFIGURED,
    SEATS_FULL,
    VALIDATION_ERROR,
    DuplicateActiveError,
    NotFoundError,
    PolicyNotConfiguredError,
)
from ..domain.events import new_id
from ..domain.policies import RegistrationPolicyFactory
from ..domain.value_objects import (
    ActivityResult,
    ActivityStatistics,
    ActivitySummary,
    RegistrationContext,
    RegistrationEvent,
    RegistrationResult,
    RegistrationSummary,
)

TITLE_MAX = 100
_FULL_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")


def normalize_start_at(value: str) -> str:
    """表单 'YYYY-MM-DDTHH:MM' → 'YYYY-MM-DDTHH:MM:SS'；已是完整格式则原样。"""
    value = (value or "").strip()
    if _FULL_TS.match(value):
        return value
    return datetime.fromisoformat(value).strftime("%Y-%m-%dT%H:%M:%S")


class ActivityService:
    def __init__(self, activity_repository, registration_repository, transaction_manager,
                 allowed_policy_values=None):
        self.activity_repository = activity_repository
        self.registration_repository = registration_repository
        self.transaction_manager = transaction_manager
        self.allowed_policy_values = set(allowed_policy_values or {"DIRECT", "APPROVAL"})

    # ---------- 查询 ----------
    def find_by_id(self, activity_id: str) -> Optional[Activity]:
        return self.activity_repository.find_by_id(activity_id)

    def search(self, keyword: str) -> List[ActivitySummary]:
        return self.activity_repository.search_summaries(keyword or "", datetime.now())

    # ---------- 命令 ----------
    def create(self, admin_id: str, activity: Activity) -> ActivityResult:
        error = self._validate_fields(activity, capacity_check=True, time_check=True)
        if error:
            return ActivityResult.fail(VALIDATION_ERROR, error)
        try:
            with self.transaction_manager.transaction(write=True):
                self.activity_repository.save(activity)
        except Exception:
            return ActivityResult.fail(PERSISTENCE_ERROR, "创建失败，请重试")
        return ActivityResult.ok(activity)

    def update(self, admin_id: str, activity_id: str, activity: Activity) -> ActivityResult:
        existing = self.activity_repository.find_by_id(activity_id)
        if existing is None:
            return ActivityResult.fail(NOT_FOUND, "活动不存在或已被删除")
        error = self._validate_fields(activity, capacity_check=True, time_check=True)
        if error:
            return ActivityResult.fail(VALIDATION_ERROR, error)
        approved = self.registration_repository.count_by_activity_and_status(
            activity_id, RegistrationStatus.APPROVED
        )
        if activity.capacity < approved:
            return ActivityResult.fail(CAPACITY_BELOW_APPROVED, "容量不能小于当前已通过人数")
        new_policy_value = getattr(activity.policy_type, "value", activity.policy_type)
        if new_policy_value != getattr(existing.policy_type, "value", existing.policy_type):
            if not existing.can_change_policy(
                self.registration_repository.exists_active_by_activity(activity_id)
            ):
                return ActivityResult.fail(POLICY_IMMUTABLE, "已有有效报名，不能修改报名方式")
        activity.activity_id = activity_id
        try:
            with self.transaction_manager.transaction(write=True):
                self.activity_repository.update(activity)
        except Exception:
            return ActivityResult.fail(PERSISTENCE_ERROR, "保存失败，请重试")
        return ActivityResult.ok(activity)

    def delete(self, admin_id: str, activity_id: str) -> ActivityResult:
        existing = self.activity_repository.find_by_id(activity_id)
        if existing is None:
            return ActivityResult.fail(NOT_FOUND, "活动不存在或已被删除")
        if self.registration_repository.exists_by_activity(activity_id):
            return ActivityResult.fail(
                ACTIVITY_HAS_REGISTRATIONS, "该活动已有报名记录，不能删除"
            )
        try:
            with self.transaction_manager.transaction(write=True):
                self.activity_repository.delete(activity_id)
        except Exception:
            return ActivityResult.fail(PERSISTENCE_ERROR, "删除失败，请重试")
        return ActivityResult.ok(existing)

    # ---------- 校验 ----------
    def _validate_fields(self, activity: Activity, capacity_check: bool, time_check: bool) -> str:
        if not activity.title or not activity.title.strip():
            return "活动名称必填"
        if len(activity.title) > TITLE_MAX:
            return f"活动名称不能超过 {TITLE_MAX} 字"
        if not activity.category or not activity.category.strip():
            return "活动类型必填"
        if not activity.location or not activity.location.strip():
            return "活动地点必填"
        if getattr(activity.policy_type, "value", activity.policy_type) not in self.allowed_policy_values:
            return "报名方式配置错误"
        if capacity_check:
            if not isinstance(activity.capacity, int) or activity.capacity <= 0:
                return "人数上限必须为正整数"
        if time_check:
            try:
                start = parse_dt(normalize_start_at(activity.start_at))
            except ValueError:
                return "开始时间格式错误"
            if start <= datetime.now():
                return "开始时间必须晚于当前时间"
        return ""


class RegistrationService:
    def __init__(self, activity_repository, registration_repository, policy_factory,
                 event_publisher, transaction_manager):
        self.activity_repository = activity_repository
        self.registration_repository = registration_repository
        self.policy_factory: RegistrationPolicyFactory = policy_factory
        self.event_publisher = event_publisher
        self.transaction_manager = transaction_manager

    # ---------- 查询 ----------
    def find_active(self, student_id: str, activity_id: str) -> Optional[Registration]:
        return self.registration_repository.find_active(student_id, activity_id)

    def list_by_student(self, student_id: str) -> List[RegistrationSummary]:
        return self.registration_repository.find_by_student(student_id)

    def list_pending(self, activity_id: str) -> List[RegistrationSummary]:
        if self.activity_repository.find_by_id(activity_id) is None:
            raise NotFoundError("活动不存在或已被删除")
        return self.registration_repository.find_by_activity_and_status(
            activity_id, RegistrationStatus.PENDING
        )

    # ---------- 命令 ----------
    def submit(self, student_id: str, activity_id: str) -> RegistrationResult:
        try:
            with self.transaction_manager.transaction(write=True):
                activity = self.activity_repository.find_by_id(activity_id)
                if activity is None:
                    return RegistrationResult.fail(NOT_FOUND, "活动不存在或已被删除")
                now = datetime.now()
                if not activity.is_open(now):
                    return RegistrationResult.fail(ACTIVITY_CLOSED, "报名已截止")
                if self.registration_repository.find_active(student_id, activity_id) is not None:
                    return RegistrationResult.fail(DUPLICATE_ACTIVE, "你已报名该活动，请勿重复提交")
                approved = self.registration_repository.count_by_activity_and_status(
                    activity_id, RegistrationStatus.APPROVED
                )
                if not activity.has_capacity(approved):
                    return RegistrationResult.fail(SEATS_FULL, "名额已满")
                try:
                    policy = self.policy_factory.create(activity.policy_type)
                except PolicyNotConfiguredError:
                    return RegistrationResult.fail(POLICY_NOT_CONFIGURED, "活动报名方式配置错误")
                status = policy.decide_initial_status(
                    RegistrationContext(student_id, activity, now, approved)
                )
                registration = Registration(
                    registration_id=new_id("reg"),
                    activity_id=activity_id,
                    student_id=student_id,
                    status=status,
                )
                try:
                    self.registration_repository.save(registration)
                except DuplicateActiveError:
                    return RegistrationResult.fail(DUPLICATE_ACTIVE, "你已报名该活动，请勿重复提交")
        except Exception:
            return RegistrationResult.fail(PERSISTENCE_ERROR, "报名失败，请重试")

        # 事务提交后发布事件；通知失败只写日志，不回滚报名
        self.event_publisher.publish(
            RegistrationEvent(
                event_id=new_id("evt"),
                registration_id=registration.registration_id,
                activity_id=registration.activity_id,
                student_id=registration.student_id,
                type=RegistrationEventType.SUBMITTED,
                status=registration.status,
            )
        )
        return RegistrationResult.ok(registration)

    def cancel(self, student_id: str, registration_id: str) -> RegistrationResult:
        try:
            with self.transaction_manager.transaction(write=True):
                registration = self.registration_repository.find_by_id(registration_id)
                if registration is None or not registration.is_owned_by(student_id):
                    # 不泄露报名是否存在
                    return RegistrationResult.fail(NOT_FOUND, "报名记录不存在")
                if not registration.is_active():
                    return RegistrationResult.fail(INVALID_STATE, "该报名已处理，不能取消")
                registration.cancel()
                self.registration_repository.update(registration)
        except Exception:
            return RegistrationResult.fail(PERSISTENCE_ERROR, "取消失败，请重试")

        self.event_publisher.publish(
            RegistrationEvent(
                event_id=new_id("evt"),
                registration_id=registration.registration_id,
                activity_id=registration.activity_id,
                student_id=registration.student_id,
                type=RegistrationEventType.CANCELLED,
                status=registration.status,
            )
        )
        return RegistrationResult.ok(registration)

    def review(self, admin_id: str, registration_id: str,
               decision: ApprovalDecision, reason: Optional[str] = None) -> RegistrationResult:
        try:
            with self.transaction_manager.transaction(write=True):
                registration = self.registration_repository.find_by_id(registration_id)
                if registration is None:
                    return RegistrationResult.fail(NOT_FOUND, "报名记录不存在")
                if not registration.is_pending():
                    return RegistrationResult.fail(ALREADY_HANDLED, "该申请已被处理")

                if decision is ApprovalDecision.APPROVE:
                    activity = self.activity_repository.find_by_id(registration.activity_id)
                    if activity is None:
                        return RegistrationResult.fail(NOT_FOUND, "活动不存在或已被删除")
                    approved = self.registration_repository.count_by_activity_and_status(
                        activity.activity_id, RegistrationStatus.APPROVED
                    )
                    if not activity.has_capacity(approved):
                        return RegistrationResult.fail(SEATS_FULL, "名额已满，无法批准")
                    registration.approve()
                    event_type = RegistrationEventType.APPROVED
                else:
                    registration.reject()
                    event_type = RegistrationEventType.REJECTED

                self.registration_repository.update(registration)
        except Exception:
            return RegistrationResult.fail(PERSISTENCE_ERROR, "审批失败，请重试")

        self.event_publisher.publish(
            RegistrationEvent(
                event_id=new_id("evt"),
                registration_id=registration.registration_id,
                activity_id=registration.activity_id,
                student_id=registration.student_id,
                type=event_type,
                status=registration.status,
                reason=reason if event_type is RegistrationEventType.REJECTED else None,
            )
        )
        return RegistrationResult.ok(registration)


class StatisticsService:
    def __init__(self, activity_repository, registration_repository):
        self.activity_repository = activity_repository
        self.registration_repository = registration_repository

    def for_activity(self, activity_id: str) -> ActivityStatistics:
        statistics = self.registration_repository.statistics(activity_id)
        if statistics is None:
            raise NotFoundError("活动不存在或已被删除")
        return statistics


class NotificationQueryService:
    def __init__(self, message_repository):
        self.message_repository = message_repository

    def list_by_student(self, student_id: str):
        return self.message_repository.find_by_student(student_id)

    def mark_read(self, student_id: str, message_id: str) -> bool:
        message = self.message_repository.find_by_id(message_id)
        if message is None or message.student_id != student_id:
            raise NotFoundError("消息不存在")
        message.mark_read()
        self.message_repository.update(message)
        return True
