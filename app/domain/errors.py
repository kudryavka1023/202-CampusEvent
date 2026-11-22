"""错误码与领域异常。

命令式服务方法（submit/cancel/review/create/update/delete）用结果对象返回
预期业务失败；查询方法在“资源不存在”时抛 NotFoundError（路由层转 404），
与设计说明书 7.3/9.1 一致。
"""

# 错误码（与设计说明书 9.1 对齐）
NOT_FOUND = "NOT_FOUND"
UNAUTHORIZED = "UNAUTHORIZED"
FORBIDDEN = "FORBIDDEN"
VALIDATION_ERROR = "VALIDATION_ERROR"
ACTIVITY_CLOSED = "ACTIVITY_CLOSED"
DUPLICATE_ACTIVE = "DUPLICATE_ACTIVE"
SEATS_FULL = "SEATS_FULL"
ALREADY_HANDLED = "ALREADY_HANDLED"
INVALID_STATE = "INVALID_STATE"
ACTIVITY_HAS_REGISTRATIONS = "ACTIVITY_HAS_REGISTRATIONS"
CAPACITY_BELOW_APPROVED = "CAPACITY_BELOW_APPROVED"
POLICY_IMMUTABLE = "POLICY_IMMUTABLE"
POLICY_NOT_CONFIGURED = "POLICY_NOT_CONFIGURED"
PERSISTENCE_ERROR = "PERSISTENCE_ERROR"
NOTIFICATION_FAILED = "NOTIFICATION_FAILED"


class DomainError(Exception):
    """领域异常基类。"""


class InvalidStateError(DomainError):
    """实体状态迁移非法：approve/reject 仅 PENDING，cancel 仅 PENDING/APPROVED。"""


class NotFoundError(DomainError):
    """查询方法的“资源不存在”。"""


class PolicyNotConfiguredError(DomainError):
    """工厂找不到报名方式对应的策略。"""


class DuplicateActiveError(DomainError):
    """同一学生同一活动已存在有效报名（部分唯一索引冲突）。"""


class DuplicateEventKeyError(DomainError):
    """消息去重键唯一约束冲突：视为“已通知”。"""
