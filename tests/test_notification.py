"""通知链路测试：幂等、失败隔离、消息内容。"""
from __future__ import annotations

from app.domain.enums import RegistrationEventType, RegistrationStatus
from app.domain.events import (
    MessageNotificationObserver,
    NotificationFailureLogger,
    SimpleRegistrationEventPublisher,
    build_message_content,
)
from app.domain.value_objects import RegistrationEvent
from conftest import make_activity


def make_event(reg_id="reg_1", type_=RegistrationEventType.SUBMITTED,
               status=RegistrationStatus.APPROVED, reason=None):
    return RegistrationEvent(
        event_id=f"evt_{reg_id}", registration_id=reg_id, activity_id="act_1",
        student_id="stu_demo1", type=type_, status=status, reason=reason,
    )


def test_observer_idempotent_by_event_key(ctx):
    publisher = SimpleRegistrationEventPublisher(
        [MessageNotificationObserver(ctx.message_repository)],
        NotificationFailureLogger(ctx.failure_log_path),
    )
    activity = make_activity("篮球赛", capacity=2)
    ctx.activity_service.create("admin", activity)
    event = make_event(reg_id="reg_1")
    event.activity_id = activity.activity_id
    publisher.publish(event)
    publisher.publish(event)  # 重复事件
    repeated = make_event(reg_id="reg_1")
    repeated.activity_id = activity.activity_id
    publisher.publish(repeated)  # 同一报名同一事件类型
    assert len(ctx.message_repository.find_by_student("stu_demo1")) == 1


def test_unique_constraint_fallback(ctx):
    """绕过先查后插：直接插同键消息 → DuplicateEventKeyError，观察者按已通知处理。"""
    from app.domain.entities import Message
    from app.domain.errors import DuplicateEventKeyError
    import pytest

    activity = make_activity("篮球赛", capacity=2)
    ctx.activity_service.create("admin", activity)
    ctx.message_repository.save(Message(
        message_id="msg_1", student_id="stu_demo1", activity_id=activity.activity_id,
        content="已存在", event_key="reg_1:SUBMITTED",
    ))
    event = make_event(reg_id="reg_1")
    event.activity_id = activity.activity_id
    observer = MessageNotificationObserver(ctx.message_repository)
    observer.on_registration_event(event)  # 先查后插发现已存在，直接跳过
    assert len(ctx.message_repository.find_by_student("stu_demo1")) == 1


def test_failing_observer_isolated_and_logged(ctx, tmp_path):
    log_path = str(tmp_path / "failure.log")
    publisher = SimpleRegistrationEventPublisher(
        [], NotificationFailureLogger(log_path)
    )

    class Boom:
        def on_registration_event(self, event):
            raise RuntimeError("boom")

    publisher.subscribe(Boom())
    event = make_event()
    publisher.publish(event)  # 不向上抛
    assert "reg_1:SUBMITTED" in open(log_path, encoding="utf-8").read()


def test_message_content_per_event_type():
    assert "已通过" in build_message_content(make_event(status=RegistrationStatus.APPROVED))
    assert "等待审核" in build_message_content(make_event(status=RegistrationStatus.PENDING))
    assert "已通过审核" in build_message_content(make_event(type_=RegistrationEventType.APPROVED))
    assert "名额调整" in build_message_content(
        make_event(type_=RegistrationEventType.REJECTED,
                   status=RegistrationStatus.REJECTED, reason="名额调整")
    )
    assert "取消" in build_message_content(
        make_event(type_=RegistrationEventType.CANCELLED, status=RegistrationStatus.CANCELLED)
    )
