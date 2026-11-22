"""核心验收用例 C1～C10（需求验收表）——全部通过才可进入变更阶段。"""
from __future__ import annotations

from app.composition import AppContext
from app.domain.enums import ApprovalDecision, PolicyType, RegistrationStatus
from conftest import future_start, make_activity


def messages_for(ctx, student_id="stu_demo1"):
    return ctx.message_repository.find_by_student(student_id)


def test_c1_create_direct_activity(ctx):
    """C1 管理员创建直接报名活动，容量 2：创建成功，可被浏览/报名。"""
    activity = make_activity("篮球赛", capacity=2, policy=PolicyType.DIRECT)
    result = ctx.activity_service.create("admin", activity)
    assert result.is_success()
    assert ctx.activity_service.find_by_id(activity.activity_id) is not None
    assert any(s.activity_id == activity.activity_id for s in ctx.activity_service.search("篮球"))


def test_c2_student_a_registers_direct_activity(ctx):
    """C2 学生 A 报名直接报名活动：状态已通过，生成通知。"""
    activity = make_activity("篮球赛", capacity=2, policy=PolicyType.DIRECT)
    ctx.activity_service.create("admin", activity)
    result = ctx.registration_service.submit("stu_demo1", activity.activity_id)
    assert result.is_success()
    assert result.registration.status is RegistrationStatus.APPROVED
    assert ctx.registration_repository.count_by_activity_and_status(
        activity.activity_id, RegistrationStatus.APPROVED
    ) == 1
    msgs = messages_for(ctx)
    assert len(msgs) == 1
    assert "已通过" in msgs[0].content


def test_c3_duplicate_active_registration(ctx):
    """C3 学生 A 再次提交相同活动：拒绝重复有效报名，不新增记录。"""
    activity = make_activity("篮球赛", capacity=2, policy=PolicyType.DIRECT)
    ctx.activity_service.create("admin", activity)
    assert ctx.registration_service.submit("stu_demo1", activity.activity_id).is_success()
    second = ctx.registration_service.submit("stu_demo1", activity.activity_id)
    assert not second.is_success()
    assert second.error_code == "DUPLICATE_ACTIVE"
    assert ctx.registration_repository.count_by_activity_and_status(
        activity.activity_id, RegistrationStatus.APPROVED
    ) == 1


def test_c4_capacity_full(ctx):
    """C4 B 报名后名额满，C 再报名：B 通过，C 名额不足失败。"""
    activity = make_activity("篮球赛", capacity=2, policy=PolicyType.DIRECT)
    ctx.activity_service.create("admin", activity)
    assert ctx.registration_service.submit("stu_demo1", activity.activity_id).is_success()  # A
    assert ctx.registration_service.submit("stu_demo2", activity.activity_id).is_success()  # B
    ctx.provider.get().execute(
        "INSERT OR IGNORE INTO students(student_id, name) VALUES ('stu_demo3','王五')"
    )
    c = ctx.registration_service.submit("stu_demo3", activity.activity_id)
    assert not c.is_success()
    assert c.error_code == "SEATS_FULL"
    assert ctx.registration_repository.count_by_activity_and_status(
        activity.activity_id, RegistrationStatus.APPROVED
    ) == 2


def test_c5_approval_activity_pending(ctx):
    """C5 创建审核型活动，学生 A 申请：状态待审核。"""
    activity = make_activity("讲座", capacity=10, policy=PolicyType.APPROVAL)
    ctx.activity_service.create("admin", activity)
    result = ctx.registration_service.submit("stu_demo1", activity.activity_id)
    assert result.is_success()
    assert result.registration.status is RegistrationStatus.PENDING
    assert ctx.registration_repository.count_by_activity_and_status(
        activity.activity_id, RegistrationStatus.APPROVED
    ) == 0
    assert any("等待审核" in m.content for m in messages_for(ctx))


def test_c6_admin_approves(ctx):
    """C6 管理员批准 A 的待审核报名：已通过且生成通知。"""
    activity = make_activity("讲座", capacity=10, policy=PolicyType.APPROVAL)
    ctx.activity_service.create("admin", activity)
    submitted = ctx.registration_service.submit("stu_demo1", activity.activity_id)
    result = ctx.registration_service.review(
        "admin", submitted.registration.registration_id, ApprovalDecision.APPROVE
    )
    assert result.is_success()
    assert result.registration.status is RegistrationStatus.APPROVED
    assert ctx.registration_repository.count_by_activity_and_status(
        activity.activity_id, RegistrationStatus.APPROVED
    ) == 1
    assert any("已通过审核" in m.content for m in messages_for(ctx))


