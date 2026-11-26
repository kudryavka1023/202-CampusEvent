"""change-v2 验收：CR-01 年级限定报名、CR-02 模拟邮件通知。

CR1-05 / CR2-05 直接重跑 baseline-v1 的 C1—C10，作为“变更未破坏原行为”的
可执行证据；完整回归仍以 `pytest` 全量结果为准。
"""
from __future__ import annotations

from app.domain.enums import (
    ApprovalDecision,
    EmailStatus,
    PolicyType,
    RegistrationEventType,
    RegistrationStatus,
)
from app.domain.value_objects import RegistrationEvent
from conftest import make_activity


def messages_for(ctx, student_id):
    return ctx.message_repository.find_by_student(student_id)


def emails_for(ctx):
    return ctx.email_log_repository.find_all()


# ---------------- CR-01 年级限定 ----------------

def test_cr1_01_grade2_can_register(ctx):
    activity = make_activity("仅大二大三", capacity=5, policy=PolicyType.DIRECT,
                             allowed_grades=(2, 3))
    ctx.activity_service.create("admin", activity)
    result = ctx.registration_service.submit("stu_demo1", activity.activity_id)  # 大二
    assert result.is_success()
    assert result.registration.status is RegistrationStatus.APPROVED
    assert ctx.registration_repository.count_by_activity_and_status(
        activity.activity_id, RegistrationStatus.APPROVED
    ) == 1


def test_cr1_02_grade3_can_register(ctx):
    activity = make_activity("仅大二大三", capacity=5, policy=PolicyType.DIRECT,
                             allowed_grades=(2, 3))
    ctx.activity_service.create("admin", activity)
    result = ctx.registration_service.submit("stu_demo2", activity.activity_id)  # 大三
    assert result.is_success()
    assert result.registration.status is RegistrationStatus.APPROVED


def test_cr1_03_grade1_rejected_with_reason(ctx):
    activity = make_activity("仅大二大三", capacity=5, policy=PolicyType.DIRECT,
                             allowed_grades=(2, 3))
    ctx.activity_service.create("admin", activity)
    result = ctx.registration_service.submit("stu_demo3", activity.activity_id)  # 大一
    assert not result.is_success()
    assert result.error_code == "GRADE_NOT_ALLOWED"
    assert "大二" in result.message and "大三" in result.message
    assert "大一" in result.message
    assert ctx.registration_repository.find_by_student("stu_demo3") == []
    assert messages_for(ctx, "stu_demo3") == []
    assert emails_for(ctx) == []


def test_cr1_04_grade4_rejected_with_reason(ctx):
    activity = make_activity("仅大二大三", capacity=5, policy=PolicyType.DIRECT,
                             allowed_grades=(2, 3))
    ctx.activity_service.create("admin", activity)
    result = ctx.registration_service.submit("stu_demo4", activity.activity_id)  # 大四
    assert not result.is_success()
    assert result.error_code == "GRADE_NOT_ALLOWED"
    assert "大四" in result.message
    assert ctx.registration_repository.find_by_student("stu_demo4") == []
    assert messages_for(ctx, "stu_demo4") == []


def _run_baseline_acceptance(make_ctx):
    """按 baseline-v1 的夹具口径重跑 C1—C10。"""
    import test_acceptance as baseline

    context = make_ctx()
    try:
        baseline.test_c1_create_direct_activity(context)
        baseline.test_c2_student_a_registers_direct_activity(context)
        baseline.test_c3_duplicate_active_registration(context)
        baseline.test_c4_capacity_full(context)
        baseline.test_c5_approval_activity_pending(context)
        baseline.test_c6_admin_approves(context)
        baseline.test_c7_admin_rejects(context)
        baseline.test_c8_approval_capacity_full(context)
        baseline.test_c9_cancel_and_statistics(context)
    finally:
        context.close()
    baseline.test_c10_restart_persistence(make_ctx)


def test_cr1_05_baseline_c1_c10_still_pass(make_ctx):
    _run_baseline_acceptance(make_ctx)


# ---------------- CR-02 模拟邮件 ----------------

def test_cr2_01_direct_pass_sends_site_and_email(ctx):
    activity = make_activity("直接报名", capacity=5, policy=PolicyType.DIRECT)
    ctx.activity_service.create("admin", activity)
    result = ctx.registration_service.submit("stu_demo1", activity.activity_id)
    assert result.is_success()

    msgs = messages_for(ctx, "stu_demo1")
    assert len(msgs) == 1 and "已通过" in msgs[0].content

    logs = emails_for(ctx)
    assert len(logs) == 1
    log = logs[0]
    assert log.status is EmailStatus.SENT
    assert log.recipient == "zhangsan@campus.edu"
    assert "报名已通过" in log.subject
    assert activity.activity_id in log.content
    assert log.registration_id == result.registration.registration_id


