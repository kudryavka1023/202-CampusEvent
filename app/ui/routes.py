"""路由层：参数绑定、角色/会话校验、CSRF 检查、调用控制器、渲染结果。

不写业务规则，不直接访问 Repository；角色不匹配 403，未登录跳演示入口。
"""
from __future__ import annotations

import secrets
from functools import wraps

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from ..domain.enums import PolicyType
from ..domain.errors import NotFoundError
from ..domain.events import new_id

bp = Blueprint("bp", __name__)

ADMIN_ID = "admin"

STATUS_TEXT = {
    "PENDING": "待审核",
    "APPROVED": "已通过",
    "REJECTED": "已拒绝",
    "CANCELLED": "已取消",
}


def get_ctx():
    return current_app.extensions["ctx"]


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return session["csrf_token"]


def check_csrf():
    if current_app.testing:
        return
    token = request.form.get("csrf_token", "")
    if not token or token != session.get("csrf_token", None):
        abort(400, "CSRF 校验失败，请刷新页面重试")


def require(role):
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if "role" not in session or "user_id" not in session:
                return redirect(url_for("bp.demo_login"))
            if session["role"] != role:
                abort(403, "无权执行该操作")
            return view(*args, **kwargs)
        return wrapper
    return decorator


def student_id():
    return session["user_id"]


# ---------------- 演示身份 ----------------

@bp.get("/demo/login")
def demo_login():
    ctx = get_ctx()
    students = ctx.student_repository.all()
    return render_template("demo_login.html", students=students)


@bp.post("/demo/session")
def demo_session():
    check_csrf()
    role = request.form.get("role", "")
    user_id = request.form.get("user_id", "")
    if role == "ADMIN":
        session["role"] = "ADMIN"
        session["user_id"] = ADMIN_ID
        session["name"] = "管理员"
        return redirect(url_for("bp.admin_activity_list"))
    if role == "STUDENT":
        ctx = get_ctx()
        student = ctx.student_repository.find_by_id(user_id)
        if student is None:
            flash("学生不存在", "error")
            return redirect(url_for("bp.demo_login"))
        session["role"] = "STUDENT"
        session["user_id"] = student.student_id
        session["name"] = student.name
        return redirect(url_for("bp.activity_list"))
    flash("请选择演示身份", "error")
    return redirect(url_for("bp.demo_login"))


# ---------------- 学生端 ----------------

@bp.get("/activities")
@require("STUDENT")
def activity_list():
    keyword = request.args.get("keyword", "")
    summaries = get_ctx().activity_controller.list(keyword)
    return render_template("activity_list.html", summaries=summaries, keyword=keyword,
                           status_text=STATUS_TEXT)


@bp.get("/activities/<activity_id>")
@require("STUDENT")
def activity_detail(activity_id):
    try:
        page = get_ctx().activity_controller.detail(activity_id, student_id())
    except NotFoundError:
        abort(404, "活动不存在或已被删除")
    policy_value = getattr(page["activity"].policy_type, "value", page["activity"].policy_type)
    policy_label = "直接报名" if policy_value == "DIRECT" else "审核型报名"
    return render_template("activity_detail.html", page=page, status_text=STATUS_TEXT,
                           policy_label=policy_label)


@bp.post("/activities/<activity_id>/registrations")
@require("STUDENT")
def activity_register(activity_id):
    check_csrf()
    result = get_ctx().registration_controller.submit(student_id(), activity_id)
    if result.is_success():
        flash("报名成功" if result.registration.status.value == "APPROVED" else "报名已提交，等待审核", "ok")
    else:
        flash(result.message or result.error_code, "error")
    return redirect(url_for("bp.activity_detail", activity_id=activity_id))


@bp.get("/registrations")
@require("STUDENT")
def my_registrations():
    items = get_ctx().registration_controller.my_registrations(student_id())
    return render_template("my_registrations.html", items=items, status_text=STATUS_TEXT)


@bp.post("/registrations/<registration_id>/cancel")
@require("STUDENT")
def cancel_registration(registration_id):
    check_csrf()
    result = get_ctx().registration_controller.cancel(student_id(), registration_id)
    if result.is_success():
        flash("已取消报名", "ok")
    else:
        flash(result.message or result.error_code, "error")
    return redirect(request.form.get("next") or url_for("bp.my_registrations"))


@bp.get("/notifications")
@require("STUDENT")
def notification_list():
    messages = get_ctx().notification_controller.list(student_id())
    return render_template("notifications.html", messages=messages)


@bp.post("/notifications/<message_id>/read")
@require("STUDENT")
def notification_read(message_id):
    check_csrf()
    try:
        get_ctx().notification_controller.mark_read(student_id(), message_id)
    except NotFoundError:
        abort(404, "消息不存在")
    return redirect(url_for("bp.notification_list"))


# ---------------- 管理端 ----------------

@bp.get("/admin/activities")
@require("ADMIN")
def admin_activity_list():
    summaries = get_ctx().activity_controller.list("")
    return render_template("admin_activity_list.html", summaries=summaries,
                           status_text=STATUS_TEXT)