def test_c7_admin_rejects(ctx):
    """C7 管理员拒绝另一待审核报名：已拒绝且生成含理由通知。"""
    activity = make_activity("讲座", capacity=10, policy=PolicyType.APPROVAL)
    ctx.activity_service.create("admin", activity)
    submitted = ctx.registration_service.submit("stu_demo2", activity.activity_id)
    result = ctx.registration_service.review(
        "admin", submitted.registration.registration_id, ApprovalDecision.REJECT, "名额调整"
    )
    assert result.is_success()
    assert result.registration.status is RegistrationStatus.REJECTED
    assert ctx.registration_repository.count_by_activity_and_status(
        activity.activity_id, RegistrationStatus.APPROVED
    ) == 0
    assert any("名额调整" in m.content for m in messages_for(ctx, "stu_demo2"))


def test_c8_approval_capacity_full(ctx):
    """C8 批准时容量已满：批准失败，不超容量，状态保持待审核。"""
    activity = make_activity("讲座", capacity=1, policy=PolicyType.APPROVAL)
    ctx.activity_service.create("admin", activity)
    a = ctx.registration_service.submit("stu_demo1", activity.activity_id)
    b = ctx.registration_service.submit("stu_demo2", activity.activity_id)
    assert ctx.registration_service.review(
        "admin", a.registration.registration_id, ApprovalDecision.APPROVE
    ).is_success()
    result = ctx.registration_service.review(
        "admin", b.registration.registration_id, ApprovalDecision.APPROVE
    )
    assert not result.is_success()
    assert result.error_code == "SEATS_FULL"
    refreshed = ctx.registration_repository.find_by_id(b.registration.registration_id)
    assert refreshed.status is RegistrationStatus.PENDING
    assert ctx.registration_repository.count_by_activity_and_status(
        activity.activity_id, RegistrationStatus.APPROVED
    ) == 1


def test_c9_cancel_and_statistics(ctx):
    """C9 学生取消待审核/已通过报名：状态已取消，统计同步。"""
    direct = make_activity("篮球赛", capacity=5, policy=PolicyType.DIRECT)
    ctx.activity_service.create("admin", direct)
    r = ctx.registration_service.submit("stu_demo1", direct.activity_id)
    assert r.is_success() and r.registration.status is RegistrationStatus.APPROVED
    stats_before = ctx.statistics_service.for_activity(direct.activity_id)
    assert stats_before.get_remaining_seats() == 4

    cancel = ctx.registration_service.cancel("stu_demo1", r.registration.registration_id)
    assert cancel.is_success()
    assert cancel.registration.status is RegistrationStatus.CANCELLED
    stats_after = ctx.statistics_service.for_activity(direct.activity_id)
    assert stats_after.approved_count == 0
    assert stats_after.get_remaining_seats() == 5
    assert any("已取消报名" in m.content for m in messages_for(ctx))

    approval = make_activity("讲座", capacity=10, policy=PolicyType.APPROVAL)
    ctx.activity_service.create("admin", approval)
    p = ctx.registration_service.submit("stu_demo2", approval.activity_id)
    assert ctx.registration_service.cancel("stu_demo2", p.registration.registration_id).is_success()


def test_c10_restart_persistence(make_ctx):
    """C10 重启服务后查询活动、报名、通知：数据仍一致。"""
    ctx1 = make_ctx()
    activity = make_activity("篮球赛", capacity=2, policy=PolicyType.DIRECT)
    ctx1.activity_service.create("admin", activity)
    r = ctx1.registration_service.submit("stu_demo1", activity.activity_id)
    db_path, failure_log = ctx1.db_path, ctx1.failure_log_path
    ctx1.close()

    ctx2 = AppContext(db_path=db_path, failure_log_path=failure_log)
    assert ctx2.activity_service.find_by_id(activity.activity_id) is not None
    assert ctx2.registration_repository.find_by_id(r.registration.registration_id) is not None
    assert len(ctx2.message_repository.find_by_student("stu_demo1")) == 1
    ctx2.close()
