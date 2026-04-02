"""Authentication blueprint — OAuth, login/logout, session management."""
import logging
import os
import secrets
from typing import Any, Optional

from flask import (
    Blueprint, abort, current_app, redirect, render_template, request, session, url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from database_api.model_user_account import UserAccount
from database_api.model_user_api_key import UserApiKey
from database_api.model_user_provider import UserProvider
from database_api.planexe_db_singleton import db

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)

AUTH_PROVIDER_LABELS = {
    "google": "Google",
    "github": "GitHub",
    "discord": "Discord",
    "password": "Password",
    "telegram": "Telegram",
    "open_access": "Open access",
}


def _new_model(model_cls: Any, **kwargs: Any) -> Any:
    from typing import cast
    return cast(Any, model_cls)(**kwargs)


def _oauth_redirect_url(provider: str) -> str:
    return f"{current_app.config['PUBLIC_BASE_URL']}/auth/{provider}/callback"


def _auth_provider_label(provider: Optional[str]) -> str:
    if not provider:
        return "Unknown"
    provider_key = str(provider).strip().lower()
    if not provider_key:
        return "Unknown"
    return AUTH_PROVIDER_LABELS.get(provider_key, provider_key.replace("_", " ").title())


def _get_user_from_provider(provider: str, token: dict[str, Any]) -> dict[str, Any]:
    oauth = current_app.extensions["authlib.integrations.flask_client"]
    if provider == "google":
        client = oauth.create_client(provider)
        userinfo = client.parse_id_token(token)
        if userinfo:
            return userinfo
        return client.get("userinfo").json()
    if provider == "github":
        client = oauth.create_client(provider)
        profile = client.get("user").json()
        emails = client.get("user/emails").json()
        primary_email = None
        for item in emails:
            if item.get("primary"):
                primary_email = item.get("email")
                break
        if primary_email and not profile.get("email"):
            profile["email"] = primary_email
        return profile
    if provider == "discord":
        client = oauth.create_client(provider)
        return client.get("users/@me").json()
    raise ValueError(f"Unsupported OAuth provider: {provider}")


def _avatar_url_from_profile(provider: str, profile: dict[str, Any]) -> Optional[str]:
    picture = profile.get("picture")
    if isinstance(picture, str) and picture:
        return picture
    avatar_url = profile.get("avatar_url")
    if isinstance(avatar_url, str) and avatar_url:
        return avatar_url
    avatar = profile.get("avatar")
    if provider == "discord":
        user_id = profile.get("id")
        if isinstance(avatar, str) and avatar and isinstance(user_id, str) and user_id:
            extension = "gif" if avatar.startswith("a_") else "png"
            return f"https://cdn.discordapp.com/avatars/{user_id}/{avatar}.{extension}"
        return None
    if isinstance(avatar, str) and avatar:
        return avatar
    return None


def _update_user_from_profile(user: UserAccount, provider: str, profile: dict[str, Any]) -> None:
    user.email = profile.get("email") or user.email
    user.name = profile.get("name") or profile.get("username") or profile.get("login") or user.name
    user.given_name = profile.get("given_name") or user.given_name
    user.family_name = profile.get("family_name") or user.family_name
    user.locale = profile.get("locale") or user.locale
    user.avatar_url = _avatar_url_from_profile(provider, profile) or user.avatar_url


def _upsert_user_from_oauth(provider: str, profile: dict[str, Any]) -> UserAccount:
    from datetime import datetime, UTC
    provider_user_id = str(profile.get("sub") or profile.get("id") or "")
    if not provider_user_id:
        raise ValueError(f"OAuth profile from {provider} missing user identifier (sub/id).")
    email = profile.get("email")
    if not email:
        logger.warning(f"OAuth profile from {provider} missing email for user {provider_user_id}")

    existing_provider = UserProvider.query.filter_by(
        provider=provider,
        provider_user_id=provider_user_id,
    ).first()
    now = datetime.now(UTC)

    if existing_provider:
        user = db.session.get(UserAccount, existing_provider.user_id)
        existing_provider.raw_profile = profile
        existing_provider.email = profile.get("email")
        existing_provider.last_login_at = now
        if user:
            user.last_login_at = now
            _update_user_from_profile(user, provider, profile)
            db.session.commit()
            return user

    user = _new_model(
        UserAccount,
        email=profile.get("email"),
        name=profile.get("name") or profile.get("username") or profile.get("login"),
        given_name=profile.get("given_name"),
        family_name=profile.get("family_name"),
        locale=profile.get("locale"),
        avatar_url=_avatar_url_from_profile(provider, profile),
        last_login_at=now,
    )
    db.session.add(user)
    db.session.commit()

    provider_row = _new_model(
        UserProvider,
        user_id=user.id,
        provider=provider,
        provider_user_id=provider_user_id,
        email=profile.get("email"),
        raw_profile=profile,
        last_login_at=now,
    )
    db.session.add(provider_row)
    db.session.commit()
    return user


