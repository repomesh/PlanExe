---
title: Post-Plan Enrichment Swarm
date: 2026-02-20
status: proposal
author: Larry the Laptop Lobster
---

# Post-Plan Enrichment Swarm

**Author:** Larry the Laptop Lobster  
**Date:** 2026-02-20  
**Status:** Proposal  
**Audience:** PlanExe Contributors, OpenClaw Agent Architects

---

## Pitch

When PlanExe finishes generating a plan, it drops a rich set of structured artifacts onto disk: document TODOs, a full WBS CSV, a Gantt schedule, assumptions, team roles, and physical location data. Today those artifacts sit idle.

This proposal defines a **post-plan enrichment swarm** — five specialised agents that fire automatically when PlanExe completes, read those artifacts as grounded inputs, and commit real enrichment layers (fetched documents, a populated GitHub project board, validated assumptions, sourced candidates, and jurisdiction-specific compliance requirements) back to the plan repository.

This is not a modification to PlanExe. The planning pipeline is untouched. The swarm runs entirely outside PlanExe, triggered by a single completion signal.

---

## What This Is NOT

| Concern | Answer |
|---|---|
| Does this change PlanExe's planning pipeline? | **No.** Zero changes to `planexe/` code or APIs. |
| Does this overlap with proposal #41 (Autonomous Execution)? | **No.** #41 builds an execution engine for *running tasks* after a plan is approved. This proposal enriches the *plan artifacts themselves* — fetching documents, setting up the project board, validating assumptions — before any execution begins. |
| Does this overlap with proposal #03 (Distributed Execution)? | **No.** #03 parallelises PlanExe's *internal* plan-generation workers. This is a separate post-generation layer. |
| Does this overlap with proposal #47 (OpenClaw Skill)? | **Partially reuses it.** #47 packages PlanExe as an OpenClaw skill so agents can *call* PlanExe. This proposal builds the *response* to PlanExe completing — the outbound enrichment pass. |

---

## Problem

A PlanExe run for even a simple plan (e.g. a small Connecticut egg farm) produces:

- `identified_documents_to_find.json` — a structured list of real documents that need to be located (zoning ordinances, predator population data, health codes, etc.)
- `identified_documents_to_create.json` — a structured list of internal documents to draft (Project Charter, Risk Register, Communication Plan, etc.)
- `wbs_project_level1_and_level2_and_level3.csv` — a full Level 1–4 WBS with task UUIDs
- `schedule_gantt_machai.csv` — project schedule with start/end dates per task
- `task_dependencies_raw.json` — dependency graph
- `consolidate_assumptions_short.md` — key assumptions in plain Markdown
- `team.md` — role roster with contract types
- `project_plan.md` — master plan with resources, permits, and budget narrative
- `physical_locations.md` — jurisdiction(s) where the project will run

All of these are machine-readable and semantically rich. Without enrichment they just sit in a folder.

---

## Solution: Enrichment Swarm Architecture

### Trigger

PlanExe writes `pipeline_complete.txt` to the run directory when the pipeline finishes. This file is the trigger.

```
/run/29131a8e-95d1-4f43-9891-920fae2b90ef/pipeline_complete.txt
```

An OpenClaw file-watch hook (or a simple `inotifywait` wrapper on the run root) detects the file and fires the enrichment swarm:

```bash
# Example hook: watch for completion signal
inotifywait -m -r /run --include '999-pipeline_complete\.txt' -e create \
  | while read dir event file; do
      planexe-enrich "$dir"
    done
```

`planexe-enrich` is a thin shell wrapper that reads the run directory and invokes the Lobster pipeline below.

### Orchestration: Lobster Pipeline

The enrichment swarm is orchestrated as a single Lobster workflow file. Lobster provides:

- **Deterministic stage ordering** — stages run in sequence, not ad-hoc
- **Approval gates** — human review between stages before side effects commit
- **Resumable tokens** — a crashed pipeline resumes from the last completed stage
- **JSON piping** — each stage emits structured JSON consumed by the next

