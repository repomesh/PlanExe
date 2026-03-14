# System prompt optimizer

My overall plan is to optimize all system prompts across PlanExe.
By first starting optimizing the earliest system prompt, when that consistently performs better than
older system prompts, then it's a keeper. Then move on to the next system prompt in the luigi pipeline.
By the end of this prompt optimization, the overall plan quality should have been improved.

I want to track metrics for how much improvement have happened.


## Status (2026-03-14)

### Done

- **Data repo created**: [PlanExe-prompt-lab](https://github.com/PlanExeOrg/PlanExe-prompt-lab) — holds baseline data, optimization run artifacts, and scores.
- **Baseline data populated**: 5 train plans and 9 verify plans extracted from zips into `baseline/train/` and `baseline/verify/`. Each plan contains ~175-189 files covering the full pipeline output.
- **`dataset.json`** defines the train/verify split with zip filenames.
- **`populate_baseline.py`** script automates ingesting baseline data from local paths or URLs.
- **Directory structure** for `runs/`, `scores/`, and `full_plan_comparisons/` is in place (empty, awaiting optimizer).
- **`prompt_optimizer/` runner** ([PR #263](https://github.com/PlanExeOrg/PlanExe/pull/263)) — re-executes the `IdentifyPotentialLevers` step with a candidate system prompt against baseline plans. Features:
  - Added optional `system_prompt` parameter to `IdentifyPotentialLevers.execute()` (backward-compatible).
  - CLI with `--system-prompt-file`, `--baseline-dir`/`--plan-dir`, `--output-dir`, `--model`.
  - Streaming progress: `meta.json` written at start, `events.jsonl` for real-time monitoring, `outputs.jsonl` for per-plan results.
  - Per-plan `activity_overview.json` and `usage_metrics.jsonl` for token/cost tracking.
  - System info (OS, CPU, memory, GPU) captured in `meta.json`.
  - Tested against all 5 training plans with local ollama-llama3.1.

### Not Started

- **Evaluator prompt** — no scoring rubric or comparison prompt written.
- **Candidate generator** — no mechanism for producing prompt variants.
- **Scorer / Optimizer loop** — no automated train/verify loop.

### Next Steps

1. **Design the evaluator prompt and scoring rubric.** Define concrete dimensions (completeness, specificity, actionability, structure) and a numeric scale. Version-control it alongside the system prompts.
2. **Build `evaluator.py`** — calls a pinned reasoning model to score/compare runner outputs against baseline.
3. **Run baseline scoring** — score the current default prompt outputs to establish a numeric starting point.
4. **Build `candidate_generator.py`** — produce prompt variants (LLM rewrites, structured mutations).
5. **Build `optimizer.py`** — orchestrate the train/verify loop (Stage 1-2).
6. **Pin the reasoning model** for evaluation so scores are reproducible across runs.
7. **Add regression detection** — after optimizing one step, re-run downstream steps to check for cascade regressions before committing.
8. **Extend runner to other pipeline steps** — the runner is designed for this; each step needs an adapter for input assembly, execute call, output filenames, and step name.


## Stage 1 - one improvement iteration

Here is how one iteration is going to be:
Optimize one system prompt for a single step in the luigi pipeline in run_plan_pipeline.py
Take the "dataset train" and unzip the files to a work dir.
Alter the system prompt of a named task in the pipeline.
For MODEL_LIST, loop through the models, (these are LLMs without reasoning):
- It's very expensive to run the full pipeline. So I only want to rerun the luigi pipeline for that just step, see if the new system prompt does a better job than the reference plan.
- Capture the output.

Have a reasoning model do a comparison of the captured outputs.
If it does better than the original prompt then it's a candidate for keeping.
If it does does worse than the original prompt then write it to a failed attempt log.
Find prompts that consistently yield better outputs than the original prompt.
Store the feedback.

At this point there should be a ranked list of candidate system prompts that are better than the original.
Go through the "dataset verify" and compute score of the best candidate prompts.
Pick the best one and commit it to git.

For all plans both train and verify, commit the new generated files for each plan.
Commit improvement stats.

## Stage 2 - multiple improvement iteration

Run "one improvement iteration" multiple times, until there score isn't improving significantly.

## Stage 3 - next item in the luigi pipeline

As more upstream tasks gets optimized, then move on to further downstream tasks.

From time to time regenerate full plan, and have a reasoning model compare how
much better or worse is the new full plan is over various KPIs.


# Dataset

Config json file that contains the "dataset train" and "dataset verify".

The dataset lives in the [PlanExe-prompt-lab](https://github.com/PlanExeOrg/PlanExe-prompt-lab) repository.

These zip files are what PlanExe currently outputs, so these are the "baseline" to compare with.


## Dataset train

20260310_hong_kong_game.zip
20250329_gta_game.zip
20250321_silo.zip
20260311_parasomnia_research_unit.zip
20260308_sovereign_identity.zip

## Dataset verify

20260303_crate_recovery_campaign.zip
20260215_nuuk_clay_workshop.zip
20260202_heatwave_resilience.zip
20260201_media_rescue.zip
20260201_yellowstone_evacuation.zip
20260131_clear_english.zip
20260129_euro_adoption.zip
20260114_cbc_validation.zip
20251101_e_bus_security.zip


# Feedback

## Strengths

- Incremental approach is smart — optimizing one pipeline step at a time and proving it before moving on avoids compounding errors.
- Train/verify split — using separate datasets to prevent overfitting to the evaluation set is the right call.
- Failed attempt log — tracking what didn't work is often overlooked but very valuable.

## Questions & Gaps

1. What are the KPIs?
The document mentions "score," "better," "worse," and "various KPIs" but never defines them. This is the most critical gap. Without concrete metrics, the reasoning model's comparison will be subjective and inconsistent. What makes one output "better"? Completeness? Specificity? Actionability? Structure?

2. How is the reasoning model prompted for comparison?
"Have a reasoning model do a comparison" is underspecified. Will it use a rubric? Pairwise ranking? A numeric score? The evaluation prompt itself will heavily influence which candidate "wins." This prompt may need its own optimization.

3. What does "consistently" mean?
"Find prompts that consistently yield better outputs" — across all train plans? A majority? With what confidence threshold? A candidate that's great for 3 plans but terrible for 1 might still be worse overall.

4. MODEL_LIST is undefined.
Which models are being tested? Are you running each candidate prompt across multiple LLMs to find prompts that are model-robust, or optimizing per-model?

5. How are candidate prompts generated?
The doc describes the evaluation loop but not how new prompt variants are created. Manual authoring? LLM-generated rewrites? A mix?

6. "Rerun just that step" — dependency handling.
If you rerun step N with a new prompt, its output feeds into step N+1 in the real pipeline. Are you only evaluating step N's output in isolation, or propagating through downstream steps? Evaluating in isolation is faster but may miss regressions that only show up downstream.

7. Budget/cost controls.
You mention "it's very expensive to run the full pipeline." What about the cost of this optimization loop itself? With multiple models x multiple candidate prompts x multiple train plans x multiple iterations, this can get expensive fast. Consider setting a budget cap or max iterations.

8. The envvar for the dataset path — good instinct, but also specify a fallback or error message if it's unset.

## Suggestions

- Define a scoring rubric (even a simple 1-5 scale across 3-4 dimensions) before starting.
- Version-control the evaluation prompts alongside the system prompts.
- Consider running a baseline score for the current prompts first so you have a numeric starting point, not just pairwise comparisons.
- Add a "no regression" gate: the new prompt must not score worse on any plan by more than X%, even if average improves.


# Repo Structure

Two repos: the optimization engine lives in PlanExe, the data/artifacts live in a separate repo.

## Repo 1: `PlanExe` (existing — add optimization tooling)

```
worker_plan/
  worker_plan_internal/
    assume/
      identify_purpose.py          # contains SYSTEM_PROMPT (current)
      ...
    ...

prompt_optimizer/                   # NEW — the optimization engine
  __init__.py
  config.py                        # loads dataset config, env vars
  runner.py                        # reruns a single pipeline step with a candidate prompt
  evaluator.py                     # calls reasoning model to score/compare outputs
  scorer.py                        # rubric definition, numeric scoring
  candidate_generator.py           # generates prompt variants
  optimizer.py                     # orchestrates the train/verify loop (Stage 1-2)
  cli.py                           # CLI entry point

  rubrics/                          # evaluation rubrics per pipeline step
    identify_purpose.yaml
    make_assumptions.yaml
    ...

  tests/
    ...
```

This keeps the optimizer close to the code it's modifying — it needs to import pipeline tasks,
swap prompts, and run individual steps.

## Repo 2: [`PlanExe-prompt-lab`](https://github.com/PlanExeOrg/PlanExe-prompt-lab) (data repo)

```
README.md
dataset.json                        # train/verify split definition
populate_baseline.py                # script to populate baseline from zip files

baseline/                           # current outputs (extracted from dataset zips)
  train/
    20260310_hong_kong_game/
      001-1-start_time.json
      001-2-plan.txt
      ...
      030-report.html
    20250329_gta_game/
      ...
    20250321_silo/
      ...
    20260311_parasomnia_research_unit/
      ...
    20260308_sovereign_identity/
      ...
  verify/
    20260303_crate_recovery_campaign/
      ...
    20260215_nuuk_clay_workshop/
      ...
    (7 more plans)

history/                                      # captured output, global run counter
  # Path: history/{counter // 100}/{counter % 100:02d}_{step_name}/
  # Counter is auto-incremented: scan history/ for the highest existing
  # run number and add 1. No counter file needed.
  # Runs for different steps are interleaved chronologically.
  0/                                          # runs 0-99
  1/                                          # runs 100-199
  2/                                          # runs 200-299
    00_identify_purpose/                      # run 200
    01_identify_potential_levers/              # run 201
    02_identify_potential_levers/              # run 202
      meta.json                                # which step, which system prompt, what model used
      events.jsonl
      outputs.jsonl
      outputs/
        20250321_silo/
          002-9-potential_levers_raw.json
          002-10-potential_levers.json
          activity_overview.json
          usage_metrics.jsonl
        20260310_hong_kong_game/
        20260201_media_rescue/
    03_identify_potential_levers/
    ...
    98_identify_potential_levers/
    99_identify_potential_levers/
  3/
prompts/
  identify_potential_levers/
    prompt_0_e51751c30bc0c48402ecf759afdb996d8067cd8c5f057d0e242a9d93a856151e.txt      # prompt_index_sha.txt
    prompt_1_long-sha-here.txt
    prompt_2_long-sha-here.txt
analysis/
  0_identify_purpose/
  1_identify_potential_levers/
    summary.json                    # ranked candidates, aggregate scores
    failed_attempts.log

scores/                             # longitudinal tracking
  scoreboard.csv                    # step, date, baseline_score, best_score, delta
  history.json                      # full history for charting

full_plan_comparisons/              # Stage 3 periodic full-plan regenerations
  2026-03-20/
    hong_kong_game/
      030-report.html
    kpi_comparison.json
```

## Connecting the two repos

`dataset.json` defines the train/verify split. The `populate_baseline.py` script reads this file and extracts the zips into `baseline/`.

```json
{
  "comment": "Replace the zip files with your own. Run the populate_baseline.py script to populate the baseline/ directory.",
  "train": [
    "20260310_hong_kong_game.zip",
    "20250329_gta_game.zip",
    "20250321_silo.zip",
    "20260311_parasomnia_research_unit.zip",
    "20260308_sovereign_identity.zip"
  ],
  "verify": [
    "20260303_crate_recovery_campaign.zip",
    "20260215_nuuk_clay_workshop.zip",
    "20260202_heatwave_resilience.zip",
    "20260201_media_rescue.zip",
    "20260201_yellowstone_evacuation.zip",
    "20260131_clear_english.zip",
    "20260129_euro_adoption.zip",
    "20260114_cbc_validation.zip",
    "20251101_e_bus_security.zip"
  ]
}
```

## Why this split

- `PlanExe` stays clean — no multi-GB plan artifacts in the code repo.
- `PlanExe-prompt-lab` can use Git LFS for the zip files and large outputs.
- The data repo is a full audit trail — every candidate, evaluation, and score is committed.
- `scoreboard.csv` gives the metrics tracking at a glance.

## Feedback from Bubba (2026-03-13)

### Additional Questions & Gaps

**Evaluation prompt is itself a prompt — it needs the same rigor.**
The reasoning model used for comparison will be guided by an evaluation prompt. That prompt encodes the scoring rubric. If the evaluation prompt is poorly specified, the optimizer will find prompts that score well on the evaluator but don't actually produce better plans. The evaluation prompt should be versioned, reviewed, and held constant across a run (or explicitly varied as a separate experiment).

**Step isolation vs. cascade quality.**
Optimizing step N in isolation assumes that step N's output quality is a meaningful proxy for end-to-end plan quality. This may not hold: a step N output that scores 5/5 in isolation might feed step N+1 in a way that degrades the downstream result. Recommendation: after each isolated step optimization, run at least one full-pipeline spot check on the best candidate to confirm no downstream regressions before committing.

**`FAST_BUT_SKIP_DETAILS` vs. `ALL_DETAILS_BUT_SLOW` — which mode for the optimizer?**
The optimizer reruns individual pipeline steps. Those steps behave differently depending on `SPEED_VS_DETAIL`. Which mode should the optimizer use? Using `FAST_BUT_SKIP_DETAILS` is cheaper but may not reflect production output quality. This should be explicit in `meta.json` and the scoring rubric should account for it.

**Candidate prompt generation is the missing piece.**
The doc describes the evaluation loop thoroughly but says nothing about how candidate prompts are created. This is the creative/generative step that drives the whole system. Options to consider:
- LLM-generated rewrites (give the current prompt + failure examples to a reasoning model, ask for 3-5 variants)
- Manual authoring with structured variation (change one constraint at a time)
- Mutation from failed-attempts log (learn what patterns correlate with failure)
The choice here will determine how fast the optimizer converges.

### Implementation Suggestion: Prompt diff in `failed_attempts.log`

The `failed_attempts.log` currently captures that a candidate failed. It should also capture:
- The diff between the candidate prompt and the base prompt
- Which specific train plans it failed on (not just aggregate)
- The evaluator's reasoning (not just the score)

This turns the failure log into a learning dataset that can feed the next round of candidate generation.

### Implementation Suggestion: Freeze the evaluation model

The reasoning model used for comparison should be pinned to a specific model version (not a rolling alias) for the duration of an optimization run. Model updates can shift evaluation scores without any change to the system prompts being tested. `meta.json` should record the exact evaluator model used.
