"""
Custom ModelViews for the PlanExe-server tables.
"""
import base64
import json
import math
import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, cast
from flask_admin.contrib.sqla import ModelView
from flask_admin.actions import action
from flask_admin import expose
from markupsafe import Markup
from flask import url_for, abort, redirect, Response, request, flash
from flask_login import current_user
from sqlalchemy.orm import defer
from wtforms import FileField, BooleanField

class AdminOnlyModelView(ModelView):
    """Restrict admin views to authenticated admin users only."""
    def is_accessible(self):
        return current_user.is_authenticated and getattr(current_user, "is_admin", False)

    def inaccessible_callback(self, name, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("login"))
        abort(403)

    @action("download_json", "Download as JSON", "Download selected rows as JSON?")
    def action_download_json(self, ids):
        """Export selected rows as a JSON file from the admin list view."""
        if not ids:
            return

        primary_keys = self.model.__mapper__.primary_key
        if len(primary_keys) != 1:
            abort(400, "Download as JSON currently supports single-column primary keys only.")
        primary_key_col = primary_keys[0]

        python_type = None
        try:
            python_type = primary_key_col.type.python_type
        except Exception:
            python_type = str

        normalized_ids = []
        for raw_id in ids:
            if python_type is uuid.UUID:
                try:
                    normalized_ids.append(uuid.UUID(str(raw_id)))
                except Exception:
                    normalized_ids.append(raw_id)
            else:
                try:
                    normalized_ids.append(python_type(raw_id))
                except Exception:
                    normalized_ids.append(raw_id)

        rows = self.session.query(self.model).filter(primary_key_col.in_(normalized_ids)).all()
        records = [self._serialize_model_row(row) for row in rows]
        payload = {
            "model": self.model.__name__,
            "count": len(records),
            "records": records,
        }
        json_body = json.dumps(payload, indent=2, ensure_ascii=False)

        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        filename = f"{self.model.__name__.lower()}_{timestamp}.json"
        return Response(
            json_body,
            mimetype="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    def _serialize_model_row(self, row):
        data = {}
        for column in row.__table__.columns:
            data[column.name] = self._serialize_value(getattr(row, column.name))
        return data

    def _serialize_value(self, value):
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, uuid.UUID):
            return str(value)
        if isinstance(value, Enum):
            return value.value if hasattr(value, "value") else str(value)
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, bytes):
            return base64.b64encode(value).decode("ascii")
        return value

class WorkerItemView(AdminOnlyModelView):
    """Custom ModelView for WorkerItem"""
    column_list = ['id', 'started_at', 'last_heartbeat_at', 'current_task_id']
    column_default_sort = ('id', False)
    column_searchable_list = ['id', 'current_task_id']
    column_filters = ['started_at', 'last_heartbeat_at']

