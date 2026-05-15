from worker_plan_internal.parameter_extraction.compress_report_section import (
    COMPRESS_REPORT_SECTION_SYSTEM_PROMPT,
    CompressedReportSection,
    CompressReportSection,
    PublicScoredItem,
    build_user_prompt,
    infer_section_type_from_path,
    normalize_section_type,
)


def test_infer_section_type_from_path() -> None:
    assert infer_section_type_from_path("/tmp/selected_scenario.md") == "selected_scenario"
    assert infer_section_type_from_path("/tmp/review_plan.md") == "review_plan"
    assert infer_section_type_from_path("/tmp/premortem.md") == "premortem"
    assert infer_section_type_from_path("/tmp/expert_criticism.md") == "expert_criticism"
    assert infer_section_type_from_path("/tmp/something_else.md") == "unknown"
    # Strategic Decisions is no longer a recognised standalone section type:
    # its content is captured upstream by SELECTED_SCENARIO and downstream
    # by the Luigi-input blobs feeding review_plan / premortem /
    # expert_criticism. Compressing it directly would double-compress.
    assert infer_section_type_from_path("strategic_decisions.md") == "unknown"


def test_normalize_section_type() -> None:
    assert normalize_section_type("Selected Scenario") == "selected_scenario"
    assert normalize_section_type("review-plan") == "review_plan"
    assert normalize_section_type("PREMORTEM") == "premortem"
    assert normalize_section_type("expert_criticism") == "expert_criticism"
    assert normalize_section_type("garbage") == "unknown"
    assert normalize_section_type(None) == "unknown"
    # See note in test_infer_section_type_from_path.
    assert normalize_section_type("strategic_decisions") == "unknown"
    assert normalize_section_type("Strategic Decisions") == "unknown"


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


def test_pydantic_schema_shape() -> None:
    """Guard against accidental drift in the assembled schema.

    All four list buckets carry the per-item ``PublicScoredItem`` shape
    (line + scoring + status + quote + code-computed quote_verified). The
    bucket prompts define what ``line`` should contain for each bucket.
    """
    fields = CompressedReportSection.model_fields
    expected = {
        "section_summary": str,
        "numeric_values": list[PublicScoredItem],
        "load_bearing_assumptions": list[PublicScoredItem],
        "gates_and_thresholds": list[PublicScoredItem],
        "risks_and_shocks": list[PublicScoredItem],
        "missing_data_to_estimate": list[PublicScoredItem],
    }
    assert set(fields.keys()) == set(expected.keys())
    for name, expected_type in expected.items():
        assert fields[name].annotation == expected_type, (
            f"Field {name!r} is {fields[name].annotation!r}; "
            f"expected {expected_type!r}."
        )


def _si(
    line: str,
    *,
    original: str | None = None,
    status: str = "explicit",
    e: int = 5,
    r: int = 5,
    quote: str = "verbatim quote",
    verified: bool = True,
) -> PublicScoredItem:
    return PublicScoredItem(
        line_english=line,
        line_original=original if original is not None else line,
        modelling_relevance=r,
        source_evidence=e,
        source_status=status,
        source_quote=quote,
        quote_verified=verified,
    )


