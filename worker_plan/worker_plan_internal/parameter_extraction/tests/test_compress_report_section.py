from worker_plan_internal.parameter_extraction.compress_report_section import (
    COMPRESS_REPORT_SECTION_SYSTEM_PROMPT,
    CompressedReportSection,
    CompressReportSection,
    build_user_prompt,
    infer_section_type_from_path,
    normalize_section_type,
)


def test_infer_section_type_from_path() -> None:
    assert infer_section_type_from_path("strategic_decisions.md") == "strategic_decisions"
    assert infer_section_type_from_path("/tmp/review_plan.md") == "review_plan"
    assert infer_section_type_from_path("/tmp/premortem.md") == "premortem"
    assert infer_section_type_from_path("/tmp/expert_criticism.md") == "expert_criticism"
    assert infer_section_type_from_path("/tmp/something_else.md") == "unknown"


def test_normalize_section_type() -> None:
    assert normalize_section_type("Strategic Decisions") == "strategic_decisions"
    assert normalize_section_type("review-plan") == "review_plan"
    assert normalize_section_type("PREMORTEM") == "premortem"
    assert normalize_section_type("expert_criticism") == "expert_criticism"
    assert normalize_section_type("garbage") == "unknown"
    assert normalize_section_type(None) == "unknown"


def test_build_user_prompt_includes_section_specific_guidance() -> None:
    prompt = build_user_prompt(
        section_markdown="dummy markdown",
        section_type="premortem",
        section_title="Premortem",
    )
    assert "Section type: premortem" in prompt
    assert "[START_SECTION_MARKDOWN]" in prompt
    assert "[END_SECTION_MARKDOWN]" in prompt
    # Premortem-specific guidance should be present
    assert "failure paths" in prompt.lower()


def test_system_prompt_states_compression_role() -> None:
    # Sanity: the system prompt must make clear this is compression, not
    # parameter extraction. Older models drift toward "summarise for a human"
    # otherwise.
    text = COMPRESS_REPORT_SECTION_SYSTEM_PROMPT.lower()
    assert "compress" in text
    assert "monte carlo" in text
    assert "do not add commentary" in text


def test_pydantic_schema_is_flat_only_strings_and_str_lists() -> None:
    """The whole point of this implementation is a flat schema. Guard against
    accidental drift back into nested objects or enums."""
    fields = CompressedReportSection.model_fields
    expected = {
        "section_summary": str,
        "numeric_values": list[str],
        "load_bearing_assumptions": list[str],
        "gates_and_thresholds": list[str],
        "risks_and_shocks": list[str],
        "missing_data_to_estimate": list[str],
    }
    assert set(fields.keys()) == set(expected.keys())
    for name, expected_type in expected.items():
        assert fields[name].annotation == expected_type, (
            f"Field {name!r} drifted to {fields[name].annotation!r}; "
            f"expected {expected_type!r}. Keep the schema flat — older LLMs "
            "depend on it."
        )


def test_convert_to_markdown_renders_each_populated_bucket() -> None:
    compressed = CompressedReportSection(
        section_summary=(
            "Strategic Decisions block names the levers that drive viability: "
            "staffing model, revenue mix, and contingency sizing."
        ),
        numeric_values=[
            "Year 1 budget: 2M DKK",
            "Startup contingency: 15% of Year 1 budget = 300,000 DKK",
            "Off-peak (Nov-Feb) is the low-utilisation season",
        ],
        load_bearing_assumptions=[
            "Greenlandic labor law allows contractor classification of instructors",
            "Tourist demand in Q3 is strong enough to subsidise local off-peak",
        ],
        gates_and_thresholds=[
            "Off-peak revenue must cover >=75% of direct utility overhead",
        ],
        risks_and_shocks=[
            "Single-kiln overload during June-September: bookings exceed 24/7 capacity by >48h",
            "Labor reclassification consumes the entire 300,000 DKK contingency",
        ],
        missing_data_to_estimate=[
            "Direct monthly utility overhead in DKK — derive from metered pricing trial",
        ],
    )

    markdown = CompressReportSection.convert_to_markdown(
        compressed, section_title="Strategic Decisions"
    )

    assert markdown.startswith("# Strategic Decisions")
    assert "## Numeric values" in markdown
    assert "## Load-bearing assumptions" in markdown
    assert "## Gates and thresholds" in markdown
    assert "## Risks and shocks" in markdown
    assert "## Missing data to estimate" in markdown
    # Verbatim numbers preserved (not converted to fractions or rounded)
    assert "300,000 DKK" in markdown
    assert "75%" in markdown


def test_convert_to_markdown_skips_empty_buckets() -> None:
    compressed = CompressedReportSection(
        section_summary="Section had only numbers worth keeping.",
        numeric_values=["budget: 100 EUR"],
        load_bearing_assumptions=[],
        gates_and_thresholds=[],
        risks_and_shocks=[],
        missing_data_to_estimate=[],
    )

    markdown = CompressReportSection.convert_to_markdown(compressed)
    assert "## Numeric values" in markdown
    # Empty buckets must not produce empty headings
    assert "## Load-bearing assumptions" not in markdown
    assert "## Gates and thresholds" not in markdown
    assert "## Risks and shocks" not in markdown
    assert "## Missing data to estimate" not in markdown
