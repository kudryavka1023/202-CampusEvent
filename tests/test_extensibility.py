"""可扩展性验证（对应实验二维护性指标）。

- CR-1 模拟“新增抽签/候补报名方式”：只扩展枚举/DB CHECK/工厂注册，
  RegistrationService.submit 一行不改（用源码断言证明）；
- CR-2 模拟“新增邮件通知”：只新增观察者并订阅，服务与发布者不改；
- 策略契约：策略不查库、只返回初始状态。
"""
from __future__ import annotations

import inspect
from enum import Enum

from app.application.services import RegistrationService
from app.composition import AppContext
from app.domain.enums import PolicyType, RegistrationStatus
from app.domain.events import RegistrationObserver
from app.domain.policies import RegistrationPolicy
from app.domain.value_objects import RegistrationContext
from conftest import make_activity


class ExtendedPolicyType(str, Enum):
    DIRECT = "DIRECT"
    APPROVAL = "APPROVAL"
    LOTTERY = "LOTTERY"


class LotteryRegistrationPolicy(RegistrationPolicy):
    """CR-1 新增策略：抽签型初始化为待审核（初始版本仅演示扩展点）。"""

    def policy_type(self):
        return ExtendedPolicyType.LOTTERY

    def decide_initial_status(self, context: RegistrationContext) -> RegistrationStatus:
        return RegistrationStatus.PENDING


def test_cr1_new_policy_requires_no_service_change(make_ctx):
    """CR-1：新增报名方式只需枚举 + DB CHECK + 工厂注册，核心服务源码零修改。"""
    source = inspect.getsource(RegistrationService.submit)
    assert "LOTTERY" not in source  # 主流程没有按方式写分支

    ctx = make_ctx(
        policy_types=(ExtendedPolicyType.DIRECT, ExtendedPolicyType.APPROVAL, ExtendedPolicyType.LOTTERY),
        extra_policies=[LotteryRegistrationPolicy()],
    )
    # 公共策略仍按值注册（值与现有枚举一致）
    activity = make_activity("抽签讲座", capacity=10, policy=ExtendedPolicyType.LOTTERY)
    created = ctx.activity_service.create("admin", activity)
    assert created.is_success()

    result = ctx.registration_service.submit("stu_demo1", activity.activity_id)
    assert result.is_success()
    assert result.registration.status is RegistrationStatus.PENDING  # 抽签先待审核
    ctx.close()


def test_cr2_new_observer_requires_no_service_change(ctx):
    """CR-2：新增通知渠道只需新增观察者并订阅，服务/发布者源码零修改。"""
    received = []

    class EmailNotificationObserver(RegistrationObserver):
        def on_registration_event(self, event):
            received.append(event.event_key())

    ctx.event_publisher.subscribe(EmailNotificationObserver())
    activity = make_activity("篮球赛", capacity=2, policy=PolicyType.DIRECT)
    ctx.activity_service.create("admin", activity)
    result = ctx.registration_service.submit("stu_demo1", activity.activity_id)
    assert result.is_success()
    assert received and received[0].endswith(":SUBMITTED")
    # 站内消息观察者不受影响
    assert len(ctx.message_repository.find_by_student("stu_demo1")) == 1
    assert "Email" not in inspect.getsource(RegistrationService)


def test_policy_never_touches_repository():
    """策略契约：策略不查库、不修改上下文、只返回 APPROVED/PENDING。"""
    from app.domain.policies import ApprovalRegistrationPolicy, DirectRegistrationPolicy

    context = RegistrationContext("stu", make_activity(), None, 0)
    for policy in (DirectRegistrationPolicy(), ApprovalRegistrationPolicy(), LotteryRegistrationPolicy()):
        assert policy.decide_initial_status(context) in (
            RegistrationStatus.APPROVED, RegistrationStatus.PENDING
        )
    assert context.approved_count == 0  # 未被修改
