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


class TestPlanCreateInputSchemaHasUserApiKey(unittest.TestCase):
    """user_api_key must be in the visible plan_create input schema."""

    def test_cloud_plan_create_schema_has_user_api_key(self):
        props = cloud_app.PLAN_CREATE_INPUT_SCHEMA.get("properties", {})
        self.assertIn("user_api_key", props)

    def test_local_plan_create_schema_has_user_api_key(self):
        props = local_app.PLAN_CREATE_INPUT_SCHEMA.get("properties", {})
        self.assertIn("user_api_key", props)


class TestPlanListInputSchemaHasUserApiKey(unittest.TestCase):
    """user_api_key must be in plan_list input schema but NOT required."""

    def test_cloud_plan_list_schema_has_optional_user_api_key(self):
        props = cloud_app.PLAN_LIST_INPUT_SCHEMA.get("properties", {})
        self.assertIn("user_api_key", props)
        required = cloud_app.PLAN_LIST_INPUT_SCHEMA.get("required", [])
        self.assertNotIn("user_api_key", required)

    def test_local_plan_list_schema_has_optional_user_api_key(self):
        props = local_app.PLAN_LIST_INPUT_SCHEMA.get("properties", {})
        self.assertIn("user_api_key", props)
        required = local_app.PLAN_LIST_INPUT_SCHEMA.get("required", [])
        self.assertNotIn("user_api_key", required)


class TestPlanRetryInputSchemaDefaults(unittest.TestCase):
    """plan_retry should default model_profile to baseline."""

    def test_cloud_plan_retry_schema_defaults_model_profile(self):
        props = cloud_app.PLAN_RETRY_INPUT_SCHEMA.get("properties", {})
        model_profile = props.get("model_profile", {})
        self.assertEqual(model_profile.get("default"), "baseline")

    def test_local_plan_retry_schema_defaults_model_profile(self):
        props = local_app.PLAN_RETRY_INPUT_SCHEMA.get("properties", {})
        model_profile = props.get("model_profile", {})
        self.assertEqual(model_profile.get("default"), "baseline")


