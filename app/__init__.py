"""Flask 应用工厂与组合根装配。"""
from __future__ import annotations

from flask import Flask

from .composition import DEFAULT_DB_PATH, DEFAULT_FAILURE_LOG, AppContext
from .ui.routes import bp, csrf_token


def create_app(db_path: str = DEFAULT_DB_PATH,
               failure_log_path: str = DEFAULT_FAILURE_LOG,
               testing: bool = False,
               extra_policies=None,
               policy_types=None) -> Flask:
    app = Flask(__name__, template_folder="ui/templates")
    app.config["SECRET_KEY"] = "dev-campus-event-2026"
    app.config["TESTING"] = testing
    app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024

    ctx = AppContext(
        db_path=db_path,
        failure_log_path=failure_log_path,
        extra_policies=extra_policies,
        policy_types=policy_types,
    )
    app.extensions["ctx"] = ctx

    app.register_blueprint(bp)
    app.context_processor(lambda: {"csrf_token": csrf_token})

    @app.teardown_appcontext
    def _close_connections(exception=None):
        ctx.close()

    return app
