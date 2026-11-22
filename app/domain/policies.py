"""报名策略（Strategy + Factory）。

契约（LSP，写在注释与测试里）：
- 前置：context.activity / context.now 非空，approved_count >= 0；
- 后置：只返回 APPROVED 或 PENDING；不修改 context；不查库；不抛业务异常。
公共规则（活动状态、重复、名额）由 RegistrationService + Activity 负责，
策略只回答“提交后是已通过还是待审核”。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict

from .enums import PolicyType, RegistrationStatus
from .errors import PolicyNotConfiguredError
from .value_objects import RegistrationContext


class RegistrationPolicy(ABC):
    @abstractmethod
    def policy_type(self) -> PolicyType: ...

    @abstractmethod
    def decide_initial_status(self, context: RegistrationContext) -> RegistrationStatus: ...


class DirectRegistrationPolicy(RegistrationPolicy):
    def policy_type(self) -> PolicyType:
        return PolicyType.DIRECT

    def decide_initial_status(self, context: RegistrationContext) -> RegistrationStatus:
        return RegistrationStatus.APPROVED


class ApprovalRegistrationPolicy(RegistrationPolicy):
    def policy_type(self) -> PolicyType:
        return PolicyType.APPROVAL

    def decide_initial_status(self, context: RegistrationContext) -> RegistrationStatus:
        return RegistrationStatus.PENDING


class RegistrationPolicyFactory:
    def __init__(self, policies=None):
        # 按报名方式的“值”注册，支持后续扩展枚举（如抽签）
        self.policies: Dict[str, RegistrationPolicy] = {}
        for policy in policies or []:
            self.register(policy)

    def register(self, policy: RegistrationPolicy) -> None:
        self.policies[policy.policy_type().value] = policy

    def create(self, policy_type) -> RegistrationPolicy:
        key = getattr(policy_type, "value", policy_type)
        policy = self.policies.get(key)
        if policy is None:
            raise PolicyNotConfiguredError(f"报名方式未配置策略：{key}")
        return policy

    def check_complete(self, allowed: tuple) -> None:
        """启动自检：枚举值是否都有策略，缺失快速失败。"""
        allowed_values = {getattr(p, "value", p) for p in allowed}
        missing = [v for v in allowed_values if v not in self.policies]
        if missing:
            raise PolicyNotConfiguredError(f"缺少策略：{missing}")
