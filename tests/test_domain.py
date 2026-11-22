"""领域单元测试：状态机、容量/时间规则、策略契约、事件键、读模型。"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.domain.entities import Activity, Registration, parse_dt
from app.domain.enums import PolicyType, RegistrationEventType, RegistrationStatus
from app.domain.errors import InvalidStateError, PolicyNotConfiguredError
from app.domain.policies import (
    ApprovalRegistrationPolicy,
    DirectRegistrationPolicy,
    RegistrationPolicyFactory,
)
from app.domain.value_objects import (
    ActivityStatistics,
    ActivitySummary,
    RegistrationContext,
    RegistrationEvent,
)
from conftest import future_start, make_activity, past_start


def registration(status=RegistrationStatus.PENDING):
    return Registration("reg_x", "act_x", "stu_demo1", status)


class TestRegistrationStateMachine:
    def test_approve_only_from_pending(self):
        reg = registration(RegistrationStatus.PENDING)
        reg.approve()
        assert reg.status is RegistrationStatus.APPROVED
        with pytest.raises(InvalidStateError):
            reg.approve()

    def test_reject_only_from_pending(self):
        reg = registration(RegistrationStatus.APPROVED)
        with pytest.raises(InvalidStateError):
            reg.reject()

    def test_cancel_from_pending_and_approved(self):
        for status in (RegistrationStatus.PENDING, RegistrationStatus.APPROVED):
            reg = registration(status)
            reg.cancel()
            assert reg.status is RegistrationStatus.CANCELLED

    def test_cancel_rejected_or_cancelled_raises(self):
        for status in (RegistrationStatus.REJECTED, RegistrationStatus.CANCELLED):
            with pytest.raises(InvalidStateError):
                registration(status).cancel()

    def test_flags(self):
        reg = registration(RegistrationStatus.PENDING)
        assert reg.is_active() and reg.is_pending() and reg.is_owned_by("stu_demo1")
        reg.approve()
        assert reg.is_active() and not reg.is_pending()


class TestActivityRules:
    def test_is_open(self):
        activity = make_activity(start_at=future_start())
        assert activity.is_open(datetime.now())
        started = make_activity(start_at=past_start())
        assert not started.is_open(datetime.now())

    def test_capacity_boundaries(self):
        activity = make_activity(capacity=2)
        assert activity.has_capacity(0) and activity.has_capacity(1)
        assert not activity.has_capacity(2) and not activity.has_capacity(3)
        assert activity.remaining_seats(1) == 1
        assert activity.remaining_seats(5) == 0

    def test_can_change_policy(self):
        activity = make_activity()
        assert activity.can_change_policy(False)
        assert not activity.can_change_policy(True)


class TestPolicyContract:
    def test_direct_returns_approved(self):
        ctx = RegistrationContext("stu", make_activity(), datetime.now(), 0)
        assert DirectRegistrationPolicy().decide_initial_status(ctx) is RegistrationStatus.APPROVED

    def test_approval_returns_pending(self):
        ctx = RegistrationContext("stu", make_activity(), datetime.now(), 0)
        assert ApprovalRegistrationPolicy().decide_initial_status(ctx) is RegistrationStatus.PENDING

    def test_policies_do_not_modify_context(self):
        ctx = RegistrationContext("stu", make_activity(), datetime.now(), 3)
        ApprovalRegistrationPolicy().decide_initial_status(ctx)
        DirectRegistrationPolicy().decide_initial_status(ctx)
        assert ctx.approved_count == 3 and ctx.student_id == "stu"

    def test_factory_missing_policy_raises(self):
        factory = RegistrationPolicyFactory([DirectRegistrationPolicy()])
        with pytest.raises(PolicyNotConfiguredError):
            factory.create(PolicyType.APPROVAL)

    def test_factory_complete_check(self):
        factory = RegistrationPolicyFactory([DirectRegistrationPolicy(), ApprovalRegistrationPolicy()])
        factory.check_complete((PolicyType.DIRECT, PolicyType.APPROVAL))


class TestValueObjects:
    def test_event_key(self):
        event = RegistrationEvent(
            "evt_1", "reg_1", "act_1", "stu_demo1",
            RegistrationEventType.SUBMITTED, RegistrationStatus.PENDING,
        )
        assert event.event_key() == "reg_1:SUBMITTED"

    def test_summary_flags(self):
        summary = ActivitySummary(
            "act_1", "篮球赛", "比赛", future_start(), "体育馆",
            2, 2, 0, "FULL",
        )
        assert summary.is_full()
        assert summary.is_open(datetime.now())

    def test_statistics_remaining(self):
        stats = ActivityStatistics("act_1", "篮球赛", 10, 7, 2)
        assert stats.get_remaining_seats() == 3
        assert ActivityStatistics("a", "t", 1, 5, 0).get_remaining_seats() == 0
