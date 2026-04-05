# Flaw Tracer — Status and Known Issues

## What works well

- **DAG traversal is correct.** The registry maps all 70 stages, upstream resolution works, dedup prevents redundant checks, depth limiting works.
- **Source code analysis gives actionable suggestions.** When the origin is correctly identified, the Phase 3 output points to specific prompt text and proposes concrete fixes.
- **Depth sorting is useful.** Deepest root causes appear first, which matches the user's intent of finding the earliest upstream origin.
- **Events.jsonl enables live monitoring.** Users can `tail -f events.jsonl` to watch progress instead of waiting blindly.
- **Phase 1 anchors to the user's flaw.** The user's specific flaw is always the first result, with additional flaws limited to the same problem family. Verified on the Minecraft escape run — the zoning/permits flaw is now correctly identified and traced.
- **Upstream checks require causal links.** The prompt requires the LLM to explain *how* upstream content caused the downstream flaw, not just topical overlap. This produces tighter, more accurate traces.
- **Evidence quotes are concise.** Both Phase 1 and Phase 2 prompts instruct the LLM to keep quotes under 200 characters.
- **Source code filenames are disambiguated.** Shows `stages/identify_purpose.py` and `assume/identify_purpose.py` instead of duplicate bare filenames.

## Fixed issues

### Phase 1 didn't anchor to user's flaw (was HIGH, fixed)

The Phase 1 prompt now requires the user's specific flaw as the first item, with additional flaws limited to the same problem family. Before the fix, the LLM would ignore the user's flaw and identify unrelated issues.

### Upstream checks were too loose (was MEDIUM, fixed)

The Phase 2 prompt now requires a causal mechanism ("how did this upstream content lead to the downstream flaw?") and explicitly rejects topical overlap. Before the fix, the LLM would say "found" whenever an upstream file discussed a related topic.

### Evidence quotes were too long (was MEDIUM, fixed)

Both Phase 1 and Phase 2 prompts now instruct "keep quotes under 200 characters." Before the fix, evidence fields contained entire JSON objects (100+ lines).

### Duplicate source code filenames (was LOW, fixed)

Source code paths now include the parent directory (`stages/identify_purpose.py`) to disambiguate files with the same name in different packages.

## Open issues to monitor

### LOW: Flaw convergence on same origin

In the first test run (India census, before prompt fixes), 3 of 5 flaws traced back to `potential_levers`. After the prompt tightening, the Minecraft escape run showed all 3 flaws converging on `identify_risks` — but this makes sense since all 3 flaws were about the same problem family (missing regulatory specifics). Monitor across more diverse runs to determine if convergence is a real pattern or an artifact.

### LOW: First-match-wins may miss parallel origins

The `_trace_upstream` method follows only the first upstream branch where the flaw is found. If a flaw has precursors in multiple parallel branches, only one is traced. This is a deliberate efficiency trade-off. If users report missing origins, consider adding a mode that follows all branches.

## Test runs completed

1. **India census** (`20250101_india_census`): Started from `029-2-self_audit.md`, 17 flaws found, 153 LLM calls, deepest origin: `potential_levers` (depth 6). Run with old prompts — flaws were not anchored to user input, traces were loose.

2. **Minecraft escape v1** (`20251016_minecraft_escape`): Started from `029-2-self_audit.md` with flaw about zoning/permits. Old prompts: 5 flaws found, 43 LLM calls, user's flaw not identified. Exposed the Phase 1 anchoring problem.

3. **Minecraft escape v2** (`20251016_minecraft_escape`): Same input, new prompts. 3 flaws found, 31 LLM calls, deepest origin: `identify_risks` (depth 5). User's zoning/permits flaw correctly identified as flaw_001. All 3 flaws in the same problem family (regulatory gaps). Evidence quotes concise. Traces causally sound.

## Architecture notes

- The tool runs from `worker_plan/` directory using Python 3.11.
- LLM calls go through `LLMExecutor` with the active model profile (`PLANEXE_MODEL_PROFILE`).
- The `record_usage_metric called but no usage metrics path is set` warnings are harmless — the flaw tracer doesn't set up the metrics path since it's a standalone CLI tool, not a pipeline task.
- The first-match-wins strategy in `_trace_upstream` means only one upstream branch is followed per flaw. If the flaw exists in multiple upstream branches, only the first one encountered is traced.
