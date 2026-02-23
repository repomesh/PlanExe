import unittest

import mcp_cloud.app as cloud_app
import mcp_local.planexe_mcp_local as local_app


def _tool_desc(tool_defs, name: str) -> str:
    for definition in tool_defs:
        if definition.name == name:
            return definition.description
    raise AssertionError(f"Tool not found: {name}")


class TestCloudToolSurfaceConsistency(unittest.TestCase):
    def test_cloud_exposes_task_file_info_not_task_download(self):
        cloud_tool_names = {definition.name for definition in cloud_app.TOOL_DEFINITIONS}
        self.assertIn("task_file_info", cloud_tool_names)
        self.assertNotIn("task_download", cloud_tool_names)

    def test_cloud_instructions_reference_cloud_download_tool(self):
        self.assertIn("task_file_info", cloud_app.PLANEXE_SERVER_INSTRUCTIONS)
        self.assertNotIn("task_download", cloud_app.PLANEXE_SERVER_INSTRUCTIONS)

    def test_cloud_task_create_description_references_cloud_download_tool(self):
        description = _tool_desc(cloud_app.TOOL_DEFINITIONS, "task_create")
        self.assertIn("task_file_info", description)
        self.assertNotIn("task_download", description)

    def test_cloud_instructions_include_task_status_state_contract(self):
        instructions = cloud_app.PLANEXE_SERVER_INSTRUCTIONS
        self.assertIn("running/stopping", instructions)
        self.assertIn("completed", instructions)
        self.assertIn("failed", instructions)
        self.assertIn("stopped", instructions)
        self.assertIn("pending for longer than 5 minutes", instructions)
        self.assertIn("longer than 20 minutes", instructions)
        self.assertIn("PlanExeOrg/PlanExe/issues", instructions)

    def test_cloud_task_status_description_includes_state_contract(self):
        description = _tool_desc(cloud_app.TOOL_DEFINITIONS, "task_status")
        self.assertIn("running/stopping", description)
        self.assertIn("completed", description)
        self.assertIn("failed", description)
        self.assertIn("stopped", description)
        self.assertIn("pending for >5 minutes", description)
        self.assertIn(">20 minutes", description)
        self.assertIn("PlanExeOrg/PlanExe/issues", description)


class TestLocalToolSurfaceConsistency(unittest.TestCase):
    def test_local_exposes_task_download_not_task_file_info(self):
        local_tool_names = {definition.name for definition in local_app.TOOL_DEFINITIONS}
        self.assertIn("task_download", local_tool_names)
        self.assertNotIn("task_file_info", local_tool_names)

    def test_local_instructions_reference_local_download_tool(self):
        self.assertIn("task_download", local_app.PLANEXE_SERVER_INSTRUCTIONS)
        self.assertNotIn("task_file_info", local_app.PLANEXE_SERVER_INSTRUCTIONS)

    def test_local_task_create_description_references_local_download_tool(self):
        description = _tool_desc(local_app.TOOL_DEFINITIONS, "task_create")
        self.assertIn("task_download", description)
        self.assertNotIn("task_file_info", description)

    def test_local_instructions_include_task_status_state_contract(self):
        instructions = local_app.PLANEXE_SERVER_INSTRUCTIONS
        self.assertIn("running/stopping", instructions)
        self.assertIn("completed", instructions)
        self.assertIn("failed", instructions)
        self.assertIn("stopped", instructions)
        self.assertIn("pending for longer than 5 minutes", instructions)
        self.assertIn("longer than 20 minutes", instructions)
        self.assertIn("PlanExeOrg/PlanExe/issues", instructions)

    def test_local_task_status_description_includes_state_contract(self):
        description = _tool_desc(local_app.TOOL_DEFINITIONS, "task_status")
        self.assertIn("running/stopping", description)
        self.assertIn("completed", description)
        self.assertIn("failed", description)
        self.assertIn("stopped", description)
        self.assertIn("pending for >5 minutes", description)
        self.assertIn(">20 minutes", description)
        self.assertIn("PlanExeOrg/PlanExe/issues", description)


if __name__ == "__main__":
    unittest.main()
