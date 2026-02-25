import unittest

import mcp_cloud.app as cloud_app
import mcp_local.planexe_mcp_local as local_app


def _tool_desc(tool_defs, name: str) -> str:
    for definition in tool_defs:
        if definition.name == name:
            return definition.description
    raise AssertionError(f"Tool not found: {name}")


def _tool_def(tool_defs, name: str):
    for definition in tool_defs:
        if definition.name == name:
            return definition
    raise AssertionError(f"Tool not found: {name}")


class TestAllToolsHaveOutputSchema(unittest.TestCase):
    """Every tool must declare an output_schema so callers know the response shape."""

    def test_cloud_all_tools_have_output_schema(self):
        for definition in cloud_app.TOOL_DEFINITIONS:
            with self.subTest(tool=definition.name):
                self.assertIsNotNone(
                    definition.output_schema,
                    f"Cloud tool {definition.name!r} is missing output_schema",
                )

    def test_local_all_tools_have_output_schema(self):
        for definition in local_app.TOOL_DEFINITIONS:
            with self.subTest(tool=definition.name):
                self.assertIsNotNone(
                    definition.output_schema,
                    f"Local tool {definition.name!r} is missing output_schema",
                )


class TestTaskCreateInputSchemaHasUserApiKey(unittest.TestCase):
    """user_api_key must be in the visible task_create input schema."""

    def test_cloud_task_create_schema_has_user_api_key(self):
        props = cloud_app.TASK_CREATE_INPUT_SCHEMA.get("properties", {})
        self.assertIn("user_api_key", props)

    def test_local_task_create_schema_has_user_api_key(self):
        props = local_app.TASK_CREATE_INPUT_SCHEMA.get("properties", {})
        self.assertIn("user_api_key", props)


class TestTaskListInputSchemaHasUserApiKey(unittest.TestCase):
    """user_api_key must be required in the task_list input schema."""

    def test_cloud_task_list_schema_requires_user_api_key(self):
        props = cloud_app.TASK_LIST_INPUT_SCHEMA.get("properties", {})
        self.assertIn("user_api_key", props)
        required = cloud_app.TASK_LIST_INPUT_SCHEMA.get("required", [])
        self.assertIn("user_api_key", required)

    def test_local_task_list_schema_requires_user_api_key(self):
        props = local_app.TASK_LIST_INPUT_SCHEMA.get("properties", {})
        self.assertIn("user_api_key", props)
        required = local_app.TASK_LIST_INPUT_SCHEMA.get("required", [])
        self.assertIn("user_api_key", required)


class TestTaskRetryInputSchemaDefaults(unittest.TestCase):
    """task_retry should default model_profile to baseline."""

    def test_cloud_task_retry_schema_defaults_model_profile(self):
        props = cloud_app.TASK_RETRY_INPUT_SCHEMA.get("properties", {})
        model_profile = props.get("model_profile", {})
        self.assertEqual(model_profile.get("default"), "baseline")

    def test_local_task_retry_schema_defaults_model_profile(self):
        props = local_app.TASK_RETRY_INPUT_SCHEMA.get("properties", {})
        model_profile = props.get("model_profile", {})
        self.assertEqual(model_profile.get("default"), "baseline")


class TestPromptExamplesAnnotations(unittest.TestCase):
    def test_cloud_prompt_examples_annotations(self):
        definition = _tool_def(cloud_app.TOOL_DEFINITIONS, "prompt_examples")
        annotations = definition.annotations or {}
        self.assertTrue(annotations.get("readOnlyHint"))
        self.assertFalse(annotations.get("destructiveHint"))
        self.assertTrue(annotations.get("idempotentHint"))
        self.assertFalse(annotations.get("openWorldHint"))

    def test_local_prompt_examples_annotations(self):
        definition = _tool_def(local_app.TOOL_DEFINITIONS, "prompt_examples")
        annotations = definition.annotations or {}
        self.assertTrue(annotations.get("readOnlyHint"))
        self.assertFalse(annotations.get("destructiveHint"))
        self.assertTrue(annotations.get("idempotentHint"))
        self.assertFalse(annotations.get("openWorldHint"))


