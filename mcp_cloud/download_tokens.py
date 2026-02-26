"""PlanExe MCP Cloud – signed download tokens and URL builders."""
import contextvars
import hashlib
import hmac
import logging
import os
import secrets
import time
from typing import Optional

from mcp_cloud.db_setup import REPORT_FILENAME, ZIP_FILENAME

logger = logging.getLogger(__name__)


# Context var set by HTTP server so download URLs use the request's host when
# PLANEXE_MCP_PUBLIC_BASE_URL is not set (avoids localhost for remote clients).
_download_base_url_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "download_base_url", default=None
)


def set_download_base_url(base_url: Optional[str]) -> None:
    """Set the base URL used for download links for this request (e.g. from HTTP Request).
    Cleared automatically when the request ends. Used when PLANEXE_MCP_PUBLIC_BASE_URL is unset."""
    if base_url is not None:
        _download_base_url_ctx.set(base_url.rstrip("/"))
    else:
        try:
            _download_base_url_ctx.set("")
        except LookupError:
            pass


def clear_download_base_url() -> None:
    """Clear the request-scoped base URL (call when request ends)."""
    try:
        _download_base_url_ctx.set("")
    except LookupError:
        pass


def _get_download_base_url() -> Optional[str]:
    """Return base URL for download links: env var, then request context, then None."""
    base_url = os.environ.get("PLANEXE_MCP_PUBLIC_BASE_URL")
    if base_url:
        return base_url.rstrip("/")
    try:
        ctx_url = _download_base_url_ctx.get()
        return ctx_url if ctx_url else None
    except LookupError:
        return None


def build_report_download_path(plan_id: str) -> str:
    return f"/download/{plan_id}/{REPORT_FILENAME}"


def build_zip_download_path(plan_id: str) -> str:
    return f"/download/{plan_id}/{ZIP_FILENAME}"


# ---------------------------------------------------------------------------
# Signed, expiring download tokens
# ---------------------------------------------------------------------------

# Default TTL for signed download tokens (seconds). Configurable via env var.
DOWNLOAD_TOKEN_TTL_SECONDS = int(os.environ.get("PLANEXE_DOWNLOAD_TOKEN_TTL", "900"))  # 15 min

# Per-process fallback secret when no env var is set.  Tokens won't survive a
# server restart, but that is acceptable for the fallback case.
_random_token_secret: Optional[bytes] = None


def validate_download_token_secret() -> None:
    """Raise if no stable download-token secret is configured.

    Call at startup when authentication is required so the server
    fails hard instead of silently using a random per-process secret
    that invalidates tokens on restart.
    """
    for env_var in ("PLANEXE_DOWNLOAD_TOKEN_SECRET", "PLANEXE_API_KEY_SECRET"):
        if os.environ.get(env_var):
            return
    raise RuntimeError(
        "Neither PLANEXE_DOWNLOAD_TOKEN_SECRET nor PLANEXE_API_KEY_SECRET is set. "
        "Set at least one or disable auth with PLANEXE_MCP_REQUIRE_AUTH=false."
    )


def _get_download_token_secret() -> bytes:
    """Return the HMAC-SHA256 secret used to sign download tokens.

    Priority: PLANEXE_DOWNLOAD_TOKEN_SECRET → PLANEXE_API_KEY_SECRET →
    per-process random (with a warning logged once).
    """
    global _random_token_secret
    for env_var in ("PLANEXE_DOWNLOAD_TOKEN_SECRET", "PLANEXE_API_KEY_SECRET"):
        value = os.environ.get(env_var)
        if value:
            return value.encode()
    if _random_token_secret is None:
        _random_token_secret = secrets.token_bytes(32)
        logger.warning(
            "PLANEXE_DOWNLOAD_TOKEN_SECRET is not set; using a random per-process secret. "
            "Download tokens will be invalidated on server restart. "
            "Set PLANEXE_DOWNLOAD_TOKEN_SECRET to a stable value."
        )
    return _random_token_secret


def generate_download_token(plan_id: str, filename: str) -> str:
    """Return a signed, time-limited token for one plan artifact download.

    Format: ``{expiry_unix_ts}.{hmac_hex}``
    The HMAC covers ``plan_id:filename:expiry`` so the token is scoped to
    exactly one file and cannot be reused for a different plan.
    """
    expiry = int(time.time()) + DOWNLOAD_TOKEN_TTL_SECONDS
    message = f"{plan_id}:{filename}:{expiry}".encode()
    mac = hmac.new(_get_download_token_secret(), message, hashlib.sha256).hexdigest()
    return f"{expiry}.{mac}"


def validate_download_token(token: str, plan_id: str, filename: str) -> bool:
    """Return True when *token* is a valid, unexpired token for the given artifact."""
    try:
        expiry_str, mac = token.split(".", 1)
        expiry = int(expiry_str)
    except (ValueError, AttributeError):
        return False
    if time.time() > expiry:
        return False
    message = f"{plan_id}:{filename}:{expiry}".encode()
    expected_mac = hmac.new(_get_download_token_secret(), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, expected_mac)


def build_report_download_url(plan_id: str) -> Optional[str]:
    base_url = _get_download_base_url()
    if not base_url:
        return None
    token = generate_download_token(plan_id, REPORT_FILENAME)
    return f"{base_url}{build_report_download_path(plan_id)}?token={token}"


def build_zip_download_url(plan_id: str) -> Optional[str]:
    base_url = _get_download_base_url()
    if not base_url:
        return None
    token = generate_download_token(plan_id, ZIP_FILENAME)
    return f"{base_url}{build_zip_download_path(plan_id)}?token={token}"
