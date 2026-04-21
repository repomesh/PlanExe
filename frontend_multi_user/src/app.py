"""
Flask UI for PlanExe-server.

PROMPT> python3 -m src.app
"""
from datetime import datetime, UTC
from decimal import Decimal
import logging
import os
import sys
import time
import json
import uuid
import hashlib
import secrets
from urllib.parse import quote_plus, urlparse
from typing import Dict, Optional, Tuple, Any, cast
from types import SimpleNamespace
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, session, abort
from flask_admin import Admin, AdminIndexView, expose
from flask_login import LoginManager, UserMixin, login_user, login_required, current_user
from authlib.integrations.flask_client import OAuth
from flask_wtf.csrf import CSRFProtect
from functools import wraps
import urllib.request
from urllib.error import URLError
from flask import make_response
from worker_plan_api.start_time import StartTime
from worker_plan_api.plan_file import PlanFile
from worker_plan_api.filenames import FilenameEnum
from worker_plan_api.prompt_catalog import PromptCatalog
from sqlalchemy import text, inspect, func
from sqlalchemy.exc import OperationalError, DataError
from database_api.model_planitem import PlanItem, PlanState
from database_api.model_event import EventType, EventItem
from database_api.model_worker import WorkerItem
from database_api.model_nonce import NonceItem
from database_api.model_user_account import UserAccount
from database_api.model_user_provider import UserProvider
from database_api.model_user_api_key import UserApiKey
from database_api.model_credit_history import CreditHistory
from database_api.model_payment_record import PaymentRecord
from database_api.model_token_metrics import TokenMetrics, TokenMetricsSummary
from database_api.model_feedback import FeedbackItem
from planexe_modelviews import WorkerItemView, PlanItemView, NonceItemView, TokenMetricsView, AdminOnlyModelView, UserAccountView
logger = logging.getLogger(__name__)

from worker_plan_api.planexe_dotenv import DotEnvKeyEnum, PlanExeDotEnv
from worker_plan_api.planexe_config import PlanExeConfig
from worker_plan_api.model_profile import ModelProfileEnum, normalize_model_profile
from worker_plan_api.pipeline_version import PIPELINE_VERSION
from worker_plan_api.llm_class_filter import (
    ENV_PLANEXE_LLM_CONFIG_WHITELISTED_CLASSES,
    is_llm_class_allowed,
    parse_llm_class_whitelist,
)

from src.utils import CREDIT_SCALE, to_credit_decimal, format_credit_display

DEMO_FORM_RUN_PROMPT_UUIDS = [
    "ab700769-c3ba-4f8a-913d-8589fea4624e",
    "00e1c738-a663-476a-b950-62785922f6f0",
    "e6ddd953-939f-4d15-89ec-fd3988f79123"
]

AUTH_PROVIDER_LABELS = {
    "google": "Google",
    "github": "GitHub",
    "discord": "Discord",
    "password": "Password",
    "telegram": "Telegram",
    "open_access": "Open access",
}


def _new_model(model_cls: Any, **kwargs: Any) -> Any:
    """Instantiate ORM models through Any to accommodate dynamic Flask-SQLAlchemy typing."""
    return cast(Any, model_cls)(**kwargs)

def build_postgres_uri_from_env(env: Dict[str, str]) -> Tuple[str, Dict[str, str]]:
    """Construct a SQLAlchemy URI for Postgres using environment variables."""
    host = env.get("PLANEXE_FRONTEND_MULTIUSER_DB_HOST") or env.get("PLANEXE_POSTGRES_HOST") or "database_postgres"
    port = str(env.get("PLANEXE_FRONTEND_MULTIUSER_DB_PORT") or env.get("PLANEXE_POSTGRES_PORT") or "5432")
    dbname = env.get("PLANEXE_FRONTEND_MULTIUSER_DB_NAME") or env.get("PLANEXE_POSTGRES_DB") or "planexe"
    user = env.get("PLANEXE_FRONTEND_MULTIUSER_DB_USER") or env.get("PLANEXE_POSTGRES_USER") or "planexe"
    password = env.get("PLANEXE_FRONTEND_MULTIUSER_DB_PASSWORD") or env.get("PLANEXE_POSTGRES_PASSWORD") or "planexe"
    uri = f"postgresql+psycopg2://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{dbname}"
    safe_config = {"host": host, "port": port, "dbname": dbname, "user": user}
    return uri, safe_config

class User(UserMixin):
    def __init__(self, user_id: str, is_admin: bool = False):
        self.id = str(user_id)
        self.is_admin = is_admin

