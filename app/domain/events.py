"""领域事件与通知（Observer）。

- 发布者只依赖 RegistrationObserver 接口；
- 运行时实现为 SimpleRegistrationEventPublisher：对每个观察者 try/except，
  失败交给 NotificationFailureLogger，不回滚业务；
- MessageNotificationObserver 按 eventKey 幂等（先查后插，唯一约束兜底）。
"""
from __future__ import annotations

import logging
import os
import uuid
from abc import ABC, abstractmethod
from typing import List

from .errors import DuplicateEventKeyError
from .value_objects import RegistrationEvent


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class RegistrationObserver(ABC):
    @abstractmethod
    def on_registration_event(self, event: RegistrationEvent) -> None: ...


class RegistrationEventPublisher(ABC):
    @abstractmethod
    def subscribe(self, observer: RegistrationObserver) -> None: ...

    @abstractmethod
    def publish(self, event: RegistrationEvent) -> None: ...


class NotificationFailureLogger:
    """把观察者异常写入文件；自身失败只写 stderr。"""

    def __init__(self, log_path: str):
        self.log_path = log_path

    def log(self, event: RegistrationEvent, error: Exception) -> None:
        line = (
            f"{event.occurred_at} | event_key={event.event_key()} | "
            f"registration_id={event.registration_id} | observer={type(error).__name__} | "
            f"error={error!r}"
        )
        try:
            os.makedirs(os.path.dirname(self.log_path) or ".", exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError as exc:  # 自身失败只写 stderr，不向上抛
            print(f"[notification-failure-logger] write failed: {exc}", file=os.sys.stderr)


class SimpleRegistrationEventPublisher(RegistrationEventPublisher):
    def __init__(self, observers: List[RegistrationObserver], failure_logger: NotificationFailureLogger):
        self.observers: List[RegistrationObserver] = list(observers)
        self.failure_logger = failure_logger

    def subscribe(self, observer: RegistrationObserver) -> None:
        self.observers.append(observer)

    def publish(self, event: RegistrationEvent) -> None:
        for observer in list(self.observers):
            try:
                observer.on_registration_event(event)
            except Exception as exc:  # 每个观察者独立隔离
                self.failure_logger.log(event, exc)


class MessageNotificationObserver(RegistrationObserver):
    """把领域事件落成站内消息；只依赖 MessageRepository 接口。"""

    def __init__(self, message_repository):
        self.message_repository = message_repository

    def on_registration_event(self, event: RegistrationEvent) -> None:
        if self.message_repository.exists_by_event_key(event.event_key()):
            return  # 已通知（幂等）
        content = build_message_content(event)
        message = self._new_message(event, content)
        try:
            self.message_repository.save(message)
        except DuplicateEventKeyError:
            pass  # 唯一约束兜底：并发下按“已通知”处理
        # 其它异常不在此吞掉，交给发布者写失败日志

    def _new_message(self, event, content):
        from .entities import Message

        return Message(
            message_id=new_id("msg"),
            student_id=event.student_id,
            activity_id=event.activity_id,
            content=content,
            event_key=event.event_key(),
        )


def build_message_content(event: RegistrationEvent) -> str:
    """消息正文不重复活动标题；通知页用 activity_id 生成活动链接。"""
    if event.type.value == "SUBMITTED":
        if event.status.value == "APPROVED":
            return "报名已提交，当前状态：已通过。"
        return "报名已提交，等待审核。"
    if event.type.value == "APPROVED":
        return "你报名的活动已通过审核。"
    if event.type.value == "REJECTED":
        reason = (event.reason or "").strip()
        return f"你报名的活动未通过。理由：{reason}" if reason else "你报名的活动未通过。"
    if event.type.value == "CANCELLED":
        return "你已取消报名。"
    return "报名状态已更新。"
