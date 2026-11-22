"""NFR-01 冒烟：200 活动列表与 500 报名统计在 2s 内完成（演示数据口径）。"""
from __future__ import annotations

import time

from app.domain.entities import Registration
from app.domain.enums import PolicyType, RegistrationStatus
from app.domain.events import new_id
from conftest import future_start, make_activity


def test_200_activities_search_under_2s(make_ctx):
    ctx = make_ctx()
    for i in range(200):
        activity = make_activity(f"活动{i:03d}", capacity=50, policy=PolicyType.DIRECT,
                                 start_at=future_start(days=(i % 60) + 1))
        ctx.activity_service.create("admin", activity)
    start = time.perf_counter()
    summaries = ctx.activity_service.search("")
    elapsed = time.perf_counter() - start
    assert len(summaries) == 200
    assert elapsed < 2.0
    ctx.close()


def test_500_registrations_statistics_under_2s(make_ctx):
    ctx = make_ctx()
    activity = make_activity("大课讲座", capacity=600, policy=PolicyType.APPROVAL)
    ctx.activity_service.create("admin", activity)
    conn = ctx.provider.get()
    for i in range(500):
        conn.execute(
            "INSERT OR IGNORE INTO students(student_id, name) VALUES (?, ?)",
            (f"stu_{i:04d}", f"学生{i}"),
        )
    for i in range(500):
        conn.execute(
            "INSERT INTO registrations(registration_id, activity_id, student_id, status, "
            "created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (new_id("reg"), activity.activity_id, f"stu_{i:04d}", "APPROVED",
             "2026-11-01T10:00:00", "2026-11-01T10:00:00"),
        )
    start = time.perf_counter()
    stats = ctx.statistics_service.for_activity(activity.activity_id)
    elapsed = time.perf_counter() - start
    assert stats.approved_count == 500
    assert elapsed < 2.0
    ctx.close()