class PlanItemView(AdminOnlyModelView):
    """Custom ModelView for PlanItem"""
    column_list = [
        'id',
        'timestamp_created',
        'state',
        'prompt',
        'progress_percentage',
        'progress_message',
        'stop_requested',
        'stop_requested_timestamp',
        'user_id',
        'parameters',
        'view_plan',
        'generated_report_html',
        'run_zip_snapshot',
        'run_activity_overview_json',
        'run_track_activity',
        'run_artifact_layout_version',
    ]
    column_labels = {
        'view_plan': 'View Plan',
        'generated_report_html': 'Report',
        'run_zip_snapshot': 'Run Zip',
        'run_activity_overview_json': 'Activity Overview',
        'run_track_activity': 'Track Activity',
        'run_artifact_layout_version': 'Artifact Layout',
    }
    column_default_sort = ('timestamp_created', False)  # Sort by creation timestamp, newest first
    column_searchable_list = ['id', 'prompt', 'user_id']
    column_filters = ['state', 'timestamp_created', 'user_id']
    column_formatters = {
        'id': lambda v, c, m, p: str(m.id)[:8] if m.id else '',
        'state': lambda v, c, m, p: (
            Markup(f'<span style="color:#e65100">{m.state.name}</span>')
            if m.state and m.state.name in ('stopped', 'failed')
            else (m.state.name if m.state else '')
        ),
        'prompt': lambda v, c, m, p: m.prompt[:100] + '...' if m.prompt and len(m.prompt) > 100 else m.prompt,
        'view_plan': lambda v, c, m, p: Markup(
            f'<a href="/viewplan?run_id={m.id}" target="_blank">View</a>'
        ) if m.has_generated_report_html else '—',
        'generated_report_html': lambda v, c, m, p: Markup(
            f'<a href="{url_for("download_task_report", task_id=str(m.id))}">Download</a>'
        ) if m.has_generated_report_html else '—',
        'run_zip_snapshot': lambda v, c, m, p: Markup(
            f'<a href="{url_for("download_task_run_zip", task_id=str(m.id))}">Download</a>'
        ) if m.has_run_zip_snapshot else '—',
        'run_activity_overview_json': lambda v, c, m, p: (
            json.dumps(m.run_activity_overview_json, ensure_ascii=False)[:120] + '...'
            if m.run_activity_overview_json and len(json.dumps(m.run_activity_overview_json, ensure_ascii=False)) > 120
            else (json.dumps(m.run_activity_overview_json, ensure_ascii=False) if m.run_activity_overview_json else '—')
        ),
        'run_track_activity': lambda v, c, m, p: Markup(
            f'<a href="{url_for("download_task_track_activity", task_id=str(m.id))}">Download</a>'
        ) if m.has_run_track_activity_jsonl else '—',
    }
    form_excluded_columns = [
        'generated_report_html',
        'run_zip_snapshot',
        'run_track_activity_jsonl',
    ]
    form_extra_fields = {
        'generated_report_html_upload': FileField('Upload Report HTML'),
        'generated_report_html_clear': BooleanField('Clear existing report HTML'),
        'run_zip_snapshot_upload': FileField('Upload Run ZIP'),
        'run_zip_snapshot_clear': BooleanField('Clear existing run ZIP'),
        'run_track_activity_jsonl_upload': FileField('Upload Track Activity JSONL'),
        'run_track_activity_jsonl_clear': BooleanField('Clear existing track activity JSONL'),
    }

    def get_query(self):
        return super().get_query().options(
            defer(self.model.generated_report_html),
            defer(self.model.run_zip_snapshot),
            defer(self.model.run_track_activity_jsonl),
        )

    def on_form_prefill(self, form: Any, id: Any) -> None:
        model = self.get_one(id)
        if model is None:
            return

        if hasattr(form, "generated_report_html_upload"):
            if model.has_generated_report_html:
                href = url_for("download_task_report", task_id=str(model.id))
                form.generated_report_html_upload.description = Markup(
                    f'Current file: <a href="{href}" target="_blank">download report.html</a>'
                )
            else:
                form.generated_report_html_upload.description = "Current file: none"

        if hasattr(form, "run_zip_snapshot_upload"):
            if model.has_run_zip_snapshot:
                href = url_for("download_task_run_zip", task_id=str(model.id))
                form.run_zip_snapshot_upload.description = Markup(
                    f'Current file: <a href="{href}" target="_blank">download run.zip</a>'
                )
            else:
                form.run_zip_snapshot_upload.description = "Current file: none"

        if hasattr(form, "run_track_activity_jsonl_upload"):
            if model.has_run_track_activity_jsonl:
                href = url_for("download_task_track_activity", task_id=str(model.id))
                form.run_track_activity_jsonl_upload.description = Markup(
                    f'Current file: <a href="{href}" target="_blank">download track_activity.jsonl</a>'
                )
            else:
                form.run_track_activity_jsonl_upload.description = "Current file: none"

    @action("change_state_to_failed", "Change State To Failed")
    def action_change_state_to_failed(self, ids):
        from flask import session as flask_session
        flask_session["bulk_fail_ids"] = list(ids)
        return redirect(self.get_url(".bulk_change_to_failed_view"))

    @expose('/bulk-change-to-failed/', methods=['GET', 'POST'])
    def bulk_change_to_failed_view(self):
        from flask import session as flask_session
        from database_api.model_planitem import PlanState

        if not self.is_accessible():
            return self.inaccessible_callback('bulk_change_to_failed_view')

        raw_ids = flask_session.get("bulk_fail_ids", [])
        if not raw_ids:
            flash('No plans selected.', 'error')
            return redirect(self.get_url('.index_view'))

        plan_ids = []
        for raw_id in raw_ids:
            try:
                plan_ids.append(uuid.UUID(str(raw_id)))
            except Exception:
                plan_ids.append(raw_id)

        plans = self.session.query(self.model).filter(
            self.model.id.in_(plan_ids)
        ).all()

        if not plans:
            flash('No matching plans found.', 'error')
            return redirect(self.get_url('.index_view'))

        if request.method == 'POST':
            def _checked(name: str) -> bool:
                return name in request.form

            failure_reason = request.form.get('failure_reason', '').strip() or 'admin_bulk_fail'
            error_message = request.form.get('error_message', '').strip() or None
            failed_step = request.form.get('failed_step', '').strip() or None
            recoverable_raw = request.form.get('recoverable', '')
            recoverable = {'true': True, 'false': False}.get(recoverable_raw, False)
            progress_pct = request.form.get('progress_percentage', '').strip()
            progress_message = request.form.get('progress_message', '').strip() or None
            steps_completed = request.form.get('steps_completed', '').strip()
            steps_total = request.form.get('steps_total', '').strip()
            current_step = request.form.get('current_step', '').strip() or None

            for plan in plans:
                plan.state = PlanState.failed
                if _checked('overwrite_failure_reason'):
                    plan.failure_reason = failure_reason
                if _checked('overwrite_error_message'):
                    plan.error_message = error_message
                if _checked('overwrite_failed_step'):
                    plan.failed_step = failed_step
                if _checked('overwrite_recoverable'):
                    plan.recoverable = recoverable
                if _checked('overwrite_progress_percentage'):
                    plan.progress_percentage = float(progress_pct) if progress_pct else 0.0
                if _checked('overwrite_progress_message'):
                    plan.progress_message = progress_message
                if _checked('overwrite_steps_completed'):
                    plan.steps_completed = int(steps_completed) if steps_completed else None
                if _checked('overwrite_steps_total'):
                    plan.steps_total = int(steps_total) if steps_total else None
                if _checked('overwrite_current_step'):
                    plan.current_step = current_step
            self.session.commit()
            flask_session.pop("bulk_fail_ids", None)
            flash(f'Transitioned {len(plans)} plan(s) to failed.', 'success')
            return redirect(self.get_url('.index_view'))

        # GET: compute state breakdown with warnings
        state_warnings = {
            'completed': 'plan already finished successfully, changing state to failed shifts blame to the system',
            'failed': 'plan is already in failed state',
            'stopped': 'changing state of an already stopped task is ill-advised, since that changes the blame from the user responsible to the system responsible',
        }
        state_rows: list[tuple[str, int, str | None]] = []
        state_counts: dict[str, int] = {}
        for plan in plans:
            state_name = plan.state.name if plan.state else 'unknown'
            state_counts[state_name] = state_counts.get(state_name, 0) + 1
        for state_name, count in state_counts.items():
            warning = state_warnings.get(state_name)
            state_rows.append((state_name, count, warning))

        return self.render(
            'admin/bulk_change_to_failed.html',
            state_rows=state_rows,
            total_count=len(plans),
            form_action=self.get_url('.bulk_change_to_failed_view'),
            cancel_url=self.get_url('.index_view'),
        )

    def on_model_change(self, form: Any, model: Any, is_created: bool) -> None:
        def _read_upload(field_name: str):
            field = getattr(form, field_name, None)
            data = getattr(field, "data", None) if field is not None else None
            filename = getattr(data, "filename", None) if data is not None else None
            if not data or not filename:
                return None
            return data.read()

        uploaded_report = _read_upload("generated_report_html_upload")
        uploaded_zip = _read_upload("run_zip_snapshot_upload")
        uploaded_track = _read_upload("run_track_activity_jsonl_upload")

        if uploaded_report is not None:
            model.generated_report_html = uploaded_report.decode("utf-8", errors="replace")
        elif bool(getattr(form.generated_report_html_clear, "data", False)):
            model.generated_report_html = None

        if uploaded_zip is not None:
            model.run_zip_snapshot = uploaded_zip
        elif bool(getattr(form.run_zip_snapshot_clear, "data", False)):
            model.run_zip_snapshot = None

        if uploaded_track is not None:
            model.run_track_activity_jsonl = uploaded_track.decode("utf-8", errors="replace")
        elif bool(getattr(form.run_track_activity_jsonl_clear, "data", False)):
            model.run_track_activity_jsonl = None

        return super().on_model_change(form, model, is_created)