class TestExamplePromptsAnnotations(unittest.TestCase):
    def test_cloud_example_prompts_annotations(self):
        definition = _tool_def(cloud_app.TOOL_DEFINITIONS, "example_prompts")
        annotations = definition.annotations or {}
        self.assertTrue(annotations.get("readOnlyHint"))
        self.assertFalse(annotations.get("destructiveHint"))
        self.assertTrue(annotations.get("idempotentHint"))
        self.assertFalse(annotations.get("openWorldHint"))

    def test_local_example_prompts_annotations(self):
        definition = _tool_def(local_app.TOOL_DEFINITIONS, "example_prompts")
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
            "plan_create": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
            "plan_status": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
            "plan_stop": {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": False},
            "plan_retry": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
            "plan_file_info": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
            "plan_list": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
        }
        for tool_name, expected_annotations in expected.items():
            with self.subTest(tool=tool_name):
                definition = _tool_def(cloud_app.TOOL_DEFINITIONS, tool_name)
                self.assertEqual(definition.annotations, expected_annotations)

    def test_local_remaining_tool_annotations(self):
        expected = {
            "plan_create": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
            "plan_status": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
            "plan_stop": {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": False},
            "plan_retry": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
            "plan_download": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
            "plan_list": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
        }
        for tool_name, expected_annotations in expected.items():
            with self.subTest(tool=tool_name):
                definition = _tool_def(local_app.TOOL_DEFINITIONS, tool_name)
                self.assertEqual(definition.annotations, expected_annotations)


class TestExamplePlansAnnotations(unittest.TestCase):
    def test_cloud_example_plans_annotations(self):
        definition = _tool_def(cloud_app.TOOL_DEFINITIONS, "example_plans")
        annotations = definition.annotations or {}
        self.assertTrue(annotations.get("readOnlyHint"))
        self.assertFalse(annotations.get("destructiveHint"))
        self.assertTrue(annotations.get("idempotentHint"))
        self.assertFalse(annotations.get("openWorldHint"))

    def test_local_example_plans_annotations(self):
        definition = _tool_def(local_app.TOOL_DEFINITIONS, "example_plans")
        annotations = definition.annotations or {}
        self.assertTrue(annotations.get("readOnlyHint"))
        self.assertFalse(annotations.get("destructiveHint"))
        self.assertTrue(annotations.get("idempotentHint"))
        self.assertFalse(annotations.get("openWorldHint"))


class TestCloudToolSurfaceConsistency(unittest.TestCase):
    def test_cloud_exposes_example_plans_tool(self):
        cloud_tool_names = {definition.name for definition in cloud_app.TOOL_DEFINITIONS}
        self.assertIn("example_plans", cloud_tool_names)

    def test_cloud_exposes_model_profiles_tool(self):
        cloud_tool_names = {definition.name for definition in cloud_app.TOOL_DEFINITIONS}
        self.assertIn("model_profiles", cloud_tool_names)

    def test_cloud_exposes_plan_retry_tool(self):
        cloud_tool_names = {definition.name for definition in cloud_app.TOOL_DEFINITIONS}
        self.assertIn("plan_retry", cloud_tool_names)

    def test_cloud_exposes_plan_file_info_not_plan_download(self):
        cloud_tool_names = {definition.name for definition in cloud_app.TOOL_DEFINITIONS}
        self.assertIn("plan_file_info", cloud_tool_names)
        self.assertNotIn("plan_download", cloud_tool_names)

    def test_cloud_exposes_plan_list_tool(self):
        cloud_tool_names = {definition.name for definition in cloud_app.TOOL_DEFINITIONS}
        self.assertIn("plan_list", cloud_tool_names)

    def test_cloud_instructions_reference_cloud_download_tool(self):
        self.assertIn("plan_file_info", cloud_app.PLANEXE_SERVER_INSTRUCTIONS)
        self.assertNotIn("plan_download", cloud_app.PLANEXE_SERVER_INSTRUCTIONS)

    def test_cloud_plan_create_description_references_cloud_download_tool(self):
        description = _tool_desc(cloud_app.TOOL_DEFINITIONS, "plan_create")
        self.assertIn("plan_file_info", description)
        self.assertNotIn("plan_download", description)

    def test_cloud_instructions_include_plan_status_state_contract(self):
        instructions = cloud_app.PLANEXE_SERVER_INSTRUCTIONS
        self.assertIn("pending/processing", instructions)
        self.assertIn("completed", instructions)
        self.assertIn("failed", instructions)
        self.assertNotIn("running/stopping", instructions)
        self.assertIn("pending for longer than 5 minutes", instructions)
        self.assertIn("longer than 20 minutes", instructions)
        self.assertIn("PlanExeOrg/PlanExe/issues", instructions)

    def test_cloud_plan_status_description_includes_state_contract(self):
        description = _tool_desc(cloud_app.TOOL_DEFINITIONS, "plan_status")
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
        prompt_schema = cloud_app.PLAN_CREATE_INPUT_SCHEMA["properties"]["prompt"]["description"]
        self.assertIn("300-800 words", prompt_schema)
        self.assertIn("objective, scope, constraints, timeline, stakeholders, budget/resources, and success criteria", prompt_schema)


class TestLocalToolSurfaceConsistency(unittest.TestCase):
    def test_local_exposes_example_plans_tool(self):
        local_tool_names = {definition.name for definition in local_app.TOOL_DEFINITIONS}
        self.assertIn("example_plans", local_tool_names)

    def test_local_exposes_model_profiles_tool(self):
        local_tool_names = {definition.name for definition in local_app.TOOL_DEFINITIONS}
        self.assertIn("model_profiles", local_tool_names)

    def test_local_exposes_plan_retry_tool(self):
        local_tool_names = {definition.name for definition in local_app.TOOL_DEFINITIONS}
        self.assertIn("plan_retry", local_tool_names)

    def test_local_exposes_plan_download_not_plan_file_info(self):
        local_tool_names = {definition.name for definition in local_app.TOOL_DEFINITIONS}
        self.assertIn("plan_download", local_tool_names)
        self.assertNotIn("plan_file_info", local_tool_names)

    def test_local_exposes_plan_list_tool(self):
        local_tool_names = {definition.name for definition in local_app.TOOL_DEFINITIONS}
        self.assertIn("plan_list", local_tool_names)

    def test_local_instructions_reference_local_download_tool(self):
        self.assertIn("plan_download", local_app.PLANEXE_SERVER_INSTRUCTIONS)
        self.assertNotIn("plan_file_info", local_app.PLANEXE_SERVER_INSTRUCTIONS)

    def test_local_plan_create_description_references_local_download_tool(self):
        description = _tool_desc(local_app.TOOL_DEFINITIONS, "plan_create")
        self.assertIn("plan_download", description)
        self.assertNotIn("plan_file_info", description)

    def test_local_instructions_include_plan_status_state_contract(self):
        instructions = local_app.PLANEXE_SERVER_INSTRUCTIONS
        self.assertIn("pending/processing", instructions)
        self.assertIn("completed", instructions)
        self.assertIn("failed", instructions)
        self.assertNotIn("running/stopping", instructions)
        self.assertIn("pending for longer than 5 minutes", instructions)
        self.assertIn("longer than 20 minutes", instructions)
        self.assertIn("PlanExeOrg/PlanExe/issues", instructions)

    def test_local_plan_status_description_includes_state_contract(self):
        description = _tool_desc(local_app.TOOL_DEFINITIONS, "plan_status")
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


class TestFastMCPCanonicalOutputSchema(unittest.TestCase):
    """FastMCP tools must advertise the canonical outputSchema from TOOL_DEFINITIONS."""

    def test_fastmcp_tools_use_canonical_output_schema(self):
        from mcp_cloud.http_server import fastmcp_server

        for tool_def in cloud_app.TOOL_DEFINITIONS:
            if tool_def.output_schema is None:
                continue
            with self.subTest(tool=tool_def.name):
                fastmcp_tool = fastmcp_server._tool_manager.get_tool(tool_def.name)
                self.assertIsNotNone(
                    fastmcp_tool,
                    f"FastMCP tool {tool_def.name!r} not registered",
                )
                self.assertEqual(
                    fastmcp_tool.output_schema,
                    tool_def.output_schema,
                    f"FastMCP tool {tool_def.name!r} outputSchema does not match TOOL_DEFINITIONS",
                )

    def test_all_tool_definitions_registered_in_fastmcp(self):
        """Every tool in TOOL_DEFINITIONS must be registered in the FastMCP server."""
        from mcp_cloud.http_server import fastmcp_server

        for tool_def in cloud_app.TOOL_DEFINITIONS:
            with self.subTest(tool=tool_def.name):
                fastmcp_tool = fastmcp_server._tool_manager.get_tool(tool_def.name)
                self.assertIsNotNone(
                    fastmcp_tool,
                    f"TOOL_DEFINITIONS has {tool_def.name!r} but FastMCP does not",
                )

    def test_plan_file_info_schema_has_three_oneof_variants(self):
        """plan_file_info must have oneOf with error, not-ready, and ready shapes."""
        tool_def = _tool_def(cloud_app.TOOL_DEFINITIONS, "plan_file_info")
        schema = tool_def.output_schema
        self.assertIn("oneOf", schema)
        self.assertEqual(len(schema["oneOf"]), 3)
        # Verify the error variant has required: ["error"]
        error_variant = schema["oneOf"][0]
        self.assertIn("error", error_variant.get("required", []))

    def test_plan_status_schema_has_two_oneof_variants(self):
        """plan_status must have oneOf with error and success shapes."""
        tool_def = _tool_def(cloud_app.TOOL_DEFINITIONS, "plan_status")
        schema = tool_def.output_schema
        self.assertIn("oneOf", schema)
        self.assertEqual(len(schema["oneOf"]), 2)
        error_variant = schema["oneOf"][0]
        self.assertIn("error", error_variant.get("required", []))

    def test_simple_tools_have_flat_schema(self):
        """Tools with a single success shape should not have oneOf."""
        simple_tools = ["example_plans", "example_prompts", "model_profiles",
                        "plan_create", "plan_list"]
        for name in simple_tools:
            with self.subTest(tool=name):
                tool_def = _tool_def(cloud_app.TOOL_DEFINITIONS, name)
                schema = tool_def.output_schema
                self.assertNotIn(
                    "oneOf", schema,
                    f"{name} should have a flat schema, not oneOf",
                )

    def test_tool_functions_return_plain_call_tool_result(self):
        """No tool function should use Annotated return type (regression guard)."""
        import inspect
        import typing
        from mcp_cloud import http_server

        tool_funcs = [
            http_server.example_plans,
            http_server.example_prompts,
            http_server.model_profiles,
            http_server.plan_create,
            http_server.plan_status,
            http_server.plan_stop,
            http_server.plan_retry,
            http_server.plan_file_info,
            http_server.plan_list,
        ]
        for func in tool_funcs:
            with self.subTest(func=func.__name__):
                hints = typing.get_type_hints(func, include_extras=True)
                ret = hints.get("return")
                origin = getattr(ret, "__class__", None)
                # typing.Annotated has __class__.__name__ == '_AnnotatedAlias'
                self.assertNotEqual(
                    getattr(origin, "__name__", ""),
                    "_AnnotatedAlias",
                    f"{func.__name__} return type must be plain CallToolResult, "
                    f"not Annotated[CallToolResult, ...]",
                )

    def test_fastmcp_plan_file_info_schema_not_derived_from_pydantic(self):
        """The injected schema must be the canonical oneOf, not a flat Pydantic derivation."""
        from mcp_cloud.http_server import fastmcp_server
        from mcp_cloud.tool_models import PlanFileInfoOutput

        fastmcp_tool = fastmcp_server._tool_manager.get_tool("plan_file_info")
        pydantic_schema = PlanFileInfoOutput.model_json_schema()
        # The FastMCP schema must NOT equal the flat Pydantic schema.
        self.assertNotEqual(
            fastmcp_tool.output_schema,
            pydantic_schema,
            "plan_file_info outputSchema looks like it was derived from "
            "PlanFileInfoOutput instead of the canonical oneOf schema",
        )
        # It must have oneOf.
        self.assertIn("oneOf", fastmcp_tool.output_schema)


if __name__ == "__main__":
    unittest.main()
