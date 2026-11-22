"""Web 冒烟测试：页面可渲染、路由/角色校验、CSRF（testing 下豁免）与关键表单流程。"""
from __future__ import annotations

from app.domain.enums import PolicyType
from conftest import make_activity


def login_student(client, student_id="stu_demo1"):
    return client.post("/demo/session", data={"role": "STUDENT", "user_id": student_id})


def login_admin(client):
    return client.post("/demo/session", data={"role": "ADMIN"})


def test_student_flow(client):
    ctx = client.application.extensions["ctx"]
    activity = make_activity("篮球赛", capacity=2, policy=PolicyType.DIRECT)
    ctx.activity_service.create("admin", activity)

    assert client.get("/demo/login").status_code == 200
    resp = login_student(client)
    assert resp.status_code == 302

    assert client.get("/activities").status_code == 200
    detail = client.get(f"/activities/{activity.activity_id}")
    assert detail.status_code == 200

    reg = client.post(f"/activities/{activity.activity_id}/registrations", data={})
    assert reg.status_code == 302
    assert client.get("/registrations").status_code == 200

    notifications = client.get("/notifications")
    assert notifications.status_code == 200
    messages = ctx.message_repository.find_by_student("stu_demo1")
    assert len(messages) == 1
    read = client.post(f"/notifications/{messages[0].message_id}/read", data={})
    assert read.status_code == 302
    assert ctx.message_repository.find_by_id(messages[0].message_id).is_read

    # 越权：学生访问管理端 → 403
    assert client.get("/admin/activities").status_code == 403
    # 未登录 → 跳演示入口
    with client.session_transaction() as sess:
        sess.clear()
    assert client.get("/activities").status_code == 302


def test_admin_flow(client):
    ctx = client.application.extensions["ctx"]
    resp = login_admin(client)
    assert resp.status_code == 302

    assert client.get("/admin/activities").status_code == 200
    form = {
        "title": "讲座",
        "category": "讲座",
        "start_at": "2026-12-01T10:00",
        "location": "报告厅",
        "capacity": "10",
        "policy_type": "APPROVAL",
    }
    created = client.post("/admin/activities/new", data=form)
    assert created.status_code == 302
    activity = ctx.activity_service.search("讲座")[0]

    # 学生报名 → 待审核
    ctx.registration_service.submit("stu_demo1", activity.activity_id)
    approvals = client.get(f"/admin/activities/{activity.activity_id}/approvals")
    assert approvals.status_code == 200

    from app.domain.enums import RegistrationStatus
    pending = ctx.registration_repository.find_by_activity_and_status(
        activity.activity_id, RegistrationStatus.PENDING
    )
    reg_id = pending[0].registration_id
    assert client.post(
        f"/admin/registrations/{reg_id}/approve",
        data={"activity_id": activity.activity_id},
    ).status_code == 302
    assert ctx.registration_repository.find_by_id(reg_id).status.value == "APPROVED"

    stats = client.get(f"/admin/activities/{activity.activity_id}/statistics")
    assert stats.status_code == 200
    assert "1" in stats.get_data(as_text=True)

    # 无报名活动可删除
    empty = make_activity("可删活动", capacity=5, policy=PolicyType.DIRECT)
    ctx.activity_service.create("admin", empty)
    assert client.post(
        f"/admin/activities/{empty.activity_id}/delete", data={}
    ).status_code == 302
    assert ctx.activity_service.find_by_id(empty.activity_id) is None
