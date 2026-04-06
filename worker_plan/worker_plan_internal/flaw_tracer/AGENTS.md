# Flaw Tracer — Status and Known Issues

## What works well

- **DAG traversal is correct.** The registry maps all 70 stages, upstream resolution works, dedup prevents redundant checks, depth limiting works.
- **Phase 1 anchors to the user's flaw.** The user's specific flaw is always the first result, with additional flaws limited to the same problem family.
- **Upstream checks require causal links.** The prompt requires the LLM to explain *how* upstream content caused the downstream flaw, not just topical overlap. This produces tighter, more accurate traces.
- **Phase 3 classifies root causes.** Each origin is categorized as `prompt_fixable`, `domain_complexity`, or `missing_input`. Verified: the India census caste enumeration flaw is correctly classified as `domain_complexity`, while the workforce feasibility flaw is `prompt_fixable`.
- **Evidence quotes are concise.** Both Phase 1 and Phase 2 prompts instruct the LLM to keep quotes under 200 characters.
- **Source code filenames are disambiguated.** Shows `stages/identify_purpose.py` and `assume/identify_purpose.py` instead of duplicate bare filenames.
- **Depth sorting is useful.** Deepest root causes appear first, matching the user's intent of finding the earliest upstream origin.
- **Events.jsonl enables live monitoring.** Users can `tail -f events.jsonl` to watch progress instead of waiting blindly.
- **Focused output.** A typical run finds 2-3 flaws in the same problem family and makes 15-30 LLM calls (down from 17 flaws / 153 calls before prompt improvements).

## Fixed issues

### Phase 1 didn't anchor to user's flaw (was HIGH, fixed)

The Phase 1 prompt now requires the user's specific flaw as the first item, with additional flaws limited to the same problem family. Before the fix, the LLM would ignore the user's flaw and identify unrelated issues.

### Upstream checks were too loose (was MEDIUM, fixed)

The Phase 2 prompt now requires a causal mechanism ("how did this upstream content lead to the downstream flaw?") and explicitly rejects topical overlap. Before the fix, the LLM would say "found" whenever an upstream file discussed a related topic.

### Evidence quotes were too long (was MEDIUM, fixed)

Both Phase 1 and Phase 2 prompts now instruct "keep quotes under 200 characters." Before the fix, evidence fields contained entire JSON objects (100+ lines).

### Phase 3 always blamed the prompt (was MEDIUM, fixed)

Phase 3 now classifies each root cause into one of three categories:
- **prompt_fixable** — the prompt has a gap that can be edited (e.g., "list specific permits with lead times")
- **domain_complexity** — inherently uncertain or contentious, no prompt change resolves it (e.g., caste enumeration politics in India)
- **missing_input** — the user's plan didn't provide enough detail

Before the fix, every suggestion was "modify the system prompt" even when the real issue was domain complexity. Verified on India census run: caste enumeration correctly classified as `domain_complexity`, workforce feasibility as `prompt_fixable`.

### Duplicate source code filenames (was LOW, fixed)

Source code paths now include the parent directory (`stages/identify_purpose.py`) to disambiguate files with the same name in different packages.

## Open issues to monitor

### LOW: Flaw convergence on same origin

After prompt tightening, convergence now makes sense — flaws in the same problem family naturally trace to the same origin. The Minecraft escape run had all 3 regulatory flaws converge on `identify_risks`, which is correct. Monitor across more diverse runs.

### LOW: First-match-wins may miss parallel origins

The `_trace_upstream` method follows only the first upstream branch where the flaw is found. If a flaw has precursors in multiple parallel branches, only one is traced. This is a deliberate efficiency trade-off. If users report missing origins, consider adding a mode that follows all branches.

## Test runs completed

1. **India census v1** (`20250101_india_census`): Old prompts. 17 flaws, 153 LLM calls, deepest origin: `potential_levers` (depth 6). Flaws not anchored to user input, traces loose, evidence bloated.

2. **Minecraft escape v1** (`20251016_minecraft_escape`): Old prompts. Flaw about zoning/permits. 5 flaws, 43 LLM calls. User's flaw not identified. Exposed Phase 1 anchoring problem.

3. **Minecraft escape v2** (`20251016_minecraft_escape`): New prompts. 3 flaws, 31 LLM calls, deepest origin: `identify_risks` (depth 5). User's flaw correctly identified as flaw_001. All flaws in same problem family (regulatory gaps).

4. **India census v2** (`20250101_india_census`): New prompts. 2 flaws (down from 17), 17 LLM calls (down from 153), deepest origin: `potential_levers` (depth 6). User's flaw correctly identified. Exposed Phase 3 "always blames prompt" limitation.

5. **India census v3** (`20250101_india_census`): New prompts + Phase 3 classification. 2 flaws, 17 LLM calls. Caste enumeration correctly classified as `domain_complexity`. Workforce feasibility correctly classified as `prompt_fixable`. All fixes verified working.

## Architecture notes

- The tool runs from `worker_plan/` directory using Python 3.11.
- LLM calls go through `LLMExecutor` with the active model profile (`PLANEXE_MODEL_PROFILE`).
- The `record_usage_metric called but no usage metrics path is set` warnings are harmless — the flaw tracer doesn't set up the metrics path since it's a standalone CLI tool, not a pipeline task.
- The first-match-wins strategy in `_trace_upstream` means only one upstream branch is followed per flaw. If the flaw exists in multiple upstream branches, only the first one encountered is traced.
