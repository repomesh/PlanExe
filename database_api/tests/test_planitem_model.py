import unittest

from flask import Flask

from database_api.planexe_db_singleton import db
from database_api.model_planitem import PlanItem, PlanState


class TestPlanItemModel(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        self.app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        db.init_app(self.app)
        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_stop_request_fields_default(self):
        with self.app.app_context():
            task = PlanItem(
                state=PlanState.pending,
                prompt="Test prompt",
                user_id="test_user",
            )
            db.session.add(task)
            db.session.commit()

            fetched = db.session.get(PlanItem, task.id)
            self.assertIsNotNone(fetched)
            self.assertTrue(hasattr(fetched, "stop_requested"))
            self.assertTrue(hasattr(fetched, "stop_requested_timestamp"))
            self.assertTrue(hasattr(fetched, "run_track_activity_jsonl"))
            self.assertTrue(hasattr(fetched, "run_track_activity_bytes"))
            self.assertTrue(hasattr(fetched, "run_activity_overview_json"))
            self.assertTrue(hasattr(fetched, "run_artifact_layout_version"))
            self.assertFalse(bool(fetched.stop_requested))

    def test_prompt_invalid_bytes_are_sanitized(self):
        with self.app.app_context():
            bad_bytes = b"Hello \xe2\x80 world"
            task = PlanItem(
                state=PlanState.pending,
                prompt=bad_bytes,
                user_id="test_user",
            )
            db.session.add(task)
            db.session.commit()

            fetched = db.session.get(PlanItem, task.id)
            self.assertIsInstance(fetched.prompt, str)
            # Must be encodable after sanitization.
            fetched.prompt.encode("utf-8")
            self.assertIn("Hello", fetched.prompt)
            self.assertIn("world", fetched.prompt)

    def test_prompt_surrogates_are_sanitized(self):
        with self.app.app_context():
            task = PlanItem(
                state=PlanState.pending,
                prompt="prefix \ud800 suffix",
                user_id="test_user",
            )
            db.session.add(task)
            db.session.commit()

            fetched = db.session.get(PlanItem, task.id)
            self.assertIsInstance(fetched.prompt, str)
            fetched.prompt.encode("utf-8")
            self.assertFalse(any(0xD800 <= ord(ch) <= 0xDFFF for ch in fetched.prompt))