@bp.route("/admin/activities/new", methods=["GET", "POST"])
@require("ADMIN")
def admin_activity_new():
    ctx = get_ctx()
    if request.method == "POST":
        check_csrf()
        activity, error = activity_from_form()
        if error:
            flash(error, "error")
            return render_template("admin_activity_form.html", activity=activity, error=error,
                                   is_edit=False), 400
        activity.activity_id = new_id("act")
        result = ctx.activity_controller.create(ADMIN_ID, activity)
        if result.is_success():
            flash("创建成功", "ok")
            return redirect(url_for("bp.admin_activity_list"))
        flash(result.message or result.error_code, "error")
        return render_template("admin_activity_form.html", activity=activity, error=result.message,
                               is_edit=False), 400
    return render_template("admin_activity_form.html", activity=None, error=None,
                           is_edit=False)


@bp.route("/admin/activities/<activity_id>/edit", methods=["GET", "POST"])
@require("ADMIN")
def admin_activity_edit(activity_id):
    ctx = get_ctx()
    existing = ctx.activity_controller.get(activity_id)
    if existing is None:
        abort(404, "活动不存在或已被删除")
    if request.method == "POST":
        check_csrf()
        activity, error = activity_from_form()
        if error:
            flash(error, "error")
            return render_template("admin_activity_form.html", activity=activity, error=error,
                                   is_edit=True), 400
        result = ctx.activity_controller.update(ADMIN_ID, activity_id, activity)
        if result.is_success():
            flash("保存成功", "ok")
            return redirect(url_for("bp.admin_activity_list"))
        flash(result.message or result.error_code, "error")
        return render_template("admin_activity_form.html", activity=activity, error=result.message,
                               is_edit=True), 400
    return render_template("admin_activity_form.html", activity=existing, error=None,
                           is_edit=True)


@bp.post("/admin/activities/<activity_id>/delete")
@require("ADMIN")
def admin_activity_delete(activity_id):
    check_csrf()
    result = get_ctx().activity_controller.delete(ADMIN_ID, activity_id)
    flash(result.message if result.message else ("删除成功" if result.is_success() else result.error_code),
          "ok" if result.is_success() else "error")
    return redirect(url_for("bp.admin_activity_list"))


@bp.get("/admin/activities/<activity_id>/approvals")
@require("ADMIN")
def admin_approvals(activity_id):
    try:
        items = get_ctx().approval_controller.pending_list(ADMIN_ID, activity_id)
    except NotFoundError:
        abort(404, "活动不存在或已被删除")
    activity = get_ctx().activity_controller.get(activity_id)
    return render_template("admin_approvals.html", items=items, activity=activity,
                           status_text=STATUS_TEXT)


@bp.post("/admin/registrations/<registration_id>/approve")
@require("ADMIN")
def admin_approve(registration_id):
    check_csrf()
    result = get_ctx().approval_controller.approve(ADMIN_ID, registration_id)
    flash(result.message if not result.is_success() else "已批准", "ok" if result.is_success() else "error")
    activity_id = result.registration.activity_id if result.registration else request.form.get("activity_id", "")
    return redirect(url_for("bp.admin_approvals", activity_id=activity_id) if activity_id
                    else url_for("bp.admin_activity_list"))


@bp.post("/admin/registrations/<registration_id>/reject")
@require("ADMIN")
def admin_reject(registration_id):
    check_csrf()
    reason = request.form.get("reason", "").strip()
    result = get_ctx().approval_controller.reject(ADMIN_ID, registration_id, reason)
    flash(result.message if not result.is_success() else "已拒绝", "ok" if result.is_success() else "error")
    activity_id = result.registration.activity_id if result.registration else request.form.get("activity_id", "")
    return redirect(url_for("bp.admin_approvals", activity_id=activity_id) if activity_id
                    else url_for("bp.admin_activity_list"))


@bp.get("/admin/activities/<activity_id>/statistics")
@require("ADMIN")
def admin_statistics(activity_id):
    try:
        stats = get_ctx().statistics_controller.view(ADMIN_ID, activity_id)
    except NotFoundError:
        abort(404, "活动不存在或已被删除")
    return render_template("admin_statistics.html", stats=stats)


# ---------------- 表单辅助 ----------------

def activity_from_form():
    """把表单解析成 Activity；解析失败返回错误信息（不写库）。"""
    from ..domain.entities import Activity

    form = request.form
    title = form.get("title", "").strip()
    category = form.get("category", "").strip()
    start_at = form.get("start_at", "").strip()
    location = form.get("location", "").strip()
    capacity_raw = form.get("capacity", "").strip()
    policy_raw = form.get("policy_type", "").strip()

    error = ""
    if start_at:
        try:
            from ..application.services import normalize_start_at

            start_at = normalize_start_at(start_at)
        except ValueError:
            error = "开始时间格式错误"

    try:
        capacity = int(capacity_raw)
    except ValueError:
        capacity = 0
    try:
        policy_type = PolicyType(policy_raw)
    except ValueError:
        policy_type = None

    activity = Activity(
        activity_id="",
        title=title,
        category=category,
        start_at=start_at,
        location=location,
        capacity=capacity,
        policy_type=policy_type,
    )
    if policy_type is None and not error:
        error = "报名方式配置错误"
    return activity, error