class TestModelProfilesAnnotations(unittest.TestCase):
    def test_cloud_model_profiles_annotations(self):
        definition = _tool_def(cloud_app.TOOL_DEFINITIONS, "model_profiles")
        annotations = definition.annotations or {}
        self.assertTrue(annotations.get("readOnlyHint"))
        self.assertFalse(annotations.get("destructiveHint"))
        self.assertTrue(annotations.get("idempotentHint"))
        self.assertFalse(annotations.get("openWorldHint"))

    def test_local_model_profiles_annotations(self):
        definition = _tool_def(local_app.TOOL_DEFINITIONS, "model_profiles")
        annotations = definition.annotations or {}
        self.assertTrue(annotations.get("readOnlyHint"))
        self.assertFalse(annotations.get("destructiveHint"))
        self.assertTrue(annotations.get("idempotentHint"))
        self.assertFalse(annotations.get("openWorldHint"))


class TestRemainingToolAnnotations(unittest.TestCase):
    def test_cloud_remaining_tool_annotations(self):
        expected = {
            "task_create": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
            "task_status": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
            "task_stop": {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": False},
            "task_retry": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
            "task_file_info": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
            "task_list": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
        }
        for tool_name, expected_annotations in expected.items():
            with self.subTest(tool=tool_name):
                definition = _tool_def(cloud_app.TOOL_DEFINITIONS, tool_name)
                self.assertEqual(definition.annotations, expected_annotations)

    def test_local_remaining_tool_annotations(self):
        expected = {
            "task_create": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
            "task_status": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
            "task_stop": {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": False},
            "task_retry": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
            "task_download": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
            "task_list": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
        }
        for tool_name, expected_annotations in expected.items():
            with self.subTest(tool=tool_name):
                definition = _tool_def(local_app.TOOL_DEFINITIONS, tool_name)
                self.assertEqual(definition.annotations, expected_annotations)


class TestCloudToolSurfaceConsistency(unittest.TestCase):
    def test_cloud_exposes_model_profiles_tool(self):
        cloud_tool_names = {definition.name for definition in cloud_app.TOOL_DEFINITIONS}
        self.assertIn("model_profiles", cloud_tool_names)

    def test_cloud_exposes_task_retry_tool(self):
        cloud_tool_names = {definition.name for definition in cloud_app.TOOL_DEFINITIONS}
        self.assertIn("task_retry", cloud_tool_names)

    def test_cloud_exposes_task_file_info_not_task_download(self):
        cloud_tool_names = {definition.name for definition in cloud_app.TOOL_DEFINITIONS}
        self.assertIn("task_file_info", cloud_tool_names)
        self.assertNotIn("task_download", cloud_tool_names)

    def test_cloud_exposes_task_list_tool(self):
        cloud_tool_names = {definition.name for definition in cloud_app.TOOL_DEFINITIONS}
        self.assertIn("task_list", cloud_tool_names)

    def test_cloud_instructions_reference_cloud_download_tool(self):
        self.assertIn("task_file_info", cloud_app.PLANEXE_SERVER_INSTRUCTIONS)
        self.assertNotIn("task_download", cloud_app.PLANEXE_SERVER_INSTRUCTIONS)

    def test_cloud_task_create_description_references_cloud_download_tool(self):
        description = _tool_desc(cloud_app.TOOL_DEFINITIONS, "task_create")
        self.assertIn("task_file_info", description)
        self.assertNotIn("task_download", description)

    def test_cloud_instructions_include_task_status_state_contract(self):
        instructions = cloud_app.PLANEXE_SERVER_INSTRUCTIONS
        self.assertIn("pending/processing", instructions)
        self.assertIn("completed", instructions)
        self.assertIn("failed", instructions)
        self.assertNotIn("running/stopping", instructions)
        self.assertIn("pending for longer than 5 minutes", instructions)
        self.assertIn("longer than 20 minutes", instructions)
        self.assertIn("PlanExeOrg/PlanExe/issues", instructions)

    def test_cloud_task_status_description_includes_state_contract(self):
        description = _tool_desc(cloud_app.TOOL_DEFINITIONS, "task_status")
        self.assertIn("pending/processing", description)
        self.assertIn("completed", description)
        self.assertIn("failed", description)
        self.assertNotIn("running/stopping", description)
        self.assertIn("pending for >5 minutes", description)
        self.assertIn(">20 minutes", description)
        self.assertIn("PlanExeOrg/PlanExe/issues", description)

    def test_cloud_instructions_include_model_profiles_unavailable_guidance(self):
        instructions = cloud_app.PLANEXE_SERVER_INSTRUCTIONS
        self.assertIn("MODEL_PROFILES_UNAVAILABLE", instructions)

    def test_cloud_prompt_schema_includes_prompt_shape_guidance(self):
        prompt_schema = cloud_app.TASK_CREATE_INPUT_SCHEMA["properties"]["prompt"]["description"]
        self.assertIn("300-800 words", prompt_schema)
        self.assertIn("objective, scope, constraints, timeline, stakeholders, budget/resources, and success criteria", prompt_schema)


class TestLocalToolSurfaceConsistency(unittest.TestCase):
    def test_local_exposes_model_profiles_tool(self):
        local_tool_names = {definition.name for definition in local_app.TOOL_DEFINITIONS}
        self.assertIn("model_profiles", local_tool_names)

    def test_local_exposes_task_retry_tool(self):
        local_tool_names = {definition.name for definition in local_app.TOOL_DEFINITIONS}
        self.assertIn("task_retry", local_tool_names)

    def test_local_exposes_task_download_not_task_file_info(self):
        local_tool_names = {definition.name for definition in local_app.TOOL_DEFINITIONS}
        self.assertIn("task_download", local_tool_names)
        self.assertNotIn("task_file_info", local_tool_names)

    def test_local_exposes_task_list_tool(self):
        local_tool_names = {definition.name for definition in local_app.TOOL_DEFINITIONS}
        self.assertIn("task_list", local_tool_names)

    def test_local_instructions_reference_local_download_tool(self):
        self.assertIn("task_download", local_app.PLANEXE_SERVER_INSTRUCTIONS)
        self.assertNotIn("task_file_info", local_app.PLANEXE_SERVER_INSTRUCTIONS)

    def test_local_task_create_description_references_local_download_tool(self):
        description = _tool_desc(local_app.TOOL_DEFINITIONS, "task_create")
        self.assertIn("task_download", description)
        self.assertNotIn("task_file_info", description)

    def test_local_instructions_include_task_status_state_contract(self):
        instructions = local_app.PLANEXE_SERVER_INSTRUCTIONS
        self.assertIn("pending/processing", instructions)
        self.assertIn("completed", instructions)
        self.assertIn("failed", instructions)
        self.assertNotIn("running/stopping", instructions)
        self.assertIn("pending for longer than 5 minutes", instructions)
        self.assertIn("longer than 20 minutes", instructions)
        self.assertIn("PlanExeOrg/PlanExe/issues", instructions)

    def test_local_task_status_description_includes_state_contract(self):
        description = _tool_desc(local_app.TOOL_DEFINITIONS, "task_status")
        self.assertIn("pending/processing", description)
        self.assertIn("completed", description)
        self.assertIn("failed", description)
        self.assertNotIn("running/stopping", description)
        self.assertIn("pending for >5 minutes", description)
        self.assertIn(">20 minutes", description)
        self.assertIn("PlanExeOrg/PlanExe/issues", description)

    def test_local_instructions_include_model_profiles_unavailable_guidance(self):
        instructions = local_app.PLANEXE_SERVER_INSTRUCTIONS
        self.assertIn("MODEL_PROFILES_UNAVAILABLE", instructions)


if __name__ == "__main__":
    unittest.main()
