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
from flask_admin.contrib.sqla import ModelView
from flask_admin.actions import action
from markupsafe import Markup
from flask import url_for, abort, redirect, Response
from flask_login import current_user

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

class TaskItemView(AdminOnlyModelView):
    """Custom ModelView for TaskItem"""
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
        'prompt': lambda v, c, m, p: m.prompt[:100] + '...' if m.prompt and len(m.prompt) > 100 else m.prompt,
        'view_plan': lambda v, c, m, p: Markup(
            f'<a href="/viewplan?run_id={m.id}" target="_blank">View</a>'
        ) if m.generated_report_html else '—',
        'generated_report_html': lambda v, c, m, p: Markup(
            f'<a href="{url_for("download_task_report", task_id=str(m.id))}">Download ({len(m.generated_report_html.encode("utf-8")) / 1024:.1f} KB)</a>'
        ) if m.generated_report_html else '—',
        'run_zip_snapshot': lambda v, c, m, p: Markup(
            f'<a href="{url_for("download_task_run_zip", task_id=str(m.id))}">Download ({len(m.run_zip_snapshot) / 1024:.1f} KB)</a>'
        ) if m.run_zip_snapshot else '—',
        'run_activity_overview_json': lambda v, c, m, p: (
            json.dumps(m.run_activity_overview_json, ensure_ascii=False)[:120] + '...'
            if m.run_activity_overview_json and len(json.dumps(m.run_activity_overview_json, ensure_ascii=False)) > 120
            else (json.dumps(m.run_activity_overview_json, ensure_ascii=False) if m.run_activity_overview_json else '—')
        ),
        'run_track_activity': lambda v, c, m, p: Markup(
            f'<a href="{url_for("download_task_track_activity", task_id=str(m.id))}">Download ({((m.run_track_activity_bytes if m.run_track_activity_bytes is not None else len(m.run_track_activity_jsonl.encode("utf-8"))) / 1024):.1f} KB)</a>'
        ) if m.run_track_activity_jsonl else '—',
    }

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
