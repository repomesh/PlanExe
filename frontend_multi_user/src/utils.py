"""Shared utility functions for the frontend_multi_user application."""
from datetime import datetime, UTC
from decimal import Decimal, ROUND_CEILING
import re
from typing import Any, Optional

CREDIT_SCALE = Decimal("0.000000001")


def safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def clean_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def extract_exception_type(message: Any) -> Optional[str]:
    text = clean_text(message)
    if text is None:
        return None
    match = re.search(r"([A-Za-z_][A-Za-z0-9_\.]*Error)\b", text)
    if match:
        return match.group(1)
    return None


def extract_nested_value(payload: Any, key_names: set[str]) -> Any:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key).strip().lower() in key_names and value not in (None, "", [], {}):
                return value
        for value in payload.values():
            found = extract_nested_value(value, key_names)
            if found not in (None, "", [], {}):
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = extract_nested_value(item, key_names)
            if found not in (None, "", [], {}):
                return found
    return None


def extract_provider_model_from_activity_key(model_key: Any) -> tuple[Optional[str], Optional[str]]:
    key = clean_text(model_key)
    if key is None:
        return None, None
    if ":" not in key:
        return None, key
    provider, model = key.split(":", 1)
    provider_clean = provider.strip() or None
    model_clean = model.strip() or None
    return provider_clean, model_clean


def to_credit_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0)).quantize(CREDIT_SCALE)
    except Exception:
        return Decimal("0").quantize(CREDIT_SCALE)


def format_credit_display(value: Any) -> str:
    amount = to_credit_decimal(value)
    quantized = amount.quantize(Decimal("0.001"), rounding=ROUND_CEILING)
    return format(quantized, ".3f")


def format_relative_time(value: Any) -> str:
    if not isinstance(value, datetime):
        return "-"
    now = datetime.now(UTC)
    dt = value if value.tzinfo else value.replace(tzinfo=UTC)
    seconds = max(0, int((now - dt).total_seconds()))
    if seconds >= 365 * 24 * 3600:
        n = seconds // (365 * 24 * 3600)
        return f"{n} year" if n == 1 else f"{n} years"
    if seconds >= 30 * 24 * 3600:
        n = seconds // (30 * 24 * 3600)
        return f"{n} month" if n == 1 else f"{n} months"
    if seconds >= 24 * 3600:
        n = seconds // (24 * 3600)
        return f"{n} day" if n == 1 else f"{n} days"
    if seconds >= 3600:
        n = seconds // 3600
        return f"{n} hour" if n == 1 else f"{n} hours"
    if seconds >= 60:
        n = seconds // 60
        return f"{n} min" if n == 1 else f"{n} mins"
    n = seconds
    return f"{n} sec" if n == 1 else f"{n} secs"


def normalize_plan_view_mode(value: Any) -> str:
    mode = str(value or "").strip().lower()
    if mode in {"info", "view"}:
        return mode
    return "view"


def coerce_json_dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}
