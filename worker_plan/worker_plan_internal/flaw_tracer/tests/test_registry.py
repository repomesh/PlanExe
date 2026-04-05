# worker_plan/worker_plan_internal/flaw_tracer/tests/test_registry.py
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from worker_plan_internal.flaw_tracer.registry import (
    StageInfo,
    STAGES,
    find_stage_by_filename,
    get_upstream_files,
    get_source_code_paths,
)


class TestStageInfo(unittest.TestCase):
    def test_stages_is_nonempty(self):
        self.assertGreater(len(STAGES), 40)

    def test_all_stages_have_required_fields(self):
        for stage in STAGES:
            self.assertIsInstance(stage.name, str, f"{stage.name} name")
            self.assertIsInstance(stage.output_files, tuple, f"{stage.name} output_files")
            self.assertTrue(len(stage.output_files) > 0, f"{stage.name} has no output_files")
            self.assertIsInstance(stage.upstream_stages, tuple, f"{stage.name} upstream_stages")
            self.assertIsInstance(stage.source_code_files, tuple, f"{stage.name} source_code_files")
            self.assertIsInstance(stage.primary_output, str, f"{stage.name} primary_output")
            self.assertIn(stage.primary_output, stage.output_files, f"{stage.name} primary_output not in output_files")

    def test_no_duplicate_stage_names(self):
        names = [s.name for s in STAGES]
        self.assertEqual(len(names), len(set(names)))

    def test_upstream_references_are_valid(self):
        valid_names = {s.name for s in STAGES}
        for stage in STAGES:
            for upstream in stage.upstream_stages:
                self.assertIn(upstream, valid_names, f"{stage.name} references unknown upstream '{upstream}'")


class TestFindStageByFilename(unittest.TestCase):
    def test_find_report(self):
        stage = find_stage_by_filename("030-report.html")
        self.assertIsNotNone(stage)
        self.assertEqual(stage.name, "report")

    def test_find_potential_levers_clean(self):
        stage = find_stage_by_filename("002-10-potential_levers.json")
        self.assertIsNotNone(stage)
        self.assertEqual(stage.name, "potential_levers")

    def test_find_potential_levers_raw(self):
        stage = find_stage_by_filename("002-9-potential_levers_raw.json")
        self.assertIsNotNone(stage)
        self.assertEqual(stage.name, "potential_levers")

    def test_find_executive_summary(self):
        stage = find_stage_by_filename("025-2-executive_summary.md")
        self.assertIsNotNone(stage)
        self.assertEqual(stage.name, "executive_summary")

    def test_unknown_filename_returns_none(self):
        stage = find_stage_by_filename("zzz-unknown.txt")
        self.assertIsNone(stage)


class TestGetUpstreamFiles(unittest.TestCase):
    def test_setup_has_no_upstream(self):
        with TemporaryDirectory() as d:
            result = get_upstream_files("setup", Path(d))
            self.assertEqual(result, [])

    def test_potential_levers_upstream(self):
        with TemporaryDirectory() as d:
            output_dir = Path(d)
            # Create the expected upstream files on disk
            (output_dir / "001-2-plan.txt").write_text("plan", encoding="utf-8")
            (output_dir / "002-6-identify_purpose.md").write_text("purpose", encoding="utf-8")
            (output_dir / "002-8-plan_type.md").write_text("type", encoding="utf-8")
            (output_dir / "002-0-extract_constraints.md").write_text("constraints", encoding="utf-8")

            result = get_upstream_files("potential_levers", output_dir)
            stage_names = [name for name, _ in result]
            self.assertIn("setup", stage_names)
            self.assertIn("identify_purpose", stage_names)
            self.assertIn("plan_type", stage_names)
            self.assertIn("extract_constraints", stage_names)

    def test_missing_files_are_skipped(self):
        with TemporaryDirectory() as d:
            output_dir = Path(d)
            # Only create one of the upstream files
            (output_dir / "001-2-plan.txt").write_text("plan", encoding="utf-8")

            result = get_upstream_files("potential_levers", output_dir)
            stage_names = [name for name, _ in result]
            self.assertIn("setup", stage_names)
            # The others should be skipped because their files don't exist
            self.assertNotIn("identify_purpose", stage_names)


class TestGetSourceCodePaths(unittest.TestCase):
    def test_potential_levers_source(self):
        paths = get_source_code_paths("potential_levers")
        filenames = [p.name for p in paths]
        self.assertIn("potential_levers.py", filenames)
        self.assertIn("identify_potential_levers.py", filenames)

    def test_unknown_stage_returns_empty(self):
        paths = get_source_code_paths("nonexistent_stage")
        self.assertEqual(paths, [])