class MyAdminIndexView(AdminIndexView):
    @expose('/')
    def index(self) -> Any:
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        if not current_user.is_admin:
            abort(403)
        return super(MyAdminIndexView, self).index()

    def is_accessible(self):
        return current_user.is_authenticated and getattr(current_user, "is_admin", False)

    def inaccessible_callback(self, name, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        abort(403)

def nocache(view):
    """Decorator to add 'no-cache' headers to a response."""
    @wraps(view)
    def no_cache_view(*args, **kwargs):
        # Call the original view function
        response = make_response(view(*args, **kwargs))
        # Modify headers
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '-1' # Or any date in the past, or 0
        return response
    return no_cache_view

def admin_required(view):
    """Decorator that requires an authenticated admin user."""
    @wraps(view)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapper


def _profile_model_rows_map() -> Dict[str, list[dict[str, str]]]:
    whitelist = parse_llm_class_whitelist(os.environ.get(ENV_PLANEXE_LLM_CONFIG_WHITELISTED_CLASSES))
    profile_to_models: Dict[str, list[dict[str, str]]] = {}
    for profile in ModelProfileEnum:
        config = PlanExeConfig.load(model_profile_override=profile)
        config_path = config.llm_config_json_path
        if config_path is None:
            profile_to_models[profile.value] = []
            continue
        try:
            with config_path.open("r", encoding="utf-8") as fh:
                model_map = json.load(fh)
        except Exception:
            profile_to_models[profile.value] = []
            continue
        if not isinstance(model_map, dict):
            profile_to_models[profile.value] = []
            continue

        def sort_key(item: tuple[str, dict]) -> tuple[int, str]:
            data = item[1] if isinstance(item[1], dict) else {}
            priority = data.get("priority")
            if not isinstance(priority, int):
                priority = 999999
            return priority, item[0]

        rows: list[dict[str, str]] = []
        for model_key, model_data in sorted(model_map.items(), key=sort_key):
            class_name = model_data.get("class") if isinstance(model_data, dict) else None
            if not is_llm_class_allowed(class_name, whitelist):
                continue
            model_name = ""
            comment = ""
            prio = ""
            model_info_url = ""
            pricing_kind = ""
            if isinstance(model_data, dict):
                args = model_data.get("arguments")
                if isinstance(args, dict) and isinstance(args.get("model"), str):
                    model_name = args["model"]
                if isinstance(model_data.get("comment"), str):
                    comment = model_data["comment"]
                if isinstance(model_data.get("prio"), int):
                    prio = str(model_data["prio"])
                elif isinstance(model_data.get("priority"), int):
                    prio = str(model_data["priority"])
                if isinstance(model_data.get("model_info_url"), str):
                    model_info_url = model_data["model_info_url"]
                if isinstance(model_data.get("pricing_kind"), str):
                    pricing_kind = model_data["pricing_kind"]
            rows.append(
                {
                    "key": model_key,
                    "prio": prio,
                    "pricing_kind": pricing_kind,
                    "model": model_name,
                    "comment": comment,
                    "model_info_url": model_info_url,
                }
            )
        profile_to_models[profile.value] = rows
    return profile_to_models


def _model_profile_options() -> list[dict[str, str]]:
    return [
        {
            "value": ModelProfileEnum.BASELINE.value,
            "title": "Baseline",
            "subtitle": "Cheap and fast.",
        },
        {
            "value": ModelProfileEnum.PREMIUM.value,
            "title": "Premium",
            "subtitle": "Expensive, slow, high quality.",
        },
        {
            "value": ModelProfileEnum.FRONTIER.value,
            "title": "Frontier",
            "subtitle": "Most capable models first.",
        },
        {
            "value": ModelProfileEnum.CUSTOM.value,
            "title": "Custom",
            "subtitle": "Use your own config file.",
        },
    ]

class MyFlaskApp:
    def __init__(self):
        logger.info(f"MyFlaskApp.__init__. Starting...")

        self.planexe_config = PlanExeConfig.load()
        logger.info(f"MyFlaskApp.__init__. planexe_config: {self.planexe_config!r}")

        self.planexe_dotenv = PlanExeDotEnv.load()
        logger.info(f"MyFlaskApp.__init__. planexe_dotenv: {self.planexe_dotenv!r}")

        # This is a workaround to fix the inconsistency.
        # Workaround-problem: When the Flask app launches in debug mode it runs __init__ twice, so that the app can hot reload.
        # However there is this inconsistency.
        # 1st time, the os.environ is the original environment of the shell.
        # 2nd time, the os.environ is the original environment of the shell + the .env content.
        # If it was the same in both cases, it would be easier to reason about the environment variables.
        # On following hot reloads, the os.environ continues to be the original environment of the shell + the .env content.
        # Workaround-solution: Every time update the os.environ with the .env content, so that the os.environ is always the
        # original environment of the shell + the .env content.
        # I prefer NEVER to modify the os.environ for the current process, and instead spawn a child process with the modified os.environ.
        self.planexe_dotenv.update_os_environ()

        self.admin_username = (self.planexe_dotenv.get("PLANEXE_FRONTEND_MULTIUSER_ADMIN_USERNAME") or "").strip()
        self.admin_password = (self.planexe_dotenv.get("PLANEXE_FRONTEND_MULTIUSER_ADMIN_PASSWORD") or "").strip()
        if not self.admin_username or not self.admin_password:
            raise ValueError("Admin credentials must be set via PLANEXE_FRONTEND_MULTIUSER_ADMIN_USERNAME and PLANEXE_FRONTEND_MULTIUSER_ADMIN_PASSWORD.")
        if self.admin_username == "admin" and self.admin_password == "admin":
            logger.warning("Admin credentials are set to the default admin/admin; set PLANEXE_FRONTEND_MULTIUSER_ADMIN_USERNAME/PLANEXE_FRONTEND_MULTIUSER_ADMIN_PASSWORD to unique values.")
        else:
            logger.info("Admin credentials loaded from PLANEXE_FRONTEND_MULTIUSER_ADMIN_USERNAME/PLANEXE_FRONTEND_MULTIUSER_ADMIN_PASSWORD.")

        override_path_to_python = self.planexe_dotenv.get_absolute_path_to_file(DotEnvKeyEnum.PATH_TO_PYTHON.value)
        if isinstance(override_path_to_python, Path):
            debug_path_to_python = 'override'
            self.path_to_python = override_path_to_python
        else:
            debug_path_to_python = 'default'
            self.path_to_python = Path(sys.executable)
        logger.info(f"MyFlaskApp.__init__. path_to_python ({debug_path_to_python}): {self.path_to_python!r}")

        self.planexe_project_root = Path(__file__).parent.parent.parent.absolute()
        logger.info(f"MyFlaskApp.__init__. planexe_project_root: {self.planexe_project_root!r}")

        self.worker_plan_url = (os.environ.get("PLANEXE_WORKER_PLAN_URL") or "http://worker_plan:8000").rstrip("/")
        logger.info(f"MyFlaskApp.__init__. worker_plan_url: {self.worker_plan_url}")

        self._start_check()

        # Load prompt catalog and examples.
        self.prompt_catalog = PromptCatalog()
        self.prompt_catalog.load_simple_plan_prompts()

        # Lightweight in-process cache for terminal task telemetry snapshots.
        # This avoids repeatedly re-querying/re-parsing run artifacts when the
        # plan iframe polls /plan/meta after a task is already finished.
        self._plan_telemetry_cache: dict[tuple[str, str, bool], dict[str, Any]] = {}

        # Point to the "templates" dir.
        # Prefer top-level templates dir (frontend_multi_user/templates) when running from Docker image.
        default_template_folder = Path(__file__).parent / "templates"
        alt_template_folder = Path(__file__).parent.parent / "templates"
        template_folder = default_template_folder if default_template_folder.exists() else alt_template_folder
        logger.info(f"MyFlaskApp.__init__. template_folder: {template_folder!r}")
        self.app = Flask(__name__, template_folder=str(template_folder))

        # Load configuration from config.py when present; otherwise use safe defaults.
        config_path = Path(__file__).with_name("config.py")
        if config_path.exists():
            logger.info("Loading Flask config from %s", config_path)
            self.app.config.from_pyfile(str(config_path))
        else:
            logger.warning("Config file not found at %s; using fallback settings.", config_path)
            self.app.config.from_mapping(
                SECRET_KEY=os.environ.get("PLANEXE_FRONTEND_MULTIUSER_SECRET_KEY", "dev-secret-key"),
                SQLALCHEMY_TRACK_MODIFICATIONS=False,
            )

        # Env overrides: production sets PLANEXE_FRONTEND_MULTIUSER_SECRET_KEY; honor it over config.py
        env_secret = os.environ.get("PLANEXE_FRONTEND_MULTIUSER_SECRET_KEY")
        if env_secret:
            self.app.config["SECRET_KEY"] = env_secret

        _public_url = os.environ.get("PLANEXE_FRONTEND_MULTIUSER_PUBLIC_URL", "").strip()
        if not _public_url:
            _public_url = "http://localhost:5001"
            logger.info("PLANEXE_FRONTEND_MULTIUSER_PUBLIC_URL not set; defaulting to %s", _public_url)
        self.public_base_url = _public_url.rstrip("/")

        # Validate SECRET_KEY - check for both default values
        secret_key = self.app.config.get("SECRET_KEY")
        is_default_key = secret_key in ("dev-secret-key", "your-secret-key", None)
        is_production = os.environ.get("FLASK_ENV") == "production" or self._looks_like_production_url(self.public_base_url)

        if is_default_key:
            if is_production:
                raise ValueError(
                    "Cannot use default SECRET_KEY in production. "
                    "Set PLANEXE_FRONTEND_MULTIUSER_SECRET_KEY environment variable. "
                    "Generate with: python -c 'import secrets; print(secrets.token_hex(32))'"
                )
            logger.warning(
                "Using default Flask SECRET_KEY (%s). "
                "Set PLANEXE_FRONTEND_MULTIUSER_SECRET_KEY for production.",
                secret_key
            )

        # Session cookie security settings
        self.app.config.setdefault('SESSION_COOKIE_SECURE', is_production)
        self.app.config.setdefault('SESSION_COOKIE_HTTPONLY', True)
        self.app.config.setdefault('SESSION_COOKIE_SAMESITE', 'Lax')
        logger.info(f"Session cookie security: secure={is_production}, httponly=True, samesite=Lax")

        if self.public_base_url.lower().startswith("https://"):
            self.app.config["SESSION_COOKIE_SECURE"] = True
            self.app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

        # Enable CSRF protection
        self.csrf = CSRFProtect(self.app)
        logger.info("CSRF protection enabled")

        self.oauth = OAuth(self.app)
        self._register_oauth_providers()

        # Determine open access mode (no login required).
        # When no OAuth providers are configured and PLANEXE_AUTH_REQUIRED is not
        # explicitly true, the app auto-logins every request as admin so Docker
        # localhost users can create plans without setting up Google Console, etc.
        self.open_access = self._determine_open_access()
        self._api_key_show_once = os.environ.get("PLANEXE_API_KEY_SHOW_ONCE", "").strip().lower() in ("1", "true", "yes")

        db_settings: Dict[str, str] = {}
        sqlalchemy_database_uri = self.planexe_dotenv.get("SQLALCHEMY_DATABASE_URI")
        if sqlalchemy_database_uri is None:
            sqlalchemy_database_uri, db_settings = build_postgres_uri_from_env(self.planexe_dotenv.dotenv_dict)
            logger.info(
                "Using Postgres defaults for SQLAlchemy: %(host)s:%(port)s/%(dbname)s user=%(user)s",
                db_settings
            )
        else:
            logger.info("Using SQLALCHEMY_DATABASE_URI from environment or .env file.")

        self.app.config['SQLALCHEMY_DATABASE_URI'] = sqlalchemy_database_uri
        self.app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_recycle': 280, 'pool_pre_ping': True}
        self.database_settings = db_settings if db_settings else {"uri_source": "SQLALCHEMY_DATABASE_URI"}

        # Initialize database
        from database_api.planexe_db_singleton import db
        self.db = db
        self.db.init_app(self.app)

        def _ensure_plans_table_name() -> None:
            """Rename legacy 'task_item' (and its indexes) to 'plans' (idempotent).

            Serialized via a Postgres advisory lock so concurrent replicas do not
            race. Must run before db.create_all() so SQLAlchemy does not create
            a second empty 'plans' table alongside 'task_item'.
            """
            sql = """
            DO $$
            BEGIN
                PERFORM pg_advisory_xact_lock(8462357421);
                IF EXISTS (SELECT 1 FROM information_schema.tables
                           WHERE table_schema = current_schema() AND table_name = 'task_item')
                   AND NOT EXISTS (SELECT 1 FROM information_schema.tables
                                   WHERE table_schema = current_schema() AND table_name = 'plans') THEN
                    ALTER TABLE task_item RENAME TO plans;
                END IF;
                IF EXISTS (SELECT 1 FROM pg_indexes
                           WHERE schemaname = current_schema() AND indexname = 'idx_task_item_user_id_timestamp_created') THEN
                    ALTER INDEX idx_task_item_user_id_timestamp_created RENAME TO idx_plans_user_id_timestamp_created;
                END IF;
                IF EXISTS (SELECT 1 FROM pg_indexes
                           WHERE schemaname = current_schema() AND indexname = 'idx_task_item_api_key_id') THEN
                    ALTER INDEX idx_task_item_api_key_id RENAME TO idx_plans_api_key_id;
                END IF;
            END$$;
            """
            try:
                with self.db.engine.begin() as conn:
                    conn.execute(text(sql))
            except Exception as exc:
                logger.warning("Rename task_item -> plans failed: %s", exc, exc_info=True)

        def _ensure_planitem_artifact_columns() -> None:
            insp = inspect(self.db.engine)
            columns = {col["name"] for col in insp.get_columns("plans")}
            with self.db.engine.begin() as conn:
                if "generated_report_html" not in columns:
                    conn.execute(text("ALTER TABLE plans ADD COLUMN IF NOT EXISTS generated_report_html TEXT"))
                if "run_zip_snapshot" not in columns:
                    conn.execute(text("ALTER TABLE plans ADD COLUMN IF NOT EXISTS run_zip_snapshot BYTEA"))
                if "run_track_activity_jsonl" not in columns:
                    conn.execute(text("ALTER TABLE plans ADD COLUMN IF NOT EXISTS run_track_activity_jsonl TEXT"))
                if "run_track_activity_bytes" not in columns:
                    conn.execute(text("ALTER TABLE plans ADD COLUMN IF NOT EXISTS run_track_activity_bytes INTEGER"))
                if "run_activity_overview_json" not in columns:
                    conn.execute(text("ALTER TABLE plans ADD COLUMN IF NOT EXISTS run_activity_overview_json JSON"))
                if "run_artifact_layout_version" not in columns:
                    conn.execute(text("ALTER TABLE plans ADD COLUMN IF NOT EXISTS run_artifact_layout_version INTEGER"))
                if "stop_requested" not in columns:
                    conn.execute(text("ALTER TABLE plans ADD COLUMN IF NOT EXISTS stop_requested BOOLEAN"))
                if "stop_requested_timestamp" not in columns:
                    conn.execute(text("ALTER TABLE plans ADD COLUMN IF NOT EXISTS stop_requested_timestamp TIMESTAMP"))

        def _ensure_token_metrics_columns() -> None:
            insp = inspect(self.db.engine)
            if "token_metrics" not in insp.get_table_names():
                return
            columns = {col["name"] for col in insp.get_columns("token_metrics")}
            with self.db.engine.begin() as conn:
                # Remove legacy identifiers. Token metrics should reference tasks only.
                if "run_id" in columns:
                    conn.execute(text("ALTER TABLE token_metrics DROP COLUMN IF EXISTS run_id"))
                if "task_name" in columns:
                    conn.execute(text("ALTER TABLE token_metrics DROP COLUMN IF EXISTS task_name"))
                if "task_id" not in columns:
                    conn.execute(text("ALTER TABLE token_metrics ADD COLUMN IF NOT EXISTS task_id VARCHAR(255)"))
                if "user_id" not in columns:
                    conn.execute(text("ALTER TABLE token_metrics ADD COLUMN IF NOT EXISTS user_id VARCHAR(255)"))
                if "upstream_provider" not in columns:
                    conn.execute(text("ALTER TABLE token_metrics ADD COLUMN IF NOT EXISTS upstream_provider VARCHAR(255)"))
                if "upstream_model" not in columns:
                    conn.execute(text("ALTER TABLE token_metrics ADD COLUMN IF NOT EXISTS upstream_model VARCHAR(255)"))
                if "cost_usd" not in columns:
                    conn.execute(text("ALTER TABLE token_metrics ADD COLUMN IF NOT EXISTS cost_usd DOUBLE PRECISION"))

        def _ensure_fractional_credit_columns() -> None:
            if self.db.engine.dialect.name != "postgresql":
                return
            insp = inspect(self.db.engine)
            table_names = set(insp.get_table_names())
            with self.db.engine.begin() as conn:
                if "user_account" in table_names:
                    conn.execute(text(
                        "ALTER TABLE user_account "
                        "ALTER COLUMN credits_balance TYPE NUMERIC(18,9) "
                        "USING credits_balance::NUMERIC(18,9)"
                    ))
                    conn.execute(text("ALTER TABLE user_account ALTER COLUMN credits_balance SET DEFAULT 0"))
                if "credit_history" in table_names:
                    conn.execute(text(
                        "ALTER TABLE credit_history "
                        "ALTER COLUMN delta TYPE NUMERIC(18,9) "
                        "USING delta::NUMERIC(18,9)"
                    ))
                if "payment_record" in table_names:
                    conn.execute(text(
                        "ALTER TABLE payment_record "
                        "ALTER COLUMN credits TYPE NUMERIC(18,9) "
                        "USING credits::NUMERIC(18,9)"
                    ))

        def _ensure_user_account_columns() -> None:
            insp = inspect(self.db.engine)
            if "user_account" not in set(insp.get_table_names()):
                return
            columns = {col["name"] for col in insp.get_columns("user_account")}
            with self.db.engine.begin() as conn:
                if "frontend_multi_user_config" not in columns:
                    conn.execute(text("ALTER TABLE user_account ADD COLUMN IF NOT EXISTS frontend_multi_user_config JSON"))

        def _ensure_multi_api_key_columns() -> None:
            """Add columns for multi-API-key support (idempotent).

            Each ALTER runs in its own transaction so one failure does not
            poison the rest (PostgreSQL aborts the entire transaction on error).
            """
            statements = (
                "ALTER TABLE user_api_key ADD COLUMN IF NOT EXISTS label VARCHAR(128)",
                "ALTER TABLE user_api_key ADD COLUMN IF NOT EXISTS key_plaintext VARCHAR(64)",
                "ALTER TABLE plans ADD COLUMN IF NOT EXISTS api_key_id VARCHAR(36)",
                "ALTER TABLE credit_history ADD COLUMN IF NOT EXISTS api_key_id VARCHAR(36)",
                "ALTER TABLE token_metrics ADD COLUMN IF NOT EXISTS api_key_id VARCHAR(36)",
            )
            for stmt in statements:
                try:
                    with self.db.engine.begin() as conn:
                        conn.execute(text(stmt))
                except Exception as exc:
                    logger.warning("Schema update failed for %s: %s", stmt, exc, exc_info=True)

        def _ensure_step_count_columns() -> None:
            insp = inspect(self.db.engine)
            columns = {col["name"] for col in insp.get_columns("plans")}
            with self.db.engine.begin() as conn:
                if "steps_completed" not in columns:
                    conn.execute(text("ALTER TABLE plans ADD COLUMN IF NOT EXISTS steps_completed INTEGER"))
                if "steps_total" not in columns:
                    conn.execute(text("ALTER TABLE plans ADD COLUMN IF NOT EXISTS steps_total INTEGER"))
                if "current_step" not in columns:
                    conn.execute(text("ALTER TABLE plans ADD COLUMN IF NOT EXISTS current_step VARCHAR(128)"))

        def _ensure_failure_diagnostic_columns() -> None:
            insp = inspect(self.db.engine)
            columns = {col["name"] for col in insp.get_columns("plans")}
            with self.db.engine.begin() as conn:
                if "failure_reason" not in columns:
                    conn.execute(text("ALTER TABLE plans ADD COLUMN IF NOT EXISTS failure_reason VARCHAR(64)"))
                if "failed_step" not in columns:
                    conn.execute(text("ALTER TABLE plans ADD COLUMN IF NOT EXISTS failed_step VARCHAR(128)"))
                if "recoverable" not in columns:
                    conn.execute(text("ALTER TABLE plans ADD COLUMN IF NOT EXISTS recoverable BOOLEAN"))
            # Rename last_error -> error_message in a separate transaction so a
            # failed RENAME (race with another container) doesn't poison the above.
            if "error_message" not in columns:
                if "last_error" in columns:
                    try:
                        with self.db.engine.begin() as conn:
                            conn.execute(text("ALTER TABLE plans RENAME COLUMN last_error TO error_message"))
                    except Exception:
                        with self.db.engine.begin() as conn:
                            conn.execute(text("ALTER TABLE plans ADD COLUMN IF NOT EXISTS error_message VARCHAR(256)"))
                else:
                    with self.db.engine.begin() as conn:
                        conn.execute(text("ALTER TABLE plans ADD COLUMN IF NOT EXISTS error_message VARCHAR(256)"))

        def _ensure_stopped_state() -> None:
            """Add 'stopped' value to the planstate/taskstate enum type (idempotent).

            The PostgreSQL enum type is named ``taskstate`` in databases
            created before the TaskState -> PlanState Python rename
            (proposal 74).  Fresh databases will have ``planstate``.
            We try both names.

            Each ALTER TYPE runs in its own transaction so a failure for
            one enum name does not poison the attempt for the other.
            """
            for type_name in ("taskstate", "planstate"):
                for enum_value in ("stopped",):
                    try:
                        with self.db.engine.begin() as conn:
                            conn.execute(text(f"ALTER TYPE {type_name} ADD VALUE IF NOT EXISTS '{enum_value}'"))
                    except Exception as exc:
                        logger.debug("ALTER TYPE %s ADD VALUE %s: %s", type_name, enum_value, exc)

        def _ensure_last_progress_at_column() -> None:
            insp = inspect(self.db.engine)
            columns = {col["name"] for col in insp.get_columns("plans")}
            if "last_progress_at" not in columns:
                with self.db.engine.begin() as conn:
                    conn.execute(text("ALTER TABLE plans ADD COLUMN IF NOT EXISTS last_progress_at TIMESTAMP"))

        def _ensure_planitem_indexes() -> None:
            insp = inspect(self.db.engine)
            table_names = set(insp.get_table_names())
            statements: list[str] = []
            if "plans" in table_names:
                statements.append(
                    "CREATE INDEX IF NOT EXISTS idx_plans_user_id_timestamp_created "
                    "ON plans (user_id, timestamp_created)"
                )
                statements.append(
                    "CREATE INDEX IF NOT EXISTS idx_plans_api_key_id "
                    "ON plans (api_key_id)"
                )
            if "credit_history" in table_names:
                statements.append(
                    "CREATE INDEX IF NOT EXISTS idx_credit_history_api_key_id "
                    "ON credit_history (api_key_id)"
                )
            for stmt in statements:
                try:
                    with self.db.engine.begin() as conn:
                        conn.execute(text(stmt))
                except Exception as exc:
                    logger.warning("Index creation skipped for %s: %s", stmt, exc)

        def _seed_initial_records() -> None:
            # Add initial records if the table is empty
            if PlanItem.query.count() == 0:
                tasks = PlanItem.demo_items()
                for task in tasks:
                    self.db.session.add(task)
                self.db.session.commit()

            if EventItem.query.count() == 0:
                events = EventItem.demo_items()
                for event in events:
                    self.db.session.add(event)
                self.db.session.commit()

            if NonceItem.query.count() == 0:
                nonce_items = NonceItem.demo_items()
                for nonce_item in nonce_items:
                    self.db.session.add(nonce_item)
                self.db.session.commit()

        # Arbitrary but fixed advisory-lock key used to serialize
        # db.create_all() across concurrent gunicorn workers so they
        # don't race on CREATE TABLE / CREATE TYPE statements.
        _ADVISORY_LOCK_KEY = 820_191_001

        def _create_tables_with_retry(attempts: int = 5, delay_seconds: float = 2.0) -> None:
            last_exc: Optional[Exception] = None
            for attempt in range(1, attempts + 1):
                try:
                    with self.app.app_context():
                        # Acquire a session-level advisory lock so only one
                        # worker runs DDL at a time.  Other workers block
                        # here until the lock is released.
                        with self.db.engine.connect() as lock_conn:
                            lock_conn.execute(text(f"SELECT pg_advisory_lock({_ADVISORY_LOCK_KEY})"))
                            try:
                                _ensure_plans_table_name()
                                self.db.create_all()
                                _ensure_planitem_artifact_columns()
                                _ensure_token_metrics_columns()
                                _ensure_fractional_credit_columns()
                                _ensure_user_account_columns()
                                _ensure_multi_api_key_columns()
                                _ensure_step_count_columns()
                                _ensure_failure_diagnostic_columns()
                                _ensure_stopped_state()
                                _ensure_last_progress_at_column()
                                _ensure_planitem_indexes()
                                _seed_initial_records()
                            finally:
                                lock_conn.execute(text(f"SELECT pg_advisory_unlock({_ADVISORY_LOCK_KEY})"))
                                lock_conn.commit()
                    return
                except OperationalError as exc:
                    last_exc = exc
                    logger.warning(
                        "Database init attempt %s/%s failed: %s. Retrying in %.1fs",
                        attempt,
                        attempts,
                        exc,
                        delay_seconds,
                    )
                    time.sleep(delay_seconds)
                except Exception as exc:  # pragma: no cover - startup guardrail
                    last_exc = exc
                    logger.error(
                        "Unexpected error during database init attempt %s/%s: %s",
                        attempt,
                        attempts,
                        exc,
                        exc_info=True,
                    )
                    time.sleep(delay_seconds)
            if last_exc:
                raise last_exc

        _create_tables_with_retry()

        # Setup Flask-Login
        self.login_manager = LoginManager()
        self.login_manager.init_app(self.app)
        self.login_manager.login_view = cast(Any, 'auth.login')

        @self.login_manager.user_loader
        def load_user(user_id):
            if user_id == self.admin_username:
                return User(user_id, is_admin=True)
            try:
                user_uuid = uuid.UUID(str(user_id))
            except ValueError:
                return None
            user = self.db.session.get(UserAccount, user_uuid)
            if not user:
                return None
            return User(user.id, is_admin=user.is_admin)

        # Setup Flask-Admin
        # Flask-Admin versions bundled in the image don't accept template_mode; stick with defaults.
        self.admin = Admin(self.app, name='PlanExe Admin', index_view=MyAdminIndexView())

        # Add database tables to admin panel
        self.admin.add_view(PlanItemView(model=PlanItem, session=self.db.session, name="Task"))
        self.admin.add_view(AdminOnlyModelView(model=EventItem, session=self.db.session, name="Event"))
        self.admin.add_view(WorkerItemView(model=WorkerItem, session=self.db.session, name="Worker"))
        self.admin.add_view(NonceItemView(model=NonceItem, session=self.db.session, name="Nonce"))
        self.admin.add_view(UserAccountView(model=UserAccount, session=self.db.session, name="User"))
        self.admin.add_view(AdminOnlyModelView(model=UserProvider, session=self.db.session, name="User Provider"))
        self.admin.add_view(AdminOnlyModelView(model=UserApiKey, session=self.db.session, name="User API Key"))
        self.admin.add_view(AdminOnlyModelView(model=CreditHistory, session=self.db.session, name="Credit History"))
        self.admin.add_view(AdminOnlyModelView(model=PaymentRecord, session=self.db.session, name="Payments"))
        self.admin.add_view(TokenMetricsView(model=TokenMetrics, session=self.db.session, name="Token Metrics"))
        self.admin.add_view(AdminOnlyModelView(model=FeedbackItem, session=self.db.session, name="Feedback"))

        # Stash shared state into app.config so blueprints can access it.
        self.app.config['ADMIN_USERNAME'] = self.admin_username
        self.app.config['ADMIN_PASSWORD'] = self.admin_password
        self.app.config['PUBLIC_BASE_URL'] = self.public_base_url
        self.app.config['OAUTH_PROVIDERS'] = self.oauth_providers
        self.app.config['WORKER_PLAN_URL'] = self.worker_plan_url
        self.app.config['PLANEXE_PROJECT_ROOT'] = self.planexe_project_root
        self.app.config['PATH_TO_PYTHON'] = self.path_to_python
        self.app.config['PROMPT_CATALOG'] = self.prompt_catalog
        self.app.config['PLANEXE_CONFIG'] = self.planexe_config
        self.app.config['PLANEXE_DOTENV'] = self.planexe_dotenv
        self.app.config['OPEN_ACCESS'] = self.open_access
        self.app.config['API_KEY_SHOW_ONCE'] = self._api_key_show_once
        self.app.config['PLAN_TELEMETRY_CACHE'] = self._plan_telemetry_cache

        # Register blueprints
        from src.auth import auth_bp
        from src.billing import billing_bp
        from src.admin_routes import admin_routes_bp
        from src.plan_routes import plan_routes_bp
        from src.downloads import downloads_bp

        self.app.register_blueprint(auth_bp)
        self.app.register_blueprint(billing_bp)
        self.app.register_blueprint(admin_routes_bp)
        self.app.register_blueprint(plan_routes_bp)
        self.app.register_blueprint(downloads_bp)

        # Exempt external webhook endpoints from CSRF protection.
        self.csrf.exempt(billing_bp)

        # Exempt /run from CSRF — it uses nonce-based replay protection instead.
        # This allows cross-origin iframe POST from partners (e.g. mach-ai.com).
        run_view = self.app.view_functions.get("plan_routes.run")
        if run_view:
            self.csrf.exempt(run_view)

        self._setup_routes()

        self._track_flask_app_started()

    def _track_flask_app_started(self):
        logger.info(f"MyFlaskApp._track_flask_app_started. Starting...")

        # Determine if this is the main process or reloader process
        is_reloader = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
        is_debug_mode = self.app.debug if hasattr(self, 'app') else True

        event_context = {
            "pid": str(os.getpid()),
            "parent_pid": str(os.getppid()),
            "is_reloader_process": is_reloader,
            "is_debug_mode": is_debug_mode,
            "WERKZEUG_RUN_MAIN": os.environ.get('WERKZEUG_RUN_MAIN', 'not_set'),
            "python_executable": sys.executable,
            "command_line": ' '.join(sys.argv),
            "FLASK_ENV": os.environ.get('FLASK_ENV', 'not_set'),
            "FLASK_DEBUG": os.environ.get('FLASK_DEBUG', 'not_set')
        }

        with self.app.app_context():
            event = _new_model(
                EventItem,
                event_type=EventType.GENERIC_EVENT,
                message="Flask app started",
                context=event_context,
            )
            self.db.session.add(event)
            self.db.session.commit()

        logger.info(f"MyFlaskApp._track_flask_app_started. Logged {event_context!r}")

    def _start_check(self):
        # When the Flask app launches in debug mode it runs __init__ twice, so that the app can hot reload.
        # However there is this inconsistency.
        # 1st time, the os.environ is the original environment of the shell.
        # 2nd time, the os.environ is the original environment of the shell + the .env content.
        # If it was the same in both cases, it would be easier to reason about the environment variables.
        # On following hot reloads, the os.environ continues to be the original environment of the shell + the .env content.
        # Log environment variable names with sensitive values redacted.
        # This lets operators see WHICH vars are set without leaking secrets.
        _sensitive_substrings = ("SECRET", "KEY", "PASSWORD", "TOKEN")
        redacted_env = {
            k: ("***REDACTED***" if any(s in k.upper() for s in _sensitive_substrings) else v)
            for k, v in os.environ.items()
        }
        logger.info(f"MyFlaskApp._start_check. environment variables: {redacted_env}")

        issue_count = 0
        if not self.path_to_python.exists():
            logger.error(f"The python executable does not exist at this point. However the python executable should exist: {self.path_to_python!r}")
            issue_count += 1
        if not self.planexe_project_root.exists():
            logger.error(f"The planexe_project_root does not exist at this point. However the planexe_project_root should exist: {self.planexe_project_root!r}")
            issue_count += 1
        if issue_count > 0:
            raise Exception(f"There are {issue_count} issues with the python executable and project root directory")

    def _fetch_worker_plan_llm_info(self) -> Tuple[Optional[dict], Optional[str]]:
        """
        Fetch LLM configuration info from the worker_plan service.
        Returns a tuple of (payload, error_message).
        """
        url = f"{self.worker_plan_url}/llm-info"
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return payload, None
        except URLError as exc:
            return None, f"Failed to reach worker_plan at {url}: {exc.reason}"
        except Exception as exc:
            return None, f"Error fetching worker_plan llm-info: {exc}"

    @staticmethod
    def _looks_like_production_url(url: str) -> bool:
        """Return True when *url* looks like a real production deployment.

        Plain ``http://localhost`` / ``http://127.0.0.1`` URLs are treated as
        development so that local Docker users don't need to set a dedicated
        SECRET_KEY or deal with ``SESSION_COOKIE_SECURE`` over plain HTTP.
        """
        if not url:
            return False
        parsed = urlparse(url.lower())
        if parsed.scheme == "https":
            return True
        # http:// to localhost / loopback is clearly dev
        if parsed.hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
            return False
        # Any other host over http is still likely a real deployment
        return True

    def _register_oauth_providers(self) -> None:
        providers = {
            "google": {
                "client_id": os.environ.get("PLANEXE_OAUTH_GOOGLE_CLIENT_ID"),
                "client_secret": os.environ.get("PLANEXE_OAUTH_GOOGLE_CLIENT_SECRET"),
                "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration",
                "client_kwargs": {"scope": "openid email profile"},
            },
            "github": {
                "client_id": os.environ.get("PLANEXE_OAUTH_GITHUB_CLIENT_ID"),
                "client_secret": os.environ.get("PLANEXE_OAUTH_GITHUB_CLIENT_SECRET"),
                "authorize_url": "https://github.com/login/oauth/authorize",
                "access_token_url": "https://github.com/login/oauth/access_token",
                "api_base_url": "https://api.github.com/",
                "client_kwargs": {"scope": "read:user user:email"},
            },
            "discord": {
                "client_id": os.environ.get("PLANEXE_OAUTH_DISCORD_CLIENT_ID"),
                "client_secret": os.environ.get("PLANEXE_OAUTH_DISCORD_CLIENT_SECRET"),
                "authorize_url": "https://discord.com/oauth2/authorize",
                "access_token_url": "https://discord.com/api/oauth2/token",
                "api_base_url": "https://discord.com/api/",
                "client_kwargs": {"scope": "identify email"},
            },
        }

        self.oauth_providers: list[str] = []
        for name, config in providers.items():
            if not config["client_id"] or not config["client_secret"]:
                continue
            reg_config = dict(config)
            if name == "google":
                reg_config["redirect_uri"] = self._oauth_redirect_url("google")
            self.oauth.register(name=name, **reg_config)
            self.oauth_providers.append(name)

        if not self.oauth_providers:
            logger.warning("No OAuth providers configured. Set PLANEXE_OAUTH_* env vars to enable OAuth login.")

    def _determine_open_access(self) -> bool:
        """Check if the app should run in open access mode (no login required).

        Open access is enabled when no OAuth providers are configured and
        ``PLANEXE_AUTH_REQUIRED`` is not explicitly set to ``true``.
        This lets Docker-on-localhost users create plans immediately after
        ``docker compose up`` without setting up Google Console or any other
        OAuth provider.

        To force login even without OAuth (e.g. admin-only access via
        username/password), set ``PLANEXE_AUTH_REQUIRED=true``.
        """
        env_val = os.environ.get("PLANEXE_AUTH_REQUIRED", "").strip().lower()
        if env_val in ("1", "true", "yes"):
            if not self.oauth_providers:
                raise ValueError(
                    "PLANEXE_AUTH_REQUIRED=true but no OAuth providers are configured. "
                    "Either set PLANEXE_OAUTH_* env vars (Google / GitHub / Discord) "
                    "or remove PLANEXE_AUTH_REQUIRED to use open access mode."
                )
            logger.info(
                "Authentication required (PLANEXE_AUTH_REQUIRED=true). "
                "%d OAuth provider(s) configured.",
                len(self.oauth_providers),
            )
            return False
        if env_val in ("0", "false", "no"):
            logger.info("Open access mode forced via PLANEXE_AUTH_REQUIRED=false.")
            return True
        # Auto-detect: open access when no OAuth providers are configured.
        if not self.oauth_providers:
            logger.info(
                "Open access mode: no OAuth providers configured, login not required. "
                "Set PLANEXE_AUTH_REQUIRED=true to enforce login."
            )
            return True
        logger.info(
            "Authentication required. %d OAuth provider(s) configured.",
            len(self.oauth_providers),
        )
        return False

    def _oauth_redirect_url(self, provider: str) -> str:
        return f"{self.public_base_url}/auth/{provider}/callback"

    def _setup_routes(self):
        # Import helpers from extracted modules for use in /account route.
        from src.auth import get_or_create_api_key, _auth_provider_label
        from src.billing import _record_event, _finalize_stripe_checkout_session
        from src.plan_routes import _get_current_user_account, _admin_user_ids

        @self.app.before_request
        def _auto_login_open_access():
            """In open access mode, auto-login as admin so @login_required routes work."""
            if self.open_access and not current_user.is_authenticated and not session.get("open_access_logged_out"):
                session["auth_provider"] = "open_access"
                login_user(User(self.admin_username, is_admin=True))

        @self.app.after_request
        def _admin_full_width(response):
            """Make Flask-Admin pages use full viewport width on large screens."""
            try:
                if not request.path.startswith('/admin'):
                    return response
                content_type = (response.headers.get("Content-Type") or "").lower()
                if "text/html" not in content_type:
                    return response

                html = response.get_data(as_text=True)
                marker = "planexe-admin-full-width"
                if marker in html or "</head>" not in html:
                    return response

                css = """
<style id="planexe-admin-full-width">
  .container { width: 100% !important; max-width: none !important; }
  .row { margin-left: 0 !important; margin-right: 0 !important; }
  .col-md-10, .col-md-2, .col-lg-10, .col-lg-2, .col-sm-10, .col-sm-2 {
    width: auto !important;
    float: none !important;
  }
  .table-responsive { overflow-x: auto; }
  #planexe-admin-nav-dashboard {
    margin-top: 8px;
    margin-right: 8px;
    padding: 6px 12px !important;
    border: 1px solid #d0d7de;
    border-radius: 999px;
    background: #fff;
    color: #24292f !important;
    line-height: 1.2 !important;
  }
  #planexe-admin-nav-dashboard:hover {
    background: #f6f8fa !important;
    color: #24292f !important;
  }
  #planexe-admin-logout {
    margin-top: 8px;
    margin-right: 8px;
    padding: 6px 12px !important;
    border: 1px solid #d0d7de;
    border-radius: 999px;
    background: #fff;
    color: #24292f !important;
    line-height: 1.2 !important;
  }
  #planexe-admin-logout:hover {
    background: #f6f8fa !important;
    color: #24292f !important;
  }
</style>
""".strip()
                html = html.replace("</head>", css + "\n</head>", 1)
                if 'id="planexe-admin-nav-dashboard"' not in html and "</body>" in html:
                    dashboard_nav_script = """
<script id="planexe-admin-nav-dashboard">
(function () {
  var rightNav = document.querySelector('.navbar .navbar-nav.navbar-right');
  if (!rightNav) {
    var navbarCollapse = document.querySelector('.navbar .navbar-collapse');
    if (!navbarCollapse) return;
    rightNav = document.createElement('ul');
    rightNav.className = 'nav navbar-nav navbar-right';
    navbarCollapse.appendChild(rightNav);
  }
  var logoutLi = document.getElementById('planexe-admin-nav-logout-item');
  if (!logoutLi) {
    logoutLi = document.createElement('li');
    logoutLi.id = 'planexe-admin-nav-logout-item';
    var logoutA = document.createElement('a');
    logoutA.id = 'planexe-admin-logout';
    logoutA.href = '/logout';
    logoutA.textContent = 'Logout';
    logoutLi.appendChild(logoutA);
  }
  var dashboardLi = document.getElementById('planexe-admin-nav-dashboard-item');
  if (!dashboardLi) {
    dashboardLi = document.createElement('li');
    dashboardLi.id = 'planexe-admin-nav-dashboard-item';
    var dashboardA = document.createElement('a');
    dashboardA.id = 'planexe-admin-nav-dashboard';
    dashboardA.href = '/';
    dashboardA.textContent = 'Dashboard';
    dashboardLi.appendChild(dashboardA);
  }
  // Keep order stable as Logout, Dashboard. Dashboard is rightmost and acts
  // as the "back to home" toggle at the same top-right location as home's
  // "Admin Panel" button.
  rightNav.appendChild(logoutLi);
  rightNav.appendChild(dashboardLi);
})();
</script>
""".strip()
                    html = html.replace("</body>", dashboard_nav_script + "\n</body>", 1)
                response.set_data(html)
                response.headers.pop("Content-Length", None)
            except Exception:
                logger.debug("Failed to inject admin full-width CSS", exc_info=True)
            return response

        @self.app.context_processor
        def inject_current_user_name():
            """Inject current_user_name for header display (full name or None)."""
            ga_id = (os.environ.get("PLANEXE_GOOGLE_ANALYTICS") or "").strip()
            extra: dict[str, Any] = {
                "open_access": self.open_access,
                "google_analytics_id": ga_id or None,
            }
            if not current_user.is_authenticated:
                extra["current_user_name"] = None
                return extra
            if current_user.is_admin:
                extra["current_user_name"] = "Admin"
                return extra
            try:
                user_uuid = uuid.UUID(str(current_user.id))
            except ValueError:
                extra["current_user_name"] = None
                return extra
            user = self.db.session.get(UserAccount, user_uuid)
            if not user:
                extra["current_user_name"] = None
                return extra
            name = (user.name or user.given_name or user.email or "Account").strip() or "Account"
            extra["current_user_name"] = name
            return extra

        @self.app.route('/')
        def index():
            user = None
            admin_account = None
            is_admin = False
            onboarding_steps: list[dict] = []

            if current_user.is_authenticated:
                is_admin = current_user.is_admin
                try:
                    if is_admin:
                        admin_account = _get_current_user_account()
                        user = SimpleNamespace(name="Admin", given_name=None)
                        user_id = str(admin_account.id) if admin_account else self.admin_username
                    else:
                        user_uuid = uuid.UUID(str(current_user.id))
                        user = self.db.session.get(UserAccount, user_uuid)
                        user_id = str(user.id) if user else None

                    if user and user_id:
                        account_id = getattr(admin_account, 'id', None) if is_admin else getattr(user, 'id', None)

                        # Step 1: Account created (always done if logged in)
                        onboarding_steps.append({
                            "title": "Create account",
                            "description": "Sign up for PlanExe to get started.",
                            "done": True,
                            "detail": "Signed in",
                            "link": None,
                        })

                        # Step 2: Deposit credits
                        if is_admin:
                            has_credits = True
                            credit_detail = "Full access"
                        else:
                            credits_balance = to_credit_decimal(user.credits_balance)
                            tx_count = CreditHistory.query.filter_by(user_id=user.id).count()
                            has_credits = credits_balance > 0 or tx_count > 1
                            credit_detail = format_credit_display(user.credits_balance) if has_credits else "No credits yet"
                        onboarding_steps.append({
                            "title": "Deposit credits",
                            "description": 'Credits pay for the AI models that generate your plan. Go to <a href="' + url_for('account') + '">Account</a> to add credits.',
                            "done": has_credits,
                            "detail": credit_detail,
                            "link": url_for('account') if not has_credits else None,
                        })

                        # Step 3: Create API key
                        key_count = UserApiKey.query.filter_by(user_id=account_id, revoked_at=None).count() if account_id else 0
                        has_key = key_count >= 1
                        if key_count == 0:
                            key_detail = "No API keys yet"
                        elif key_count == 1:
                            key_detail = "1 API key"
                        else:
                            key_detail = f"{key_count} API keys"
                        onboarding_steps.append({
                            "title": "Create API key",
                            "description": 'Your AI assistant uses an API key to connect to PlanExe. Create one on the <a href="' + url_for('account') + '">Account</a> page.',
                            "done": has_key,
                            "detail": key_detail,
                            "link": url_for('account') if not has_key else None,
                        })

                        # Step 4: Use MCP (check if any API key has LLM calls)
                        total_llm_calls = 0
                        if has_key:
                            user_key_ids = [
                                str(k.id) for k in UserApiKey.query
                                .filter_by(user_id=account_id, revoked_at=None)
                                .all()
                            ] if account_id else []
                            if user_key_ids:
                                try:
                                    total_llm_calls = (
                                        self.db.session.query(func.count(TokenMetrics.id))
                                        .filter(TokenMetrics.api_key_id.in_(user_key_ids))
                                        .scalar() or 0
                                    )
                                except Exception:
                                    self.db.session.rollback()
                        used_mcp = total_llm_calls >= 1
                        onboarding_steps.append({
                            "title": "Connect via MCP",
                            "description": "Add PlanExe to your AI tool (Claude, Cursor, Windsurf, etc.) using your API key. Your AI will then be able to create plans for you.",
                            "done": used_mcp,
                            "detail": f"{total_llm_calls} LLM calls" if used_mcp else "Not connected yet",
                            "link": "https://docs.planexe.org/mcp/mcp_welcome/" if not used_mcp else None,
                        })

                        # Step 5: Create 5+ plans
                        uid_filter = (
                            PlanItem.user_id.in_(_admin_user_ids())
                            if is_admin
                            else PlanItem.user_id == str(user_id)
                        )
                        total_plans = PlanItem.query.filter(uid_filter).count()
                        is_superuser = total_plans >= 5
                        onboarding_steps.append({
                            "title": "Superuser",
                            "description": "Create 5 or more plans to earn the Superuser badge.",
                            "done": is_superuser,
                            "detail": f"{total_plans} plans created" if is_superuser else f"{total_plans}/5 plans",
                            "link": None,
                        })
                except Exception:
                    logger.debug("Could not load dashboard data", exc_info=True)

            # Debug overrides: /?debug=1&step1=0&step2=1&step3=0&step4=1&step5=0
            if request.args.get("debug") == "1" and onboarding_steps:
                step_keys = ["step1", "step2", "step3", "step4", "step5"]
                for i, key in enumerate(step_keys):
                    val = request.args.get(key)
                    if val is not None and i < len(onboarding_steps):
                        onboarding_steps[i]["done"] = val == "1"

            return render_template(
                'index.html',
                user=user,
                is_admin=is_admin,
                onboarding_steps=onboarding_steps,
                onboarding_debug=request.args.get("debug") == "1",
            )

        @self.app.route('/models')
        @login_required
        def models():
            model_profile_options = _model_profile_options()
            option_by_value = {item["value"]: item for item in model_profile_options}
            profile_to_models = _profile_model_rows_map()
            profile_sections = [
                {
                    "key": profile.value,
                    "title": option_by_value.get(profile.value, {}).get("title", profile.value),
                    "subtitle": option_by_value.get(profile.value, {}).get("subtitle", ""),
                    "filename": f"llm_config/{PlanExeConfig.load(model_profile_override=profile).llm_config_json_name}",
                    "models": profile_to_models.get(profile.value, []),
                }
                for profile in ModelProfileEnum
            ]
            return render_template(
                'models.html',
                profile_sections=profile_sections,
            )

        @self.app.route('/healthcheck')
        def healthcheck():
            try:
                self.db.session.execute(text("SELECT 1"))
                return jsonify({"status": "ok", "database": "ok"}), 200
            except Exception:
                logger.error("Health check failed", exc_info=True)
                return jsonify({"status": "error", "database": "error"}), 500

        @self.app.route('/llms.txt')
        def llms_txt():
            llms_path = self.planexe_project_root / "public" / "llms.txt"
            if not llms_path.exists():
                abort(404)
            return send_file(llms_path, mimetype="text/plain; charset=utf-8")

        @self.app.route('/llm.txt')
        def llm_txt_alias():
            return redirect('/llms.txt', code=308)

        @self.app.route('/account', methods=['GET', 'POST'])
        @login_required
        def account():
            is_admin = current_user.is_admin
            if is_admin:
                user = _get_current_user_account()
                if not user:
                    # Force-create the admin UserAccount directly as a
                    # fallback -- _get_current_user_account may fail on a
                    # fresh DB or after schema migrations.
                    logger.warning(
                        "Account page: _get_current_user_account returned None for admin, "
                        "attempting inline creation. current_user.id=%r admin_username=%r",
                        str(current_user.id), self.admin_username,
                    )
                    admin_pref_id = uuid.uuid5(
                        uuid.NAMESPACE_URL, f"planexe-admin-pref:{self.admin_username}"
                    )
                    try:
                        user = self.db.session.get(UserAccount, admin_pref_id)
                        if not user:
                            user = _new_model(
                                UserAccount,
                                id=admin_pref_id,
                                is_admin=True,
                                name="Admin",
                            )
                            self.db.session.add(user)
                            self.db.session.commit()
                            logger.info("Created admin UserAccount %s via account page fallback", admin_pref_id)
                    except Exception:
                        self.db.session.rollback()
                        logger.exception("Inline admin UserAccount creation failed for %s", admin_pref_id)
                        user = self.db.session.get(UserAccount, admin_pref_id)
            else:
                user_uuid = uuid.UUID(str(current_user.id))
                user = self.db.session.get(UserAccount, user_uuid)
            if not user:
                logger.warning(
                    "Account page: no UserAccount found, redirecting to logout. "
                    "is_admin=%s current_user.id=%r",
                    is_admin, str(current_user.id),
                )
                return redirect(url_for('logout'))

            stripe_result = request.args.get("stripe")
            stripe_session_id = request.args.get("session_id", "").strip()
            if request.method == "GET" and stripe_result in ("success", "cancel"):
                _record_event(
                    EventType.GENERIC_EVENT,
                    "Stripe return to account page",
                    context={
                        "user_id": str(user.id),
                        "stripe_result": stripe_result,
                        "checkout_session_id": stripe_session_id or None,
                    },
                )
                if stripe_result == "success" and stripe_session_id:
                    _finalize_stripe_checkout_session(user, stripe_session_id)

            new_api_key = session.pop("new_api_key", None)
            if request.method == 'POST':
                action = request.form.get('action')
                try:
                    if action == "create_api_key":
                        raw_key = get_or_create_api_key(user, name=request.form.get("name"))
                        if raw_key:
                            session["new_api_key"] = raw_key
                    elif action == "revoke_api_key":
                        key_id = request.form.get("key_id", "").strip()
                        if key_id:
                            try:
                                key_uuid = uuid.UUID(key_id)
                            except ValueError:
                                key_uuid = None
                            if key_uuid:
                                target_key = UserApiKey.query.filter_by(
                                    id=key_uuid, user_id=user.id, revoked_at=None
                                ).first()
                                if target_key:
                                    target_key.revoked_at = datetime.now(UTC)
                                    self.db.session.commit()
                    elif action == "rename_api_key":
                        key_id = request.form.get("key_id", "").strip()
                        new_name = (request.form.get("name") or "").strip()[:128]
                        if key_id:
                            try:
                                key_uuid = uuid.UUID(key_id)
                            except ValueError:
                                key_uuid = None
                            if key_uuid:
                                target_key = UserApiKey.query.filter_by(
                                    id=key_uuid, user_id=user.id, revoked_at=None
                                ).first()
                                if target_key:
                                    target_key.name = new_name or None
                                    self.db.session.commit()
                    elif action == "reset_api_key":
                        key_id = request.form.get("key_id", "").strip()
                        if key_id:
                            try:
                                key_uuid = uuid.UUID(key_id)
                            except ValueError:
                                key_uuid = None
                            if key_uuid:
                                target_key = UserApiKey.query.filter_by(
                                    id=key_uuid, user_id=user.id, revoked_at=None
                                ).first()
                                if target_key:
                                    api_key_secret = os.environ.get("PLANEXE_API_KEY_SECRET", "dev-api-key-secret")
                                    raw_key = f"pex_{secrets.token_urlsafe(24)}"
                                    target_key.key_hash = hashlib.sha256(f"{api_key_secret}:{raw_key}".encode("utf-8")).hexdigest()
                                    target_key.key_prefix = raw_key[:10]
                                    target_key.key_plaintext = raw_key if not self._api_key_show_once else None
                                    self.db.session.commit()
                                    session["new_api_key"] = raw_key
                    elif action == "regenerate_api_key":
                        # Legacy action: revoke all, create one new key.
                        existing_keys = UserApiKey.query.filter_by(user_id=user.id, revoked_at=None).all()
                        now = datetime.now(UTC)
                        for key in existing_keys:
                            key.revoked_at = now
                        self.db.session.commit()
                        raw_key = get_or_create_api_key(user)
                        if raw_key:
                            session["new_api_key"] = raw_key
                except Exception:
                    self.db.session.rollback()
                    logger.exception("Account POST action=%s failed", action)
                return redirect(url_for('account'))

            active_keys = (
                UserApiKey.query
                .filter_by(user_id=user.id, revoked_at=None)
                .order_by(UserApiKey.created_at.asc())
                .all()
            )

            # Per-key stats: LLM call counts and credit usage.
            active_key_ids = [str(k.id) for k in active_keys]
            llm_call_counts: dict[str, int] = {}
            credit_usage: dict[str, str] = {}
            if active_key_ids:
                try:
                    for row in (
                        self.db.session.query(TokenMetrics.api_key_id, func.count(TokenMetrics.id))
                        .filter(TokenMetrics.api_key_id.in_(active_key_ids))
                        .group_by(TokenMetrics.api_key_id)
                        .all()
                    ):
                        llm_call_counts[row[0]] = row[1]
                except Exception as exc:
                    logger.warning("Per-key LLM call count query failed: %s", exc)
                    self.db.session.rollback()
                try:
                    for row in (
                        self.db.session.query(CreditHistory.api_key_id, func.sum(CreditHistory.delta))
                        .filter(
                            CreditHistory.api_key_id.in_(active_key_ids),
                            CreditHistory.delta < 0,
                        )
                        .group_by(CreditHistory.api_key_id)
                        .all()
                    ):
                        credit_usage[row[0]] = format_credit_display(abs(row[1]))
                except Exception as exc:
                    logger.warning("Per-key credit usage query failed: %s", exc)
                    self.db.session.rollback()

            payment_rows = (
                PaymentRecord.query
                .filter_by(user_id=user.id)
                .order_by(PaymentRecord.created_at.desc())
                .limit(20)
                .all()
            )
            recent_payments: list[dict[str, Any]] = []
            for row in payment_rows:
                created_at = row.created_at
                if created_at and created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=UTC)
                amount_minor = int(row.amount or 0)
                recent_payments.append({
                    "created_at": created_at.strftime("%Y-%m-%d %H:%M:%S UTC") if created_at else "\u2014",
                    "provider": (row.provider or "").upper(),
                    "status": row.status or "unknown",
                    "credits": format_credit_display(row.credits),
                    "amount_major": amount_minor / 100.0,
                    "currency": (row.currency or "usd").upper(),
                    "payment_id": row.provider_payment_id or "",
                })

            linked_provider_rows = (
                UserProvider.query
                .filter_by(user_id=user.id)
                .order_by(UserProvider.last_login_at.desc())
                .all()
            )
            linked_sign_in_methods: list[str] = []
            for row in linked_provider_rows:
                label = _auth_provider_label(row.provider)
                if label not in linked_sign_in_methods:
                    linked_sign_in_methods.append(label)

            auth_provider_session = session.get("auth_provider")
            signed_in_with = _auth_provider_label(auth_provider_session)
            if signed_in_with == "Unknown" and linked_sign_in_methods:
                signed_in_with = linked_sign_in_methods[0]
            if is_admin:
                signed_in_with = "Admin credentials"

            return render_template(
                'account.html',
                admin_mode=is_admin,
                user=user,
                credits_balance_display="Full access" if is_admin else format_credit_display(user.credits_balance),
                credit_price_cents=max(1, int(os.environ.get("PLANEXE_CREDIT_PRICE_CENTS", "100"))),
                active_keys=active_keys,
                llm_call_counts=llm_call_counts,
                credit_usage=credit_usage,
                can_create_key=len(active_keys) < 10,
                new_api_key=new_api_key,
                recent_payments=recent_payments,
                signed_in_with=signed_in_with,
                linked_sign_in_methods=linked_sign_in_methods,
                stripe_enabled=bool(os.environ.get("PLANEXE_STRIPE_SECRET_KEY")),
                telegram_enabled=bool(os.environ.get("PLANEXE_TELEGRAM_BOT_TOKEN")),
                api_key_show_once=self._api_key_show_once,
            )

    def run_server(self, debug: bool = False, host: str = "0.0.0.0", port: int = 5000):
        env_debug = os.environ.get("PLANEXE_FRONTEND_MULTIUSER_DEBUG")
        if env_debug is not None:
            debug = env_debug.lower() in ("1", "true", "yes", "on")
        host = os.environ.get("PLANEXE_FRONTEND_MULTIUSER_HOST", host)
        port_str = os.environ.get("PLANEXE_FRONTEND_MULTIUSER_PORT")
        if port_str:
            port = int(port_str)
        self.app.run(debug=debug, host=host, port=port)

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(threadName)s - %(message)s'
    )
    try:
        flask_app_instance = MyFlaskApp()
    except ValueError as exc:
        # Configuration errors (e.g. PLANEXE_AUTH_REQUIRED=true without OAuth).
        # Exit with code 0 so Docker "on-failure" restart policy does NOT restart.
        logger.critical("Configuration error – service will not start: %s", exc)
        sys.exit(0)
    flask_app_instance.run_server()
