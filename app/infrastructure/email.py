"""模拟邮件发送器：不接真实 SMTP，只把发送结果写入 email_log。

- 成功：status=SENT；
- 失败：先写 status=FAILED + error，再抛 EmailSendError，交给发布者写失败日志；
- 测试可通过 fail_next=True 模拟一次发送故障。
"""
from __future__ import annotations

from ..domain.email import EmailLogRepository, EmailSender
from ..domain.enums import EmailStatus
from ..domain.errors import EmailSendError
from ..domain.ids import new_id
from ..domain.value_objects import EmailLog, EmailMessage


class MockEmailSender(EmailSender):
    def __init__(self, email_log_repository: EmailLogRepository, fail_next: bool = False):
        self.email_log_repository = email_log_repository
        self.fail_next = fail_next

    def send(self, message: EmailMessage) -> None:
        log = EmailLog(
            email_id=new_id("email"),
            event_key=message.event_key,
            registration_id=message.registration_id,
            student_id=message.student_id,
            recipient=message.recipient,
            subject=message.subject,
            content=message.content,
            status=EmailStatus.SENT,
        )
        if self.fail_next:
            self.fail_next = False
            log.status = EmailStatus.FAILED
            log.error = "模拟邮件服务器故障"
            self.email_log_repository.save(log)
            raise EmailSendError(log.error)
        self.email_log_repository.save(log)
