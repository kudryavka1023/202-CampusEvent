"""组合根：启动时集中装配具体实现，服务只依赖接口。"""
from __future__ import annotations

import os

from .application.services import (
    ActivityService,
    NotificationQueryService,
    RegistrationService,
    StatisticsService,
)
from .domain.enums import PolicyType
from .domain.events import (
    MessageNotificationObserver,
    NotificationFailureLogger,
    SimpleRegistrationEventPublisher,
)
from .domain.policies import (
    ApprovalRegistrationPolicy,
    DirectRegistrationPolicy,
    RegistrationPolicyFactory,
)
from .infrastructure.db import ConnectionProvider
from .infrastructure.repositories import (
    SqliteActivityRepository,
    SqliteMessageRepository,
    SqliteRegistrationRepository,
    SqliteStudentRepository,
)
from .infrastructure.transactions import TransactionManager
from .ui.controllers import (
    ActivityController,
    ApprovalController,
    NotificationController,
    RegistrationController,
    StatisticsController,
)

DEFAULT_DB_PATH = os.path.join("data", "campus.db")
DEFAULT_FAILURE_LOG = os.path.join("logs", "notification-failure.log")


class AppContext:
    """容器对象：提供 provider、仓储、服务与控制器，供 Flask 与测试使用。"""

    def __init__(self, db_path: str = DEFAULT_DB_PATH,
                 failure_log_path: str = DEFAULT_FAILURE_LOG,
                 extra_policies=None, policy_types=None):
        policy_types = policy_types or (PolicyType.DIRECT, PolicyType.APPROVAL)
        self.db_path = db_path
        self.failure_log_path = failure_log_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

        self.provider = ConnectionProvider(db_path)
        self.provider.initialize(allowed_policy_types=policy_types)

        self.transaction_manager = TransactionManager(self.provider)
        self.activity_repository = SqliteActivityRepository(self.provider)
        self.registration_repository = SqliteRegistrationRepository(self.provider)
        self.message_repository = SqliteMessageRepository(self.provider)
        self.student_repository = SqliteStudentRepository(self.provider)

        policies = [DirectRegistrationPolicy(), ApprovalRegistrationPolicy()] + list(extra_policies or [])
        self.policy_factory = RegistrationPolicyFactory(policies)
        self.policy_factory.check_complete(tuple(policy_types))

        self.failure_logger = NotificationFailureLogger(failure_log_path)
        self.event_publisher = SimpleRegistrationEventPublisher(
            [MessageNotificationObserver(self.message_repository)], self.failure_logger
        )

        self.activity_service = ActivityService(
            self.activity_repository, self.registration_repository, self.transaction_manager,
            allowed_policy_values={p.value for p in policy_types},
        )
        self.registration_service = RegistrationService(
            self.activity_repository, self.registration_repository,
            self.policy_factory, self.event_publisher, self.transaction_manager,
        )
        self.statistics_service = StatisticsService(
            self.activity_repository, self.registration_repository
        )
        self.notification_service = NotificationQueryService(self.message_repository)

        self.activity_controller = ActivityController(
            self.activity_service, self.registration_service, self.statistics_service
        )
        self.registration_controller = RegistrationController(self.registration_service)
        self.approval_controller = ApprovalController(self.registration_service)
        self.notification_controller = NotificationController(self.notification_service)
        self.statistics_controller = StatisticsController(self.statistics_service)

    def close(self):
        self.provider.close_all()
