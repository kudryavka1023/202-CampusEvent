"""领域枚举：与 SRS/状态图/数据库 CHECK 保持四值、两值一致。"""
from enum import Enum


class RegistrationStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class PolicyType(str, Enum):
    DIRECT = "DIRECT"
    APPROVAL = "APPROVAL"


class ApprovalDecision(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


class RegistrationEventType(str, Enum):
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