def get_or_create_api_key(user: UserAccount, name: Optional[str] = None) -> str:
    import hashlib
    api_key_secret = os.environ.get("PLANEXE_API_KEY_SECRET", "dev-api-key-secret")
    if api_key_secret == "dev-api-key-secret":
        logger.warning("PLANEXE_API_KEY_SECRET not set. Using dev secret for API key hashing.")

    active_count = UserApiKey.query.filter_by(user_id=user.id, revoked_at=None).count()
    if active_count >= 10:
        return ""

    raw_key = f"pex_{secrets.token_urlsafe(24)}"
    key_hash = hashlib.sha256(f"{api_key_secret}:{raw_key}".encode("utf-8")).hexdigest()
    key_prefix = raw_key[:10]
    api_key_show_once = current_app.config.get("API_KEY_SHOW_ONCE", False)
    sanitized_name = (name or "").strip()[:128] or None
    api_key = _new_model(
        UserApiKey,
        user_id=user.id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        name=sanitized_name,
        key_plaintext=raw_key if not api_key_show_once else None,
    )
    db.session.add(api_key)
    db.session.commit()
    return raw_key


# Import User class from app module to avoid circular imports at module level.
# The User class is defined in app.py and registered with Flask-Login there.


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        admin_username = current_app.config["ADMIN_USERNAME"]
        admin_password = current_app.config["ADMIN_PASSWORD"]
        if username == admin_username and password == admin_password:
            session.pop("open_access_logged_out", None)
            session["auth_provider"] = "password"
            from src.app import User
            user = User(admin_username, is_admin=True)
            login_user(user)
            return redirect(url_for("index"))
        return "Invalid credentials", 401
    oauth_providers = current_app.config.get("OAUTH_PROVIDERS", [])
    return render_template(
        "login.html",
        oauth_providers=oauth_providers,
        oauth_provider_labels=AUTH_PROVIDER_LABELS,
        telegram_enabled=bool(os.environ.get("PLANEXE_TELEGRAM_BOT_TOKEN")),
        telegram_login_url=os.environ.get("PLANEXE_TELEGRAM_LOGIN_URL") or None,
    )


@auth_bp.route("/api/oauth-redirect-uri")
def oauth_redirect_uri_debug():
    oauth_providers = current_app.config.get("OAUTH_PROVIDERS", [])
    lines = [
        f"PLANEXE_FRONTEND_MULTIUSER_PUBLIC_URL={current_app.config.get('PUBLIC_BASE_URL') or '(not set)'}",
        f"redirect_uri={_oauth_redirect_url('google') if 'google' in oauth_providers else '(google not configured)'}",
    ]
    body = "\n".join(lines)
    return body, 200, {"Content-Type": "text/plain; charset=utf-8"}


@auth_bp.route("/login/<provider>")
def oauth_login(provider: str):
    oauth_providers = current_app.config.get("OAUTH_PROVIDERS", [])
    if provider not in oauth_providers:
        abort(404)
    oauth = current_app.extensions["authlib.integrations.flask_client"]
    client = oauth.create_client(provider)
    redirect_uri = _oauth_redirect_url(provider)
    if provider == "google":
        nonce = secrets.token_urlsafe(16)
        session["oauth_google_nonce"] = nonce
        return client.authorize_redirect(redirect_uri, nonce=nonce)
    return client.authorize_redirect(redirect_uri)


@auth_bp.route("/auth/<provider>/callback")
def oauth_callback(provider: str):
    oauth_providers = current_app.config.get("OAUTH_PROVIDERS", [])
    if provider not in oauth_providers:
        abort(404)

    try:
        oauth = current_app.extensions["authlib.integrations.flask_client"]
        client = oauth.create_client(provider)
        token = client.authorize_access_token()

        if provider == "google":
            nonce = session.pop("oauth_google_nonce", None)
            profile = client.parse_id_token(token, nonce=nonce)
            if not profile:
                profile = client.get("userinfo").json()
        else:
            profile = _get_user_from_provider(provider, token)

        user = _upsert_user_from_oauth(provider, profile)
        session.pop("open_access_logged_out", None)
        session["auth_provider"] = provider
        from src.app import User
        login_user(User(user.id, is_admin=user.is_admin))
        has_key = UserApiKey.query.filter_by(user_id=user.id, revoked_at=None).first() is not None
        if not has_key:
            new_api_key = get_or_create_api_key(user, name="Default")
            if new_api_key:
                session["new_api_key"] = new_api_key
        return redirect(url_for("account"))

    except Exception as e:
        logger.error(f"OAuth callback error for {provider}: {e}", exc_info=True)
        return render_template(
            "login.html",
            error="Authentication failed. Please try again or contact support.",
            oauth_providers=oauth_providers,
            oauth_provider_labels=AUTH_PROVIDER_LABELS,
            telegram_enabled=bool(os.environ.get("PLANEXE_TELEGRAM_BOT_TOKEN")),
            telegram_login_url=os.environ.get("PLANEXE_TELEGRAM_LOGIN_URL") or None,
        ), 401


@auth_bp.route("/logout")
@login_required
def logout():
    session["open_access_logged_out"] = True
    session.pop("auth_provider", None)
    logout_user()
    return redirect(url_for("index"))
