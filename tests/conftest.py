"""pytest 夹具：独立 SQLite 文件、可重启的 AppContext、Flask 测试客户端。"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from app import create_app
from app.composition import AppContext
from app.domain.entities import Activity
from app.domain.enums import PolicyType

TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"


def future_start(days: int = 7) -> str:
    return (datetime.now() + timedelta(days=days)).strftime(TIME_FORMAT)


def past_start(days: int = 7) -> str:
    return (datetime.now() - timedelta(days=days)).strftime(TIME_FORMAT)


def make_activity(title="篮球赛", category="比赛", capacity=2, policy=PolicyType.DIRECT,
                  start_at=None, allowed_grades=None) -> Activity:
    return Activity(
        activity_id=f"act_{uuid.uuid4().hex[:10]}",
        title=title,
        category=category,
        start_at=start_at or future_start(),
        location="体育馆",
        capacity=capacity,
        policy_type=policy,
        allowed_grades=allowed_grades,
    )


@pytest.fixture
def make_ctx(tmp_path):
    """返回 AppContext 工厂；每次调用用独立 DB 文件，支持自定义策略集合（CR-1 模拟）。"""
    counter = {"n": 0}

    def _make(policy_types=(PolicyType.DIRECT, PolicyType.APPROVAL), extra_policies=None):
        counter["n"] += 1
        db_path = tmp_path / f"campus_{counter['n']}.db"
        return AppContext(
            db_path=str(db_path),
            failure_log_path=str(tmp_path / "notification-failure.log"),
            extra_policies=extra_policies,
            policy_types=policy_types,
        )

    return _make


@pytest.fixture
def ctx(make_ctx):
    context = make_ctx()
    yield context
    context.close()


@pytest.fixture
def client(tmp_path):
    app = create_app(
        db_path=str(tmp_path / "web.db"),
        failure_log_path=str(tmp_path / "notification-failure.log"),
        testing=True,
    )
    return app.test_client()