def test_cr2_02_approve_and_reject_send_both_channels(ctx):
    activity = make_activity("审核报名", capacity=5, policy=PolicyType.APPROVAL)
    ctx.activity_service.create("admin", activity)

    submitted = ctx.registration_service.submit("stu_demo1", activity.activity_id)
    assert submitted.is_success()
    assert submitted.registration.status is RegistrationStatus.PENDING
    # 待审核提交只有站内消息，不发邮件（CR-02 范围）
    assert any("等待审核" in m.content for m in messages_for(ctx, "stu_demo1"))
    assert emails_for(ctx) == []

    approved = ctx.registration_service.review(
        "admin", submitted.registration.registration_id, ApprovalDecision.APPROVE
    )
    assert approved.is_success()
    assert any("已通过审核" in m.content for m in messages_for(ctx, "stu_demo1"))
    approve_logs = emails_for(ctx)
    assert len(approve_logs) == 1
    assert approve_logs[0].status is EmailStatus.SENT
    assert "审核已通过" in approve_logs[0].subject

    second = ctx.registration_service.submit("stu_demo2", activity.activity_id)
    rejected = ctx.registration_service.review(
        "admin", second.registration.registration_id, ApprovalDecision.REJECT, "名额调整"
    )
    assert rejected.is_success()
    assert any("名额调整" in m.content for m in messages_for(ctx, "stu_demo2"))
    reject_logs = emails_for(ctx)
    assert len(reject_logs) == 2
    reject_log = next(log for log in reject_logs if log.student_id == "stu_demo2")
    assert reject_log.status is EmailStatus.SENT
    assert "未通过" in reject_log.subject
    assert "名额调整" in reject_log.content


def test_cr2_03_email_failure_keeps_registration_and_logs(ctx, tmp_path):
    activity = make_activity("邮件故障", capacity=5, policy=PolicyType.DIRECT)
    ctx.activity_service.create("admin", activity)

    ctx.email_sender.fail_next = True
    result = ctx.registration_service.submit("stu_demo1", activity.activity_id)
    assert result.is_success()
    assert result.registration.status is RegistrationStatus.APPROVED
    assert ctx.registration_repository.count_by_activity_and_status(
        activity.activity_id, RegistrationStatus.APPROVED
    ) == 1

    logs = emails_for(ctx)
    assert len(logs) == 1
    assert logs[0].status is EmailStatus.FAILED
    assert logs[0].error
    assert logs[0].registration_id == result.registration.registration_id

    failure_text = open(ctx.failure_log_path, encoding="utf-8").read()
    assert result.registration.registration_id in failure_text
    assert "EmailSendError" in failure_text


def test_cr2_04_duplicate_action_no_duplicate_notifications(ctx):
    activity = make_activity("防重复", capacity=5, policy=PolicyType.DIRECT)
    ctx.activity_service.create("admin", activity)

    first = ctx.registration_service.submit("stu_demo1", activity.activity_id)
    assert first.is_success()
    duplicate = ctx.registration_service.submit("stu_demo1", activity.activity_id)
    assert not duplicate.is_success()
    assert duplicate.error_code == "DUPLICATE_ACTIVE"

    assert len(messages_for(ctx, "stu_demo1")) == 1
    assert len(emails_for(ctx)) == 1

    # 同一业务事件被重复发布（例如重试）也不得重复通知
    event = RegistrationEvent(
        event_id="evt_retry",
        registration_id=first.registration.registration_id,
        activity_id=activity.activity_id,
        student_id="stu_demo1",
        type=RegistrationEventType.SUBMITTED,
        status=RegistrationStatus.APPROVED,
    )
    ctx.event_publisher.publish(event)
    ctx.event_publisher.publish(event)
    assert len(messages_for(ctx, "stu_demo1")) == 1
    assert len(emails_for(ctx)) == 1


def test_cr2_05_baseline_c1_c10_still_pass(make_ctx):
    _run_baseline_acceptance(make_ctx)


# ---------------- Web 冒烟：年级表单/提示、邮件记录页 ----------------

def test_cr1_web_grade_form_and_rejection(client):
    from conftest import future_start

    ctx = client.application.extensions["ctx"]
    client.post("/demo/session", data={"role": "ADMIN"})
    form = {
        "title": "年级限定讲座",
        "category": "讲座",
        "start_at": future_start()[:16],
        "location": "报告厅",
        "capacity": "10",
        "policy_type": "DIRECT",
        "allowed_grades": ["2", "3"],
    }
    assert client.post("/admin/activities/new", data=form).status_code == 302
    activity = ctx.activity_service.search("年级限定讲座")[0]
    assert activity.allowed_grades == (2, 3)

    client.post("/demo/session", data={"role": "STUDENT", "user_id": "stu_demo3"})
    detail = client.get(f"/activities/{activity.activity_id}")
    assert detail.status_code == 200
    assert "仅限大二、大三" in detail.get_data(as_text=True)
    assert client.post(
        f"/activities/{activity.activity_id}/registrations", data={}
    ).status_code == 302
    assert ctx.registration_repository.find_by_student("stu_demo3") == []


def test_cr2_web_admin_email_log_page(client):
    ctx = client.application.extensions["ctx"]
    activity = make_activity("邮件页活动", capacity=5, policy=PolicyType.DIRECT)
    ctx.activity_service.create("admin", activity)

    client.post("/demo/session", data={"role": "STUDENT", "user_id": "stu_demo1"})
    assert client.post(
        f"/activities/{activity.activity_id}/registrations", data={}
    ).status_code == 302

    client.post("/demo/session", data={"role": "ADMIN"})
    page = client.get("/admin/emails")
    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert "报名已通过" in body
    assert "zhangsan@campus.edu" in body