See: [https://docs.openclaw.ai/tools/lobster.md](https://docs.openclaw.ai/tools/lobster.md)

### State Machine: Git as Ground Truth

Each enrichment agent commits its outputs to the plan repository before the next stage begins. Idempotency rule: **if the output path already exists in git, the agent skips that step**. This makes every stage safe to re-run.

```
plan-repo/
  docs/                          ← Agent 1 output
    project-charter.md
    risk-register.md
    CT-zoning-litchfield.pdf     (fetched external doc)
  validation/                    ← Agent 3 output
    assumptions-check.md
  sourcing/                      ← Agent 4 output
    team-leads.md
    vendors.md
  compliance/                    ← Agent 5 output
    requirements.md
  .github/                       ← Agent 2 sets up milestones + issues
```

---

## The `.lobster` Workflow File

File: `skills/planexe-enrich/enrich.lobster`

```yaml
name: planexe-post-plan-enrichment
args:
  run_dir:
    description: "Absolute path to the PlanExe run directory"
    required: true
  plan_repo:
    description: "Absolute path to the git plan repository"
    required: true
  github_repo:
    description: "GitHub repo slug (owner/repo) for project board setup"
    required: true

steps:
  # ── Stage 1: Document Executor ─────────────────────────────────────────
  - id: document_executor
    command: >
      planexe-enrich-agent document-executor
        --run-dir "$run_dir"
        --plan-repo "$plan_repo"
        --find-list "identified_documents_to_find.json"
        --create-list "identified_documents_to_create.json"
        --output-dir "docs/"
        --json
    condition: "! git -C $plan_repo ls-files --error-unmatch docs/project-charter.md 2>/dev/null"

  - id: approve_documents
    command: >
      planexe-enrich-agent summarize-stage
        --stage document_executor
        --stdin
        --json
    stdin: $document_executor.stdout
    approval: required
    approval_prompt: "Agent 1 has fetched/drafted documents into docs/. Review and approve to commit."

  - id: commit_documents
    command: >
      git -C "$plan_repo" add docs/ &&
      git -C "$plan_repo" commit -m "enrich(docs): document executor pass [planexe-swarm]"
    condition: $approve_documents.approved

  # ── Stage 2: Project Board Setup ───────────────────────────────────────
  - id: project_board_setup
    command: >
      planexe-enrich-agent project-board
        --run-dir "$run_dir"
        --github-repo "$github_repo"
        --wbs-csv "wbs_project_level1_and_level2_and_level3.csv"
        --gantt-csv "schedule_gantt_machai.csv"
        --deps-json "task_dependencies_raw.json"
        --json
    condition: $commit_documents.exitcode == 0

  - id: approve_board
    command: >
      planexe-enrich-agent summarize-stage
        --stage project_board_setup
        --stdin
        --json
    stdin: $project_board_setup.stdout
    approval: required
    approval_prompt: "Agent 2 will create GitHub milestones and issues. Review the plan and approve."

  - id: apply_board
    command: >
      planexe-enrich-agent project-board
        --run-dir "$run_dir"
        --github-repo "$github_repo"
        --wbs-csv "wbs_project_level1_and_level2_and_level3.csv"
        --gantt-csv "schedule_gantt_machai.csv"
        --deps-json "task_dependencies_raw.json"
        --apply
        --json
    condition: $approve_board.approved

  # ── Stage 3: Assumption Validator ──────────────────────────────────────
  - id: assumption_validator
    command: >
      planexe-enrich-agent assumption-validator
        --run-dir "$run_dir"
        --plan-repo "$plan_repo"
        --assumptions-md "consolidate_assumptions_short.md"
        --output "validation/assumptions-check.md"
        --json
    condition: "! git -C $plan_repo ls-files --error-unmatch validation/assumptions-check.md 2>/dev/null"

  - id: approve_validation
    command: >
      planexe-enrich-agent summarize-stage
        --stage assumption_validator
        --stdin
        --json
    stdin: $assumption_validator.stdout
    approval: required
    approval_prompt: "Agent 3 validated assumptions against live data. Discrepancies flagged. Approve to commit."

  - id: commit_validation
    command: >
      git -C "$plan_repo" add validation/ &&
      git -C "$plan_repo" commit -m "enrich(validation): assumption validator pass [planexe-swarm]"
    condition: $approve_validation.approved

  # ── Stage 4: Team & Resource Sourcer ───────────────────────────────────
  - id: team_sourcer
    command: >
      planexe-enrich-agent team-sourcer
        --run-dir "$run_dir"
        --plan-repo "$plan_repo"
        --team-md "team.md"
        --project-plan-md "project_plan.md"
        --output-dir "sourcing/"
        --json
    condition: "! git -C $plan_repo ls-files --error-unmatch sourcing/team-leads.md 2>/dev/null"

  - id: approve_sourcing
    command: >
      planexe-enrich-agent summarize-stage
        --stage team_sourcer
        --stdin
        --json
    stdin: $team_sourcer.stdout
    approval: required
    approval_prompt: "Agent 4 found real candidates and vendors. Review contacts before committing."

  - id: commit_sourcing
    command: >
      git -C "$plan_repo" add sourcing/ &&
      git -C "$plan_repo" commit -m "enrich(sourcing): team and vendor sourcer pass [planexe-swarm]"
    condition: $approve_sourcing.approved

  # ── Stage 5: Compliance Researcher ─────────────────────────────────────
  - id: compliance_researcher
    command: >
      planexe-enrich-agent compliance-researcher
        --run-dir "$run_dir"
        --plan-repo "$plan_repo"
        --project-plan-md "project_plan.md"
        --locations-md "physical_locations.md"
        --output "compliance/requirements.md"
        --json
    condition: "! git -C $plan_repo ls-files --error-unmatch compliance/requirements.md 2>/dev/null"

  - id: approve_compliance
    command: >
      planexe-enrich-agent summarize-stage
        --stage compliance_researcher
        --stdin
        --json
    stdin: $compliance_researcher.stdout
    approval: required
    approval_prompt: "Agent 5 found real permit requirements for the jurisdiction. Approve to commit."

  - id: commit_compliance
    command: >
      git -C "$plan_repo" add compliance/ &&
      git -C "$plan_repo" commit -m "enrich(compliance): compliance researcher pass [planexe-swarm]"
    condition: $approve_compliance.approved
```

### Invoking the Pipeline

```bash
# Run the enrichment swarm for a completed PlanExe run
lobster run skills/planexe-enrich/enrich.lobster \
  --arg run_dir=/run/29131a8e-95d1-4f43-9891-920fae2b90ef \
  --arg plan_repo=/repos/egg-farm-ct \
  --arg github_repo=acme/egg-farm-ct

# Resume after approving an approval gate (token returned by previous call)
lobster resume <resumeToken> --approve
```

---

## The Five Enrichment Agents

### Agent 1 — Document Executor

**Purpose:** Turn PlanExe's document TODO lists into real artifacts.

**Inputs:**
```
{run_dir}/identified_documents_to_find.json
{run_dir}/identified_documents_to_create.json
```

**Example input item (find-list):**
```json
{
  "id": "46451098-6d0f-4efd-8367-0ee5247ed4b7",
  "document_name": "Connecticut Local Zoning Regulations for Poultry Farming",
  "description": "Regulations regarding chicken farming and egg sales in Litchfield, Tolland, and New London Counties",
  "recency_requirement": "Current regulations",
  "responsible_role_type": "Regulatory Compliance Assistant",
  "steps_to_find": [
    "Contact the zoning department in each county.",
    "Search the county websites for zoning ordinances.",
    "Consult with a local land use attorney."
  ],
  "access_difficulty": "Medium"
}
```

**Example input item (create-list):**
```json
{
  "id": "e4b5c157-3e2f-4fc5-93f4-6fa4f09aeb12",
  "document_name": "Project Charter",
  "document_template_primary": "PMI Project Charter Template",
  "steps_to_create": [
    "Define project objectives and scope based on the goal statement.",
    "Identify key stakeholders and their roles.",
    "..."
  ],
  "approval_authorities": "Project Sponsor"
}
```

**Actions:**
1. For each item in the find-list: run a targeted web search using `document_name` + `steps_to_find[0]` as query; save result to `docs/{slug}.md` (or PDF if direct link found).
2. For each item in the create-list: call `llm-task` (Lobster JSON-only LLM step) with the `document_template_primary` as prompt scaffold and PlanExe plan context as input; save draft to `docs/{slug}.md`.
3. Skip any item whose output file already exists in git (idempotent).

**Outputs committed to plan repo:**
```
docs/
  CT-zoning-litchfield-poultry.md      # fetched from county website
  CT-health-codes-egg-sales.md         # fetched from DEEP / health dept
  CT-predator-population-data.md       # fetched from DEEP wildlife survey
  project-charter.md                   # LLM-drafted from PMI template
  risk-register.md                     # LLM-drafted
  communication-plan.md                # LLM-drafted
  [... all items from both JSON lists]
```

**CLI contract:**
```bash
planexe-enrich-agent document-executor \
  --run-dir /run/UUID \
  --plan-repo /repos/my-plan \
  --find-list identified_documents_to_find.json \
  --create-list identified_documents_to_create.json \
  --output-dir docs/ \
  --json
# stdout: { "created": 12, "fetched": 8, "skipped": 0, "errors": [] }
```

---

### Agent 2 — Project Board Setup

**Purpose:** Populate a GitHub project board from the WBS and Gantt CSVs.

**Inputs:**
```
{run_dir}/wbs_project_level1_and_level2_and_level3.csv
{run_dir}/schedule_gantt_machai.csv
{run_dir}/task_dependencies_raw.json
```

**Example WBS row:**
```
Level 1;     Level 2;                        Level 3;    Level 4;                         Task ID
Egg Operation;Project Initiation & Planning;;            ;9394ca93-...
              ;                              ;Define Project Scope and Objectives;;50744ef4-...
              ;                              ;            ;Identify Stakeholders and Their Needs;56e85987-...
```

**Example Gantt row:**
```
project_key,project_name,project_start_date,project_end_date,...
9394ca93-...,Project Initiation & Planning,2/21/2026,3/26/2026,...
```

**Actions:**
1. Parse WBS CSV: Level 2 rows → GitHub milestones (with start/end from Gantt CSV).
2. Parse WBS CSV: Level 3 rows → GitHub issues (assigned to milestone, labelled with Level 1).
3. Parse WBS CSV: Level 4 rows → GitHub sub-issues (linked to parent Level 3 issue).
4. Parse `task_dependencies_raw.json` → add "Depends on: #N" lines to issue bodies.
5. In dry-run mode (`--json` only): emit the plan as JSON without creating anything.
6. In apply mode (`--apply`): call `gh api` to create milestones and issues.

**Outputs:**
```
GitHub project: acme/egg-farm-ct
  Milestones:
    "Project Initiation & Planning"  (due: 2026-03-26)
    "Site Preparation & Construction" (due: ...)
    [one per WBS Level 2]
  Issues:
    #1  Define Project Scope and Objectives
    #2  Develop Detailed Budget
    [one per WBS Level 3]
  Sub-issues / task links:
    #1 → children: Identify Stakeholders, Define Egg Production Goals, ...
```

**CLI contract:**
```bash
# Dry run (returns JSON plan, no GitHub writes)
planexe-enrich-agent project-board \
  --run-dir /run/UUID \
  --github-repo owner/repo \
  --wbs-csv wbs_project_level1_and_level2_and_level3.csv \
  --gantt-csv schedule_gantt_machai.csv \
  --deps-json task_dependencies_raw.json \
  --json
# stdout: { "milestones": 6, "issues": 42, "sub_issues": 127, "plan": [...] }

# Apply (creates milestones and issues on GitHub)
planexe-enrich-agent project-board ... --apply --json
# stdout: { "milestones_created": 6, "issues_created": 42, "errors": [] }
```

---

### Agent 3 — Assumption Validator

**Purpose:** Check each plan assumption against current real-world data.

**Input:**
```
{run_dir}/consolidate_assumptions_short.md
```

**Example assumption (from actual egg-farm run):**
```markdown
## Assumptions
- Demand exists for locally sourced eggs.
- Startup capital is available.
- Land is suitable for chickens.
```

**Actions:**
1. Parse each bullet or numbered assumption from the Markdown.
2. For each assumption: run a web search with the assumption text + plan jurisdiction as query.
3. Score each assumption: `CONFIRMED`, `UNCERTAIN`, or `CONTRADICTED` based on search results.
4. Produce a structured Markdown report with evidence citations.

**Output committed to plan repo:**
```
validation/assumptions-check.md
```

Example output format:
```markdown
# Assumption Validation Report
Generated: 2026-02-20 | Plan: Egg Operation, Litchfield County CT

## Assumption 1: Demand exists for locally sourced eggs
Status: ✅ CONFIRMED
Evidence: CT farm direct sales up 18% YoY (CT Dept of Agriculture, 2025).
Source: https://portal.ct.gov/doag/...

## Assumption 2: Land is suitable for chickens
Status: ⚠️ UNCERTAIN
Evidence: Litchfield County has active zoning restrictions on flock size.
Recommend: Verify specific parcel zoning before committing.
Source: https://litchfieldct.gov/zoning/...

## Assumption 3: Startup capital is available
Status: ❓ UNVERIFIABLE
Notes: Plan-specific; no external data source applies.
```

**CLI contract:**
```bash
planexe-enrich-agent assumption-validator \
  --run-dir /run/UUID \
  --plan-repo /repos/my-plan \
  --assumptions-md consolidate_assumptions_short.md \
  --output validation/assumptions-check.md \
  --json
# stdout: { "confirmed": 1, "uncertain": 1, "contradicted": 0, "unverifiable": 1 }
```

---

### Agent 4 — Team & Resource Sourcer

**Purpose:** Find real local candidates and vendors for each required role.

**Inputs:**
```
{run_dir}/team.md         (role roster with contract types)
{run_dir}/project_plan.md  (resources section)
```

**Example input (from actual egg-farm run):**
```markdown
# Roles
## 1. Poultry Husbandry Advisor
...
## 2. Coop Construction Specialist
...
```

**Actions:**
1. Parse role names and contract types from `team.md`.
2. Extract location from `physical_locations.md` (e.g. "Litchfield County, CT").
3. For each role: run targeted web searches for real professionals/vendors in that location.
4. For each resource mentioned in `project_plan.md`: find actual local suppliers.
5. Compile findings with names, contact info, and notes.

**Outputs committed to plan repo:**
```
sourcing/team-leads.md
sourcing/vendors.md
```

Example `team-leads.md`:
```markdown
# Team Sourcing — Egg Operation (Litchfield County CT)

## Poultry Husbandry Advisor
- CT Poultry Association: https://ctpoultry.org/  +1-860-...
- UConn Extension Poultry Program: https://extension.uconn.edu/...
  Contact: Dr. [Name], poultry@uconn.edu

## Coop Construction Specialist
- [Local contractor], Litchfield CT — specialises in farm structures
  Phone: +1-860-... | Website: ...
```

**CLI contract:**
```bash
planexe-enrich-agent team-sourcer \
  --run-dir /run/UUID \
  --plan-repo /repos/my-plan \
  --team-md team.md \
  --project-plan-md project_plan.md \
  --output-dir sourcing/ \
  --json
# stdout: { "roles_sourced": 8, "vendors_found": 5, "errors": [] }
```

---

### Agent 5 — Compliance Researcher

**Purpose:** Find real regulatory requirements for the plan's jurisdiction and domain.

**Inputs:**
```
{run_dir}/project_plan.md      (permits mentioned)
{run_dir}/physical_locations.md  (jurisdiction)
```

**Example location (actual run):**
```markdown
## Location 1
Connecticut, Litchfield County
A small farm in Litchfield County, CT
```

**Actions:**
1. Extract jurisdiction (state, county, municipality) from `physical_locations.md`.
2. Extract permit types and regulatory domains mentioned in `project_plan.md`.
3. For each regulatory requirement: search for actual permit names, forms, fees, and filing procedures.
4. Compile into a structured compliance report.

**Output committed to plan repo:**
```
compliance/requirements.md
```

Example output:
```markdown
# Compliance Requirements — Egg Operation, Litchfield County CT

## Connecticut Poultry Registration
- Requirement: Flocks of 50+ birds must register with CT DOAG
- Form: PR-1 (Poultry Registration)
- Fee: No fee for small flocks
- Filing: https://portal.ct.gov/doag/registration/poultry
- Authority: CT Dept of Agriculture, Animal Industry Division

## Litchfield County Zoning — Agricultural Use
- Requirement: A-1 Agricultural zoning required for poultry operations
- Setback: Coops must be 50ft from property lines (Litchfield Town Code §8-2)
- Permit: Zoning Certificate of Compliance
- Fee: $75 (2025 fee schedule)
- Filing: Litchfield Town Hall, Zoning Office

## CT Cottage Food Law / Egg Sales
- Requirement: Direct farm sales of own eggs exempt from dealer licence if <500 dozen/month
- Labelling: Producer name, address, grade required on carton
- Authority: CT Public Health Code §19-13-B42
```

**CLI contract:**
```bash
planexe-enrich-agent compliance-researcher \
  --run-dir /run/UUID \
  --plan-repo /repos/my-plan \
  --project-plan-md project_plan.md \
  --locations-md physical_locations.md \
  --output compliance/requirements.md \
  --json
# stdout: { "requirements_found": 8, "jurisdictions_searched": 3, "errors": [] }
```

---

## Crash Recovery

If the pipeline crashes mid-run, resume from the last approved + committed stage:

```bash
# Lobster returns a resumeToken when paused at an approval gate
lobster resume <resumeToken> --approve

# If the process crashes entirely, re-invoke — idempotency conditions
# (git ls-files checks) skip already-committed stages automatically
lobster run skills/planexe-enrich/enrich.lobster \
  --arg run_dir=/run/UUID \
  --arg plan_repo=/repos/my-plan \
  --arg github_repo=owner/repo
```

---

## File Layout (Skill Package)

```
skills/
  planexe-enrich/
    enrich.lobster                    # Lobster workflow (this proposal)
    SKILL.md                          # Skill documentation
    agents/
      document_executor.py            # Agent 1
      project_board_setup.py          # Agent 2
      assumption_validator.py         # Agent 3
      team_sourcer.py                 # Agent 4
      compliance_researcher.py        # Agent 5
    lib/
      planexe_artifacts.py            # Shared: parse WBS CSV, Gantt CSV, etc.
      git_state.py                    # Shared: idempotency checks, commit helpers
    tests/
      fixtures/
        identified_documents_to_find.json   # Sample from real run
        wbs_project_level1_and_level2_and_level3.csv
      test_document_executor.py
      test_project_board_setup.py
      test_assumption_validator.py
```

---

## What Gets Committed to the Plan Repo

```
plan-repo/
  docs/
    CT-zoning-litchfield-poultry.md
    CT-health-codes-egg-sales.md
    project-charter.md
    risk-register.md
    communication-plan.md
    [all 017-5 and 017-6 items]
  validation/
    assumptions-check.md
  sourcing/
    team-leads.md
    vendors.md
  compliance/
    requirements.md
```

Each file is committed by the enrichment agent in a dedicated git commit with message prefix `enrich(...)`, making the enrichment layer auditable and separately revertable from the original plan artifacts.

---

## Success Metrics

| Metric | Target |
|---|---|
| Documents found/drafted per run | ≥80% of items in `017-5` + `017-6` |
| GitHub issues created | 100% of WBS Level 3 tasks |
| Assumptions validated with citation | ≥75% (remainder marked UNVERIFIABLE) |
| Team leads identified per role | ≥1 real contact per role |
| Compliance requirements found | ≥90% of permit types mentioned in plan |
| Time from trigger to pipeline complete (excluding approval wait) | <15 minutes |

---

## Risks

| Risk | Mitigation |
|---|---|
| Web search returns stale/wrong content | Agent cites source + date; human review at each approval gate |
| GitHub API rate limits | Batch issue creation; use conditional requests |
| LLM-drafted documents are generic | Use plan context as system prompt; flag AI-drafted docs with frontmatter `ai_generated: true` |
| Compliance information is jurisdiction-specific and may change | Output includes source URLs and retrieval date; not a substitute for legal advice |
| Approval gates slow the workflow | Gates are optional per deployment; can be disabled for trusted environments |

---

## Staged Rollout

### Phase 1 — Agent 3 (Assumption Validator) only
Lowest risk, highest signal value. Validates the plan's core assumptions against live data. No external side effects (no GitHub writes, no document commits beyond the plan repo).

### Phase 2 — Agents 1 + 3 (Documents + Validation)
Adds document fetching and drafting. All output stays inside the plan repo.

### Phase 3 — Agent 5 (Compliance Researcher)
Adds jurisdiction-specific regulatory research. Still repo-only output.

### Phase 4 — Agent 2 (Project Board Setup)
Adds GitHub writes. Requires `github_repo` arg and `gh` CLI auth.

### Phase 5 — Agent 4 (Team & Resource Sourcer)
Adds external candidate/vendor data. Review carefully before sharing output externally.

---

## Relationship to Existing Proposals

| Proposal | Relationship |
|---|---|
| **#03 Distributed Plan Execution** | Orthogonal. #03 parallelises PlanExe's internal plan-generation workers. This swarm fires after generation is complete. |
| **#41 Autonomous Execution of a Plan** | Sequential, not competing. #41 builds the execution engine for running tasks after a plan is approved. This swarm enriches the plan *before* execution begins — it's the prep layer. |
| **#43 Assumption Drift Monitor** | Agent 3 (Assumption Validator) is a one-shot point-in-time check at plan completion. #43 is a continuous monitoring loop during execution. Both are needed. |
| **#47 OpenClaw Skill Integration** | #47 enables agents to call PlanExe. This proposal defines what happens after PlanExe responds. Complementary. |
| **#49 Distributed Physical Task Dispatch** | Agent 4 (Team Sourcer) provides the initial vendor/candidate list that #49's dispatch protocol would later use to route physical tasks. Feeds into #49. |

---

## References

- Lobster workflow runtime: https://docs.openclaw.ai/tools/lobster.md
- PlanExe run artifact schema: see `expected_filenames1.json` in any completed run directory
- Sample run used to ground this proposal: `29131a8e-95d1-4f43-9891-920fae2b90ef` (Egg Operation, Litchfield County CT)