class NonceItemView(AdminOnlyModelView):
    """Custom ModelView for NonceItem"""
    def __init__(self, model, *args, **kwargs):
        self.column_list = [c.key for c in model.__table__.columns]
        self.form_columns = self.column_list
        super(NonceItemView, self).__init__(model, *args, **kwargs)
        
    column_default_sort = ('created_at', True)
    column_searchable_list = ['nonce_key']
    column_filters = ['request_count', 'created_at', 'last_accessed_at']

    def get_create_form(self):
        form = self.scaffold_form()
        delattr(form, 'id')
        return form


class UserAccountView(AdminOnlyModelView):
    """Custom ModelView for UserAccount with admin credit management."""

    column_default_sort = ('created_at', True)
    column_searchable_list = ['email', 'name']
    column_filters = ['is_admin', 'created_at', 'last_login_at']
    column_formatters = {
        'credits_balance': lambda v, c, m, p: _ceil_decimal(m.credits_balance, 3),
    }

    @expose('/add-credits/', methods=['GET', 'POST'])
    def add_credits_view(self):
        from database_api.model_credit_history import CreditHistory

        if not self.is_accessible():
            return self.inaccessible_callback('add_credits_view')

        user_id = request.args.get('id') or request.form.get('id')
        if not user_id:
            flash('No user selected.', 'error')
            return redirect(self.get_url('.index_view'))

        try:
            user_uuid = uuid.UUID(str(user_id))
        except ValueError:
            flash('Invalid user ID.', 'error')
            return redirect(self.get_url('.index_view'))

        from database_api.model_user_account import UserAccount
        user = self.session.get(UserAccount, user_uuid)
        if not user:
            flash('User not found.', 'error')
            return redirect(self.get_url('.index_view'))

        if request.method == 'POST':
            try:
                credits_str = request.form.get('credits', '').strip()
                if not credits_str:
                    raise ValueError('Credits amount is required.')
                credits_amount = Decimal(credits_str)
                if credits_amount <= 0:
                    raise ValueError('Credits must be a positive number.')
            except Exception as e:
                flash(f'Invalid credits value: {e}', 'error')
                return redirect(self.get_url('.add_credits_view', id=user_id))

            reason = request.form.get('reason', '').strip() or 'admin_grant'
            credit_scale = Decimal("0.000000001")

            current_balance = Decimal(str(user.credits_balance or 0)).quantize(credit_scale)
            delta = Decimal(str(credits_amount)).quantize(credit_scale)
            next_balance = max(Decimal("0"), current_balance + delta).quantize(credit_scale)
            user.credits_balance = next_balance

            ledger = cast(Any, CreditHistory)(
                user_id=user.id,
                delta=delta,
                reason=reason,
                source='admin',
            )
            self.session.add(ledger)
            self.session.commit()

            flash(f'Added {credits_amount} credits to {user.email or user.name or user.id}. '
                  f'New balance: {next_balance}', 'success')
            return redirect(self.get_url('.index_view'))

        # GET: render the form
        current_balance = _ceil_decimal(user.credits_balance, 3)
        user_display = user.email or user.name or str(user.id)
        return self.render(
            'admin/add_credits.html',
            user_display=user_display,
            current_balance=current_balance,
            form_action=self.get_url('.add_credits_view', id=user_id),
            user_id=user_id,
            cancel_url=self.get_url('.index_view'),
        )

    column_extra_row_actions = None  # will be set in __init__

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from flask_admin.model.template import EndpointLinkRowAction
        self.column_extra_row_actions = [
            EndpointLinkRowAction('fa fa-plus glyphicon glyphicon-plus', '.add_credits_view', title='Add Credits'),
        ]


