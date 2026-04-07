# worker_plan/worker_plan_internal/flaw_tracer/tests/test_registry.py
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from worker_plan_internal.flaw_tracer.registry import (
    NodeInfo,
    NODES,
    find_node_by_filename,
    get_upstream_files,
    get_source_code_paths,
)


class TestNodeInfo(unittest.TestCase):
    def test_nodes_is_nonempty(self):
        self.assertGreater(len(NODES), 40)

    def test_all_nodes_have_required_fields(self):
        for node in NODES:
            self.assertIsInstance(node.name, str, f"{node.name} name")
            self.assertIsInstance(node.output_files, tuple, f"{node.name} output_files")
            self.assertTrue(len(node.output_files) > 0, f"{node.name} has no output_files")
            self.assertIsInstance(node.depends_on, tuple, f"{node.name} depends_on")
            self.assertIsInstance(node.source_code_files, tuple, f"{node.name} source_code_files")
            self.assertIsInstance(node.primary_output, str, f"{node.name} primary_output")
            self.assertIn(node.primary_output, node.output_files, f"{node.name} primary_output not in output_files")

    def test_no_duplicate_node_names(self):
        names = [n.name for n in NODES]
        self.assertEqual(len(names), len(set(names)))

    def test_upstream_references_are_valid(self):
        valid_names = {n.name for n in NODES}
        for node in NODES:
            for upstream in node.depends_on:
                self.assertIn(upstream, valid_names, f"{node.name} references unknown upstream '{upstream}'")


class TestFindNodeByFilename(unittest.TestCase):
    def test_find_report(self):
        node = find_node_by_filename("030-report.html")
        self.assertIsNotNone(node)
        self.assertEqual(node.name, "report")

    def test_find_potential_levers_clean(self):
        node = find_node_by_filename("002-10-potential_levers.json")
        self.assertIsNotNone(node)
        self.assertEqual(node.name, "potential_levers")

    def test_find_potential_levers_raw(self):
        node = find_node_by_filename("002-9-potential_levers_raw.json")
        self.assertIsNotNone(node)
        self.assertEqual(node.name, "potential_levers")

    def test_find_executive_summary(self):
        node = find_node_by_filename("025-2-executive_summary.md")
        self.assertIsNotNone(node)
        self.assertEqual(node.name, "executive_summary")

    def test_unknown_filename_returns_none(self):
        node = find_node_by_filename("zzz-unknown.txt")
        self.assertIsNone(node)


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
            node_names = [name for name, _ in result]
            self.assertIn("setup", node_names)
            self.assertIn("identify_purpose", node_names)
            self.assertIn("plan_type", node_names)
            self.assertIn("extract_constraints", node_names)

    def test_missing_files_are_skipped(self):
        with TemporaryDirectory() as d:
            output_dir = Path(d)
            # Only create one of the upstream files
            (output_dir / "001-2-plan.txt").write_text("plan", encoding="utf-8")

            result = get_upstream_files("potential_levers", output_dir)
            node_names = [name for name, _ in result]
            self.assertIn("setup", node_names)
            # The others should be skipped because their files don't exist
            self.assertNotIn("identify_purpose", node_names)


class TestGetSourceCodePaths(unittest.TestCase):
    def test_potential_levers_source(self):
        paths = get_source_code_paths("potential_levers")
        filenames = [p.name for p in paths]
        self.assertIn("potential_levers.py", filenames)
        self.assertIn("identify_potential_levers.py", filenames)

    def test_unknown_node_returns_empty(self):
        paths = get_source_code_paths("nonexistent_node")
        self.assertEqual(paths, [])
