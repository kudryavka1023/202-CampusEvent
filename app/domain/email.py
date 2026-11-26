"""邮件发送与邮件记录端口（由基础设施层实现）。

领域只依赖抽象：EmailNotificationObserver 依赖 EmailSender / EmailLogRepository；
MockEmailSender 与 SqliteEmailLogRepository 在基础设施层实现，组合根装配。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from .value_objects import EmailLog, EmailMessage


class EmailSender(ABC):
    @abstractmethod
    def send(self, message: EmailMessage) -> None:
        """发送一封邮件；失败抛 EmailSendError。"""


class EmailLogRepository(ABC):
    @abstractmethod
    def save(self, log: EmailLog) -> None: ...

    @abstractmethod
    def exists_by_event_key(self, event_key: str) -> bool: ...

    @abstractmethod
    def find_all(self, limit: int = 200) -> List[EmailLog]: ...