class TokenMetricsView(AdminOnlyModelView):
    """Custom ModelView for TokenMetrics."""
    column_list = [
        'id',
        'timestamp',
        'task_id',
        'user_id',
        'llm_model',
        'upstream_provider',
        'upstream_model',
        'input_tokens',
        'output_tokens',
        'thinking_tokens',
        'total_tokens',
        'cost_usd',
        'duration_seconds',
        'success',
        'error_message',
    ]
    column_default_sort = ('timestamp', True)
    column_searchable_list = ['task_id', 'user_id', 'llm_model', 'upstream_provider', 'upstream_model']
    column_filters = ['timestamp', 'user_id', 'llm_model', 'upstream_provider', 'upstream_model', 'success']
    column_formatters = {
        'timestamp': lambda v, c, m, p: _format_timestamp_seconds(m.timestamp),
        'cost_usd': lambda v, c, m, p: _ceil_decimal(m.cost_usd, 3),
        'duration_seconds': lambda v, c, m, p: _ceil_decimal(m.duration_seconds, 2),
    }


def _ceil_decimal(value, decimals: int) -> str:
    if value is None:
        return '—'
    scale = 10 ** decimals
    rounded = math.ceil(float(value) * scale) / scale
    return f"{rounded:.{decimals}f}"


def _format_timestamp_seconds(value) -> str:
    if value is None:
        return '—'
    return value.strftime('%Y-%m-%d %H:%M:%S')
