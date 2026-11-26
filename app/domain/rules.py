"""报名资格规则（可组合）。

设计选择（见 docs/CR-01-CR-02-影响分析.md）：
- 年级限定是“是否允许报名”的公共资格约束，不是“初始状态”决策；
- 因此不新增 PolicyType，也不污染 RegistrationPolicy 契约；
- RegistrationService 只保留一个通用钩子：按顺序执行 EligibilityRule，
  返回第一个 EligibilityViolation 即拒绝；规则本身不查库、不写库、不改上下文。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, List, Optional

from .entities import GRADE_TEXT
from .errors import GRADE_NOT_ALLOWED
from .value_objects import EligibilityViolation, RegistrationContext


class EligibilityRule(ABC):
    @abstractmethod
    def check(self, context: RegistrationContext) -> Optional[EligibilityViolation]:
        """返回 None 表示通过；返回 violation 表示拒绝。"""


class CompositeEligibilityRule(EligibilityRule):
    """组合规则：按注册顺序执行，返回第一个失败；全部通过返回 None。"""

    def __init__(self, rules: Optional[Iterable[EligibilityRule]] = None):
        self.rules: List[EligibilityRule] = list(rules or [])

    def add(self, rule: EligibilityRule) -> None:
        self.rules.append(rule)

    def check(self, context: RegistrationContext) -> Optional[EligibilityViolation]:
        for rule in self.rules:
            violation = rule.check(context)
            if violation is not None:
                return violation
        return None


class GradeEligibilityRule(EligibilityRule):
    """活动配置了 allowedGrades 时，只允许指定年级报名。"""

    def check(self, context: RegistrationContext) -> Optional[EligibilityViolation]:
        activity = context.get_activity()
        if activity.allowed_grades is None:
            return None
        student = context.get_student()
        if student is None:
            return EligibilityViolation(
                GRADE_NOT_ALLOWED, "无法确认学生年级，不能报名该活动"
            )
        if activity.is_grade_allowed(student.get_grade()):
            return None
        allowed = activity.grade_requirement_text()
        current = GRADE_TEXT.get(student.get_grade(), str(student.get_grade()))
        return EligibilityViolation(
            GRADE_NOT_ALLOWED,
            f"该活动仅限{allowed}学生报名，当前年级：{current}",
        )
