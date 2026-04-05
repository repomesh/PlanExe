# Flaw Tracer — Status and Known Issues

## What works well

- **DAG traversal is correct.** The registry maps all 70 stages, upstream resolution works, dedup prevents redundant checks, depth limiting works.
- **Source code analysis gives actionable suggestions.** When the origin is correctly identified, the Phase 3 output points to specific prompt text and proposes concrete fixes.
- **Depth sorting is useful.** Deepest root causes appear first, which matches the user's intent of finding the earliest upstream origin.
- **Events.jsonl enables live monitoring.** Users can `tail -f events.jsonl` to watch progress instead of waiting blindly.
- **Evidence quoting works.** The LLM generally finds relevant passages in upstream files.

## Known issues to fix

### HIGH: Phase 1 doesn't anchor to the user's flaw description

The user provides a specific flaw (e.g., "zoning and permits in Shanghai lack specifics") but Phase 1 identifies *different* flaws from the file instead. The LLM uses the description as inspiration rather than finding that exact flaw and closely related ones.

**Root cause:** The Phase 1 prompt says "identify each discrete flaw" broadly. It should prioritize flaws matching the user's description, then optionally find additional ones.

**Fix direction:** Restructure the Phase 1 prompt to first locate the user's specific flaw in the file, then look for related flaws. Consider splitting into "anchor the user's flaw" + "find additional flaws" as two steps.

### MEDIUM: Upstream checks are too loose

The LLM says "found" when an upstream file discusses a related *topic* rather than containing the actual *precursor* to the flaw. Example: a flaw about "Lead Room Designer talent availability" traces through "Room Design Complexity" evidence because both involve room design.

**Root cause:** The upstream check prompt asks "does this file contain the same problem or a precursor?" — the word "precursor" is too vague. The LLM interprets topical similarity as causal connection.

**Fix direction:** Make the upstream check prompt more specific. Require the LLM to explain the causal mechanism (how upstream content *caused* the downstream flaw), not just topical overlap. Consider asking the LLM to rate confidence (HIGH/MEDIUM/LOW) and only follow HIGH-confidence matches.

### MEDIUM: Evidence quotes are too long

Some evidence fields contain entire JSON objects (100+ lines) instead of the relevant snippet. This makes the output hard to read and wastes context window in downstream LLM calls.

**Fix direction:** Add guidance to the upstream check prompt: "Quote only the specific sentence or phrase that demonstrates the flaw, not the entire surrounding object or section. Keep quotes under 200 characters."

### LOW: Duplicate source code filenames are confusing

When the stage file and implementation file have the same name (e.g., `identify_purpose.py` in both `stages/` and `assume/`), the output shows `["identify_purpose.py", "identify_purpose.py"]`.

**Fix direction:** Include the parent directory in source code file names, e.g., `stages/identify_purpose.py` and `assume/identify_purpose.py`.

### LOW: Most flaws converge on the same origin

In test runs, 3 of 5 flaws trace back to `potential_levers`. This may be accurate (many downstream issues really do originate from lever identification) but could also indicate the upstream check is too eager. Worth monitoring across more runs to determine if this is a real pattern or an artifact of loose matching.

## Test runs completed

1. **India census** (`20250101_india_census`): Started from `029-2-self_audit.md`, 17 flaws found, 153 LLM calls, deepest origin: `potential_levers` (depth 6). Many flaws traced to early pipeline stages.

2. **Minecraft escape** (`20251016_minecraft_escape`): Started from `029-2-self_audit.md` with specific flaw about zoning/permits, 5 flaws found, 43 LLM calls, deepest origin: `identify_purpose` (depth 5). The user's specific flaw was not among the 5 identified — exposed the Phase 1 anchoring problem.

## Architecture notes

- The tool runs from `worker_plan/` directory using Python 3.11.
- LLM calls go through `LLMExecutor` with the active model profile (`PLANEXE_MODEL_PROFILE`).
- The `record_usage_metric called but no usage metrics path is set` warnings are harmless — the flaw tracer doesn't set up the metrics path since it's a standalone CLI tool, not a pipeline task.
- The first-match-wins strategy in `_trace_upstream` means only one upstream branch is followed per flaw. If the flaw exists in multiple upstream branches, only the first one encountered is traced.
