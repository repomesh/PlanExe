"""Check whether a user_id belongs to a MachAI iframe user."""
import logging
import os
import uuid

from database_api.planexe_db_singleton import db
from database_api.model_user_account import UserAccount

logger = logging.getLogger(__name__)


def is_machai_user(user_id: str) -> bool:
    """Return True if *user_id* belongs to a MachAI iframe user.

    Registered users (home.planexe.org sign-ups, docker admin) use UUID
    identifiers and exist in the UserAccount table.  MachAI iframe users
    use opaque, non-UUID strings and are *not* in the table.

    Must be called inside a Flask app context.
    """
    # Registered users and admins use UUIDs as their user_id.
    try:
        user_uuid = uuid.UUID(str(user_id))
        user = db.session.get(UserAccount, user_uuid)
        if user is not None:
            logger.debug("is_machai_user: user_id %r found in database — not a MachAI user.", user_id)
            return False
    except (ValueError, AttributeError):
        pass

    # Fallback admin username (non-UUID string like "admin").
    admin_username = os.environ.get("PLANEXE_FRONTEND_MULTIUSER_ADMIN_USERNAME", "")
    if admin_username and user_id == admin_username:
        logger.debug("is_machai_user: user_id %r matches admin username — not a MachAI user.", user_id)
        return False

    # Unknown user — likely a MachAI iframe user.
    logger.debug("is_machai_user: user_id %r is unknown — treating as MachAI user.", user_id)
    return True
