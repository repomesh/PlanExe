# Flaw Tracer — Status and Known Issues

## What works well

- **DAG traversal is correct.** The registry maps all 70 nodes, upstream resolution works, dedup prevents redundant checks, depth limiting works.
- **Phase 1 anchors to the user's flaw.** The user's specific flaw is always the first result, with additional flaws limited to the same problem family.
- **Upstream checks require causal links.** The prompt requires the LLM to explain *how* upstream content caused the downstream flaw, not just topical overlap. This produces tighter, more accurate traces.
- **Phase 3 classifies root causes.** Each origin is categorized as `prompt_fixable`, `domain_complexity`, or `missing_input`. Verified: the India census caste enumeration flaw is correctly classified as `domain_complexity`, while the workforce feasibility flaw is `prompt_fixable`.
- **Evidence quotes are concise.** Both Phase 1 and Phase 2 prompts instruct the LLM to keep quotes under 200 characters.
- **Source code filenames are disambiguated.** Shows `nodes/identify_purpose.py` and `assume/identify_purpose.py` instead of duplicate bare filenames.
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

Source code paths now include the parent directory (`nodes/identify_purpose.py`) to disambiguate files with the same name in different packages.

## Open issues

### MEDIUM: Non-determinism untested

This is LLM judging LLM output. Every upstream check is a subjective call. Two runs on the same input may produce different traces. We haven't tested reproducibility — run the same input 3 times and compare. If traces diverge significantly, consider requiring higher-confidence matches or running multiple passes and intersecting results.

### MEDIUM: Static registry will drift

The DAG mapping in `registry.py` is a hand-maintained copy of the pipeline topology. Adding, removing, or renaming nodes requires a manual update — the registry won't auto-detect changes. If the registry falls out of sync, traces will silently miss nodes or follow wrong paths.

**Fix direction:** Generate the registry from Luigi task introspection at startup, or add a CI check that compares the registry against the actual task classes.

### LOW: First-match-wins may miss parallel origins

The `_trace_upstream` method follows only the first upstream branch where the flaw is found. Real flaws often have multiple contributing causes from parallel branches, but only one is traced. The trace looks clean and linear, but reality is messier.

**Fix direction:** Add a `--thorough` mode that follows all branches where the flaw is found, producing a tree instead of a chain.

### LOW: Flaw convergence on same origin

After prompt tightening, convergence makes sense — flaws in the same problem family naturally trace to the same origin. Monitor across more diverse runs.

## Test runs completed

1. **India census v1** (`20250101_india_census`): Old prompts. 17 flaws, 153 LLM calls, deepest origin: `potential_levers` (depth 6). Flaws not anchored to user input, traces loose, evidence bloated.

2. **Minecraft escape v1** (`20251016_minecraft_escape`): Old prompts. Flaw about zoning/permits. 5 flaws, 43 LLM calls. User's flaw not identified. Exposed Phase 1 anchoring problem.

3. **Minecraft escape v2** (`20251016_minecraft_escape`): New prompts. 3 flaws, 31 LLM calls, deepest origin: `identify_risks` (depth 5). User's flaw correctly identified as flaw_001. All flaws in same problem family (regulatory gaps).

4. **India census v2** (`20250101_india_census`): New prompts. 2 flaws (down from 17), 17 LLM calls (down from 153), deepest origin: `potential_levers` (depth 6). User's flaw correctly identified. Exposed Phase 3 "always blames prompt" limitation.

5. **India census v3** (`20250101_india_census`): New prompts + Phase 3 classification. 2 flaws, 17 LLM calls. Caste enumeration correctly classified as `domain_complexity`. Workforce feasibility correctly classified as `prompt_fixable`. All fixes verified working.

## Honest assessment

The tool is a useful diagnostic prototype. The trace chains are the most trustworthy part — they're mechanically grounded in the DAG structure. The suggestions are LLM opinions — useful starting points, not patches.

The category classification (`prompt_fixable` / `domain_complexity` / `missing_input`) turned out to be the most valuable feature. It prevents wasted effort on flaws that can't be fixed by prompt editing.

The tool is diagnostic, not prescriptive. It tells you *where* a flaw originated and *why*, but someone still has to decide what to do. It can't catch flaws that don't leave textual evidence — timing issues, model-specific quirks, or structural DAG problems are invisible.

Starting from `029-2-self_audit.md` is the sweet spot. That file already contains identified issues, so the tracer is tracing known problems upstream rather than discovering flaws from scratch.

Before relying on this for automated decisions (e.g., in the self-improve loop), it needs more diverse test runs (10+ plans) and reproducibility testing.

## Architecture notes

- The tool runs from `worker_plan/` directory using Python 3.11.
- LLM calls go through `LLMExecutor` with the active model profile (`PLANEXE_MODEL_PROFILE`).
- The `record_usage_metric called but no usage metrics path is set` warnings are harmless — the flaw tracer doesn't set up the metrics path since it's a standalone CLI tool, not a pipeline task.
- The first-match-wins strategy in `_trace_upstream` means only one upstream branch is followed per flaw. If the flaw exists in multiple upstream branches, only the first one encountered is traced.
