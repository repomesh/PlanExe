"""Feedback submitted by MCP clients about plan quality, workflow, or the interface."""
import uuid
from datetime import datetime, UTC
from database_api.planexe_db_singleton import db


class FeedbackItem(db.Model):
    __tablename__ = "feedback_item"

    # Server-generated UUID.
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # When the feedback was received (UTC).
    received_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(UTC), index=True)

    # Feedback category (one of the 12 defined categories).
    category = db.Column(db.String(32), nullable=False)

    # Free-text feedback message.
    message = db.Column(db.Text, nullable=False)

    # Optional plan UUID this feedback is about.
    plan_id = db.Column(db.String(36), nullable=True)

    # Optional satisfaction score (1-5).
    rating = db.Column(db.Integer, nullable=True)

    # User who submitted the feedback (resolved from auth context).
    user_id = db.Column(db.String(36), nullable=True)

    # Inline snapshot of the plan state at feedback time.
    plan_progress_pct = db.Column(db.Float, nullable=True)
    plan_state = db.Column(db.String(16), nullable=True)
    plan_current_step = db.Column(db.String(128), nullable=True)

    def __repr__(self):
        return f"<FeedbackItem(id={self.id}, category='{self.category}', received_at='{self.received_at}')>"
