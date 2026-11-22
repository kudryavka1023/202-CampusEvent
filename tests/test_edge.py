"""边界与并发用例 E1～E10。"""
from __future__ import annotations

import threading

from app.composition import AppContext
from app.domain.enums import ApprovalDecision, PolicyType, RegistrationStatus
from app.domain.events import RegistrationObserver
from conftest import future_start, make_activity, past_start


def test_e1_register_after_start(ctx):
    """E1 活动已开始后报名：拒绝（ACTIVITY_CLOSED）。"""
    activity = make_activity(start_at=past_start())
    ctx.activity_repository.save(activity)  # 绕过创建校验，直接落一条已开始的活动
    result = ctx.registration_service.submit("stu_demo1", activity.activity_id)
    assert not result.is_success()
    assert result.error_code == "ACTIVITY_CLOSED"


def test_e2_concurrent_last_seat(make_ctx, tmp_path):
    """E2 两名学生并发抢最后一个名额：恰好 1 人成功。"""
    db_path = str(tmp_path / "e2.db")
    failure_log = str(tmp_path / "failure.log")

    def seed():
        ctx = AppContext(db_path=db_path, failure_log_path=failure_log)
        activity = make_activity("篮球赛", capacity=1, policy=PolicyType.DIRECT)
        ctx.activity_service.create("admin", activity)
        ctx.close()
        return activity.activity_id

    activity_id = seed()
    barrier = threading.Barrier(2)
    results = {}

    def worker(student_id):
        ctx = AppContext(db_path=db_path, failure_log_path=failure_log)
        barrier.wait()
        results[student_id] = ctx.registration_service.submit(student_id, activity_id)
        ctx.close()

    threads = [
        threading.Thread(target=worker, args=("stu_demo1",)),
        threading.Thread(target=worker, args=("stu_demo2",)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    successes = [r for r in results.values() if r.is_success()]
    failures = [r for r in results.values() if not r.is_success()]
    assert len(successes) == 1
    assert failures and failures[0].error_code == "SEATS_FULL"
    check = AppContext(db_path=db_path, failure_log_path=failure_log)
    assert check.registration_repository.count_by_activity_and_status(
        activity_id, RegistrationStatus.APPROVED
    ) == 1
    check.close()


def test_e3_concurrent_approval_last_seat(make_ctx, tmp_path):
    """E3 两名管理员并发批准最后一个名额：恰好 1 人成功。"""
    db_path = str(tmp_path / "e3.db")
    failure_log = str(tmp_path / "failure.log")
    ctx = AppContext(db_path=db_path, failure_log_path=failure_log)
    activity = make_activity("讲座", capacity=1, policy=PolicyType.APPROVAL)
    ctx.activity_service.create("admin", activity)
    reg_a = ctx.registration_service.submit("stu_demo1", activity.activity_id).registration
    reg_b = ctx.registration_service.submit("stu_demo2", activity.activity_id).registration
    ctx.close()

    barrier = threading.Barrier(2)
    results = {}

    def worker(reg_id):
        ctx = AppContext(db_path=db_path, failure_log_path=failure_log)
        barrier.wait()
        results[reg_id] = ctx.registration_service.review(
            "admin", reg_id, ApprovalDecision.APPROVE
        )
        ctx.close()

    threads = [
        threading.Thread(target=worker, args=(reg_a.registration_id,)),
        threading.Thread(target=worker, args=(reg_b.registration_id,)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    successes = [r for r in results.values() if r.is_success()]
    assert len(successes) == 1
    check = AppContext(db_path=db_path, failure_log_path=failure_log)
    assert check.registration_repository.count_by_activity_and_status(
        activity.activity_id, RegistrationStatus.APPROVED
    ) == 1
    check.close()


class FailingObserver(RegistrationObserver):
    def on_registration_event(self, event):
        raise RuntimeError("boom")


def test_e4_notification_failure_isolated(ctx):
    """E4 通知观察者抛异常：业务仍成功，失败留痕，后续观察者继续执行。"""
    ctx.event_publisher.observers.insert(0, FailingObserver())  # 放在消息观察者之前
    activity = make_activity("篮球赛", capacity=2, policy=PolicyType.DIRECT)
    ctx.activity_service.create("admin", activity)
    result = ctx.registration_service.submit("stu_demo1", activity.activity_id)
    assert result.is_success()
    assert ctx.registration_repository.find_by_id(result.registration.registration_id) is not None
    assert len(ctx.message_repository.find_by_student("stu_demo1")) == 1  # 后续观察者仍执行
    log_text = open(ctx.failure_log_path, encoding="utf-8").read()
    assert result.registration.registration_id in log_text


def test_e5_delete_activity_with_registrations(ctx):
    """E5 删除有报名的活动：拒绝删除，数据不变。"""
    activity = make_activity("篮球赛", capacity=2, policy=PolicyType.DIRECT)
    ctx.activity_service.create("admin", activity)
    ctx.registration_service.submit("stu_demo1", activity.activity_id)
    result = ctx.activity_service.delete("admin", activity.activity_id)
    assert not result.is_success()
    assert result.error_code == "ACTIVITY_HAS_REGISTRATIONS"
    assert ctx.activity_service.find_by_id(activity.activity_id) is not None
    assert ctx.registration_repository.exists_by_activity(activity.activity_id)


def test_e6_change_policy_with_active_registration(ctx):
    """E6 有有效报名时改报名方式：拒绝修改。"""
    activity = make_activity("篮球赛", capacity=2, policy=PolicyType.DIRECT)
    ctx.activity_service.create("admin", activity)
    ctx.registration_service.submit("stu_demo1", activity.activity_id)
    changed = make_activity("篮球赛", capacity=2, policy=PolicyType.APPROVAL)
    result = ctx.activity_service.update("admin", activity.activity_id, changed)
    assert not result.is_success()
    assert result.error_code == "POLICY_IMMUTABLE"


def test_e7_capacity_below_approved(ctx):
    """E7 容量下调到小于已通过数：拒绝保存。"""
    activity = make_activity("篮球赛", capacity=3, policy=PolicyType.DIRECT)
    ctx.activity_service.create("admin", activity)
    ctx.registration_service.submit("stu_demo1", activity.activity_id)
    ctx.registration_service.submit("stu_demo2", activity.activity_id)
    changed = make_activity("篮球赛", capacity=1, policy=PolicyType.DIRECT)
    result = ctx.activity_service.update("admin", activity.activity_id, changed)
    assert not result.is_success()
    assert result.error_code == "CAPACITY_BELOW_APPROVED"


def test_e8_cancel_others_registration(ctx):
    """E8 学生取消他人报名：拒绝（NOT_FOUND，不泄露存在性）。"""
    activity = make_activity("篮球赛", capacity=2, policy=PolicyType.DIRECT)
    ctx.activity_service.create("admin", activity)
    reg = ctx.registration_service.submit("stu_demo1", activity.activity_id).registration
    result = ctx.registration_service.cancel("stu_demo2", reg.registration_id)
    assert not result.is_success()
    assert result.error_code == "NOT_FOUND"
    assert ctx.registration_repository.find_by_id(reg.registration_id).status is RegistrationStatus.APPROVED


def test_e9_reapply_after_reject(ctx):
    """E9 已拒绝后再次申请：新建记录，旧记录保留，有效报名仍最多 1 条。"""
    activity = make_activity("讲座", capacity=10, policy=PolicyType.APPROVAL)
    ctx.activity_service.create("admin", activity)
    first = ctx.registration_service.submit("stu_demo1", activity.activity_id).registration
    ctx.registration_service.review("admin", first.registration_id, ApprovalDecision.REJECT)
    second = ctx.registration_service.submit("stu_demo1", activity.activity_id)
    assert second.is_success()
    assert second.registration.registration_id != first.registration_id
    history = ctx.registration_repository.find_by_student("stu_demo1")
    assert len([r for r in history if r.activity_id == activity.activity_id]) == 2
    assert ctx.registration_repository.find_active("stu_demo1", activity.activity_id) is not None


def test_e10_review_already_handled(ctx):
    """E10 审批已处理报名：ALREADY_HANDLED，状态不变。"""
    activity = make_activity("讲座", capacity=10, policy=PolicyType.APPROVAL)
    ctx.activity_service.create("admin", activity)
    reg = ctx.registration_service.submit("stu_demo1", activity.activity_id).registration
    ctx.registration_service.review("admin", reg.registration_id, ApprovalDecision.APPROVE)
    again = ctx.registration_service.review("admin", reg.registration_id, ApprovalDecision.APPROVE)
    assert not again.is_success()
    assert again.error_code == "ALREADY_HANDLED"
    assert ctx.registration_repository.find_by_id(reg.registration_id).status is RegistrationStatus.APPROVED