def test_convert_to_markdown_renders_each_populated_bucket() -> None:
    compressed = CompressedReportSection(
        section_summary=(
            "Strategic Decisions block names the levers that drive viability: "
            "staffing model, revenue mix, and contingency sizing."
        ),
        numeric_values=[
            _si("Year 1 budget: 2M DKK — input to cash burn model"),
            _si(
                "Startup contingency: 15% of Year 1 budget = 300,000 DKK — shock buffer",
                status="derived",
                e=4,
            ),
            _si(
                "Off-peak (Nov-Feb) is the low-utilisation season — capacity ceiling",
                e=3,
                r=3,
                verified=False,
            ),
        ],
        load_bearing_assumptions=[
            _si("Greenlandic labor law allows contractor classification of instructors"),
            _si("Tourist demand in Q3 is strong enough to subsidise local off-peak"),
        ],
        gates_and_thresholds=[
            _si(
                "If off-peak revenue falls below 75% of direct utility overhead, "
                "then contingency funds operating costs",
            ),
        ],
        risks_and_shocks=[
            _si(
                "Single-kiln overload during June-September: bookings exceed 24/7 capacity by >48h"
            ),
            _si("Labor reclassification consumes the entire 300,000 DKK contingency"),
        ],
        missing_data_to_estimate=[
            _si(
                "Direct monthly utility overhead in DKK — derive from metered pricing trial",
                status="inferred",
                e=1,
                quote="NOT IN SOURCE",
                verified=False,
            ),
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
    # Inline tag is composed from PublicScoredItem fields on every list bucket
    assert "[explicit | e=5 r=5 | quote: verified]" in markdown
    assert "[derived | e=4 r=5 | quote: verified]" in markdown
    assert "[inferred | e=1 r=5 | quote: unverified]" in markdown
    assert "quote: unverified" in markdown


def test_annotate_forces_missing_status_for_missing_data_bucket() -> None:
    """The annotator overwrites source_status to 'missing' for items in the
    missing_data_to_estimate bucket, regardless of what the LLM said. The
    bucket name already determines the right status."""
    from worker_plan_internal.parameter_extraction.compress_report_section import (
        annotate_scored_items,
        ScoredItem,
    )

    llm_items = [
        ScoredItem(
            line_english="Year 1 fixed labor cost in DKK/month — needed for cash burn model",
            line_original="Year 1 fixed labor cost in DKK/month — needed for cash burn model",
            modelling_relevance=5,
            source_evidence=2,
            source_status="explicit",  # LLM got this wrong
            source_quote="exact fixed annualized cost",
        ),
        ScoredItem(
            line_english="Direct utility overhead in DKK/month — estimate from metered trial",
            line_original="Direct utility overhead in DKK/month — estimate from metered trial",
            modelling_relevance=5,
            source_evidence=1,
            source_status="inferred",
            source_quote="NOT IN SOURCE",
        ),
    ]

    kept, scored = annotate_scored_items(
        llm_items, section_markdown="", field_name="missing_data_to_estimate"
    )

    # Every surviving item in missing_data_to_estimate must have source_status='missing'.
    for item in kept:
        assert item.source_status == "missing", item
    # And the metadata copy also reflects the overwrite.
    for record in scored:
        assert record["source_status"] == "missing", record


def test_annotate_does_not_force_status_for_other_buckets() -> None:
    """The forced-status override only applies to missing_data_to_estimate.
    Other buckets pass the LLM's source_status through untouched."""
    from worker_plan_internal.parameter_extraction.compress_report_section import (
        annotate_scored_items,
        ScoredItem,
    )

    llm_items = [
        ScoredItem(
            line_english="Single kiln breakdown: 4-8 weeks production stoppage",
            line_original="Single kiln breakdown: 4-8 weeks production stoppage",
            modelling_relevance=5,
            source_evidence=3,
            source_status="stress_test",
            source_quote="4-8 weeks total production stop",
        ),
    ]
    kept, _ = annotate_scored_items(
        llm_items, section_markdown="", field_name="risks_and_shocks"
    )
    assert kept[0].source_status == "stress_test"


def test_source_status_accepts_stress_test() -> None:
    """stress_test is a distinct epistemic tag used for premortem shock
    magnitudes that are NOT plan facts. Schema must accept it without
    coercion, and the markdown render must surface the tag."""
    item = _si(
        "Single kiln breakdown: 4-8 weeks production stoppage",
        status="stress_test",
        e=3,
        r=4,
    )
    compressed = CompressedReportSection(
        section_summary="Premortem digest.",
        numeric_values=[],
        load_bearing_assumptions=[],
        gates_and_thresholds=[],
        risks_and_shocks=[item],
        missing_data_to_estimate=[],
    )
    assert compressed.risks_and_shocks[0].source_status == "stress_test"
    markdown = CompressReportSection.convert_to_markdown(compressed)
    assert "[stress_test | e=3 r=4 |" in markdown


def test_markdown_uses_english_keeps_original_in_json() -> None:
    """Markdown renders the clean English version; line_original is
    preserved only in the JSON shape (model_dump)."""
    item = _si(
        "Contingency reserve: 300,000 DKK — shock buffer",
        original="Kontingensreserve: 300.000 DKK — stødpude",
        quote="udrydde hele jeres 15% kontingens",
    )
    compressed = CompressedReportSection(
        section_summary="Danish-source workshop plan.",
        numeric_values=[item],
        load_bearing_assumptions=[],
        gates_and_thresholds=[],
        risks_and_shocks=[],
        missing_data_to_estimate=[],
    )

    markdown = CompressReportSection.convert_to_markdown(compressed)
    assert "Contingency reserve: 300,000 DKK" in markdown
    # The native-language string is NOT in markdown — markdown is the
    # downstream-readable English digest.
    assert "Kontingensreserve" not in markdown
    # But the JSON shape carries both versions.
    dumped = compressed.model_dump()
    assert dumped["numeric_values"][0]["line_english"] == "Contingency reserve: 300,000 DKK — shock buffer"
    assert dumped["numeric_values"][0]["line_original"] == "Kontingensreserve: 300.000 DKK — stødpude"


def test_convert_to_markdown_skips_empty_buckets() -> None:
    compressed = CompressedReportSection(
        section_summary="Section had only numbers worth keeping.",
        numeric_values=[_si("budget: 100 EUR — input to cash burn model")],
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


def test_numeric_density_bonus_counts_numeric_tokens() -> None:
    """Numeric density is the only content-bonus the scorer applies and it
    must be language- and domain-neutral. Digits are digits regardless of
    whether the surrounding text is English, Danish, French, or domain-
    specific (commercial, public-health, renovation, hobby)."""
    from worker_plan_internal.parameter_extraction.compress_report_section import (
        numeric_density_bonus,
    )

    assert numeric_density_bonus("No numbers in this line") == 0
    assert numeric_density_bonus("Rental rate is 165 per hour") == 1.0
    # Three tokens: "2,000,000", "0.15", "300,000"
    assert numeric_density_bonus("Budget 2,000,000 at 0.15 leaves 300,000") == 3.0
    # Cap at 3.0 even with more numbers
    assert numeric_density_bonus("1 2 3 4 5 6 7 8") == 3.0
    # Same scorer regardless of input language. The Danish phrase below
    # has two numeric tokens ("2.000.000" and "15"), so the bonus is 2.0
    # — no English keyword is required for the count to work.
    assert numeric_density_bonus("Budgettet er 2.000.000 DKK med 15 procent reserve") == 2.0


def test_composite_score_prefers_quantified_over_prose() -> None:
    """Two items with identical LLM self-ratings and quote-verification
    status should be ordered by quantification: numeric content outranks
    bare prose. No language- or domain-specific keyword check involved."""
    from worker_plan_internal.parameter_extraction.compress_report_section import (
        ScoredItem,
        annotate_scored_items,
    )

    section = (
        "Total commitment 2,000,000 with 15% buffer. "
        "Some background prose about community values."
    )
    quantified = ScoredItem(
        line_english="Reserve buffer is 15% of the 2,000,000 total",
        line_original="Reserve buffer is 15% of the 2,000,000 total",
        modelling_relevance=3,
        source_evidence=3,
        source_status="explicit",
        source_quote="15% buffer",
    )
    prose = ScoredItem(
        line_english="The plan emphasizes community-focused values for residents",
        line_original="The plan emphasizes community-focused values for residents",
        modelling_relevance=3,
        source_evidence=3,
        source_status="explicit",
        source_quote="community values",
    )
    kept, _ = annotate_scored_items(
        [prose, quantified], section_markdown=section, field_name="numeric_values"
    )
    # Same base (3*3=9) and both verified. The quantified item wins on the
    # numeric-density bonus alone.
    assert kept[0].line_english.startswith("Reserve buffer is 15%")
    assert kept[1].line_english.startswith("The plan emphasizes community")
