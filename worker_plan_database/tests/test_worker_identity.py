import unittest

from worker_plan_database.worker_identity import resolve_and_set_worker_id, resolve_worker_id


class TestWorkerIdentity(unittest.TestCase):
    def test_uses_planexe_worker_id_when_set(self):
        env = {"PLANEXE_WORKER_ID": "worker-123"}
        self.assertEqual(resolve_worker_id(env), "worker-123")

    def test_builds_from_railway_replica_vars(self):
        env = {"RAILWAY_REPLICA_REGION": "europe-west4", "RAILWAY_REPLICA_ID": "2"}
        self.assertEqual(resolve_worker_id(env), "europe-west4_2")

    def test_prefers_explicit_over_railway_values(self):
        env = {
            "PLANEXE_WORKER_ID": "explicit",
            "RAILWAY_REPLICA_REGION": "europe-west4",
            "RAILWAY_REPLICA_ID": "2",
        }
        self.assertEqual(resolve_worker_id(env), "explicit")

    def test_raises_when_missing_all_identity_inputs(self):
        with self.assertRaises(ValueError):
            resolve_worker_id({})

    def test_sets_planexe_worker_id_after_resolution(self):
        env = {"RAILWAY_REPLICA_REGION": "us-west1", "RAILWAY_REPLICA_ID": "7"}
        worker_id = resolve_and_set_worker_id(env)
        self.assertEqual(worker_id, "us-west1_7")
        self.assertEqual(env["PLANEXE_WORKER_ID"], "us-west1_7")


if __name__ == "__main__":
    unittest.main()
