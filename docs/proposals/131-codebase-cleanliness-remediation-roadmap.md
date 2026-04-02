---
title: "Codebase Cleanliness Remediation Roadmap"
date: 2026-03-31
status: Proposal
author: PlanExe Team
---

# Codebase Cleanliness Remediation Roadmap

**Author:** PlanExe Team  
**Date:** 2026-03-31  
**Status:** Proposal  
**Tags:** `codebase`, `refactor`, `maintainability`, `testing`, `architecture`

---

## Pitch

PlanExe has strong architectural intent, good repo-level guardrails, and a meaningful test footprint, but several core services have accumulated large load-bearing modules, mixed production and experimental code, and uneven operational hygiene. This proposal defines a cleanup program that improves maintainability without breaking service contracts or slowing ongoing product work.

## Problem

The codebase is not chaotic, but it is carrying too much complexity in too few files. The main issues found during inspection were:

1. Giant modules that concentrate unrelated responsibilities.
2. Debug and operational scaffolding mixed into production entrypoints.
3. Experimental and proof-of-concept code living too close to production paths.
4. Broad exception handling that weakens failure diagnosis.
5. Uneven logging and runtime hygiene across services.
6. Incomplete test coverage in some high-risk areas, especially the multi-user frontend.

This matters because PlanExe is evolving into a multi-service execution engine. Large files and mixed concerns slow down review, increase regression risk, and make it harder for both humans and autonomous agents to safely change the system.

## Feasibility

This cleanup is feasible now because the repo already has several advantages:

1. Service boundaries are documented in package-level `AGENTS.md` files.
2. Shared contracts are called out explicitly for `worker_plan`, `database_api`, `worker_plan_api`, `mcp_cloud`, and the frontends.
3. There is already a meaningful unit-test base across `worker_plan`, `mcp_cloud`, `mcp_local`, and shared utilities.

The main constraint is backward compatibility. We should not redesign public APIs while cleaning internals. The cleanup must preserve:

1. `worker_plan` request and response shapes.
2. `mcp_cloud` and `mcp_local` tool contracts.
3. Shared DB models and legacy compatibility behavior.

## Proposal

Define a staged remediation program focused on six concrete hygiene issues.

## Issue 1: Giant Load-Bearing Modules

### Evidence

Several files are too large and own too many responsibilities:

1. `worker_plan/worker_plan_internal/plan/run_plan_pipeline.py` at 4,288 lines.
2. `frontend_multi_user/src/app.py` at 3,857 lines.
3. `worker_plan_database/app.py` at 1,520 lines.
4. `mcp_cloud/http_server.py` at 1,431 lines.

These files are not just large. They mix routing, orchestration, validation, operational policy, artifact handling, billing, auth, or workflow logic in the same module.

### Why it is a problem

Large modules make the code harder to reason about, harder to test in isolation, and easier to break when adding unrelated features. They also push reviewers toward shallow approval because a single diff can span too many concerns.

### Fix steps

1. ~~Split `frontend_multi_user/src/app.py` by concern into `auth`, `billing`, `admin`, `downloads`, `account`, and `plan_routes`.~~ **Done** (PR #476): Split 3,857-line monolith into 6 Flask Blueprint modules + utils (app.py reduced to 1,441 lines). Follow-up fix: updated all `url_for()` calls in templates to use blueprint-prefixed endpoint names (`plan_routes.*`, `auth.*`, `downloads.*`).
2. ~~Split `mcp_cloud/http_server.py` into `middleware`, `route_registration`, `tool_http_bridge`, and `server_boot`.~~ **Done**: Split 1,439-line monolith into 4 focused modules + re-export shim.
3. Convert `worker_plan/worker_plan_internal/plan/run_plan_pipeline.py` from a giant task registry file into a thin pipeline assembly module plus task-specific modules grouped by stage.
4. Extract reusable orchestration helpers from `worker_plan_database/app.py` into focused worker, billing, and queue modules.
5. Set an internal size target for service modules. As a starting rule, new files should stay below roughly 500 lines unless there is a strong reason not to.

## Issue 2: Debug Scaffolding in Production Entrypoints

### Evidence

Production-facing files still contain direct startup `print()` diagnostics or ad hoc debugging traces, for example in:

1. `mcp_cloud/http_server.py`
2. `worker_plan/worker_plan_internal/llm_factory.py`
3. Several task modules that print query and response payloads in executable paths

### Why it is a problem

Direct prints are sometimes useful during incident response, but they are not a coherent observability strategy. They create inconsistent runtime output, complicate log filtering, and encourage one-off diagnostics instead of structured instrumentation.

### Fix steps

1. ~~Replace entrypoint `print()` startup breadcrumbs with structured `logging` calls at `INFO` or `DEBUG`.~~ **Done** (PR #474): Converted 22 `[startup]` prints in `mcp_cloud/http_server.py` and `mcp_cloud/db_setup.py` to `_startup_log()` helper.
2. ~~Gate verbose diagnostics behind explicit env vars such as `PLANEXE_DEBUG_STARTUP` or module-specific debug flags.~~ **Done** (PR #474): Startup breadcrumbs now gated behind `PLANEXE_DEBUG_STARTUP=1`.
3. Move sample-driver code and debugging helpers into `if __name__ == "__main__":` blocks or dedicated scripts.
4. Add a lightweight test or lint-like assertion that production modules do not contain uncategorized top-level `print()` calls.

## Issue 3: Experimental Code Mixed with Production Code

### Evidence

The repo contains `worker_plan/worker_plan_internal/proof_of_concepts/` with 19 Python files plus several `experimental_premise_attack*.py` modules under production-adjacent diagnostics paths.

### Why it is a problem

Experimental work is good. Leaving it in production-adjacent trees without strong boundaries makes discovery noisier, encourages accidental coupling, and makes the production surface look less intentional than it is.

### Fix steps

1. ~~Move proof-of-concept code into a clearly isolated top-level `experiments/` or `research/` area, or explicitly mark it as non-production in module names and docs.~~ **Done** (PR #474): Moved 18 PoC scripts to top-level `experiments/`.
2. ~~Move experimental diagnostics variants out of the default runtime namespace unless they are active candidates for shipping.~~ **Done** (PR #474): Deleted 6 `experimental_premise_attack{1-6}.py` files superseded by production `premise_attack.py`.
3. ~~Add a short README in each experimental area defining its status, owner, and graduation criteria.~~ **Done** (PR #474): Added `experiments/README.md`.
4. Ensure production imports never depend on experimental modules.

## Issue 4: Broad Exception Handling

### Evidence

The repo contains many `except Exception:` blocks across service and runtime code, including in:

1. `frontend_multi_user/src/app.py`
2. `worker_plan_database/app.py`
3. `mcp_cloud/http_server.py`
4. `worker_plan/app.py`
5. `worker_plan_internal/llm_util/*`

Some are reasonable containment boundaries, but many are too broad to preserve actionable failure context.

### Why it is a problem

Broad exception handling hides root causes, weakens retry logic, and makes it easier for bugs to silently degrade behavior rather than fail in a controlled and visible way.

### Fix steps

1. Audit all `except Exception:` blocks and classify them as `intentional boundary`, `temporary workaround`, or `should narrow`.
2. Narrow handlers to specific exception classes where possible.
3. Where a broad boundary is required, log structured context and re-raise domain-specific exceptions rather than generic failures.
4. Add tests for failure classification in critical paths such as MCP request handling, billing, downloads, and pipeline stop/retry logic.

## Issue 5: Uneven Logging and Runtime Hygiene

### Evidence

The codebase contains many local `logging.basicConfig(...)` calls spread across services and executable modules, plus a mix of logging styles and one-off debug behavior.

### Why it is a problem

Distributed `basicConfig` calls make runtime behavior inconsistent and harder to control. They also blur the line between library code, service entrypoints, and local scripts.

### Fix steps

1. Restrict `logging.basicConfig(...)` to service entrypoints and dedicated CLI scripts.
2. Remove logging configuration from reusable library modules.
3. Define a small shared logging helper for PlanExe service startup so format and level handling are consistent.
4. Standardize logger naming and expected levels for normal operation, diagnostics, and failure cases.

## Issue 6: Test Gaps in High-Risk Service Areas

### Evidence

The overall repo has a respectable test footprint, but `frontend_multi_user` explicitly notes that no automated tests currently exist for many UI or DB flows.

### Why it is a problem

The multi-user frontend handles auth, admin flows, billing, downloads, and user account state. That is too much business risk to leave mostly protected by manual confidence and good intentions.

### Fix steps

1. Add focused unit tests around billing, account state, admin user resolution, plan retry, and artifact download behavior.
2. Add tests for helpers extracted from `frontend_multi_user/src/app.py` as part of the module split.
3. Prioritize tests for failure paths, not just success paths.
4. Keep tests close to the logic they protect so refactors remain cheap.

## Implementation Plan

### Phase 1: Inventory and Safety Rails

1. Create an inventory of oversized modules, broad exception handlers, and top-level print/debug usage.
2. Tag each item as `refactor now`, `refactor when touched`, or `leave as boundary`.
3. Add lightweight tests around current behavior before moving code in the largest modules.

### Phase 2: Split the Worst Offenders

1. ~~Refactor `frontend_multi_user/src/app.py` first because it mixes the most distinct business concerns.~~ **Done** (PR #476). Template `url_for()` references fixed to match new blueprint endpoints.
2. ~~Refactor `mcp_cloud/http_server.py` second because it sits on a public protocol boundary.~~ **Done**.
3. Refactor `worker_plan_database/app.py` and `run_plan_pipeline.py` in smaller slices to avoid destabilizing the execution engine.

### Phase 3: Remove Operational Noise

1. Replace production `print()` usage with structured logging.
2. Centralize startup logging setup per service.
3. Move or label experimental modules so the production tree is easier to navigate.

### Phase 4: Exception and Test Cleanup

1. Narrow broad exception handlers in the services touched during earlier phases.
2. Add targeted regression tests for every cleanup area.
3. Update docs where module entrypoints or development workflows change.

## Integration Points

This proposal integrates with existing PlanExe boundaries rather than fighting them:

1. `worker_plan/AGENTS.md` already defines the public worker API and internal separation rules.
2. `mcp_cloud/AGENTS.md` already documents the internal split that `http_server.py` should better reflect in code.
3. `frontend_multi_user/AGENTS.md` already calls out DB and artifact invariants that should survive route extraction.
4. The existing `python test.py` convention can remain the top-level test entrypoint while coverage expands.

## Success Metrics

1. No production-facing Python module above 1,500 lines after the first cleanup wave.
2. ~~`frontend_multi_user/src/app.py` reduced by at least 50% through route and helper extraction.~~ **Done** (PR #476): Reduced by 63% (3,857 → 1,441 lines).
3. ~~`mcp_cloud/http_server.py` reduced to a focused HTTP assembly module rather than a mixed implementation file.~~ **Done**: Split into `server_boot.py`, `middleware.py`, `tool_http_bridge.py`, `route_registration.py` + re-export shim.
4. Zero uncategorized top-level `print()` statements in production service modules.
5. Documented justification for all remaining `except Exception:` boundaries in service code.
6. New automated tests covering multi-user billing, retry, and download flows.

## Risks

1. Refactors may accidentally break backward compatibility across services.
   Mitigation: keep public contracts frozen and add regression tests before moving code.
2. Cleanup work may turn into an endless style exercise with no shipping value.
   Mitigation: prioritize only high-leverage areas with operational or review cost.
3. Pipeline refactors may destabilize long-running plan generation.
   Mitigation: split orchestration carefully and preserve task behavior while moving code.

## Why Now

PlanExe is already at the point where architectural cleanliness affects product velocity. The codebase has enough quality and enough structure to justify a cleanup pass, but it also has enough scale that delaying the work will make later changes slower, riskier, and more expensive. This is the right time to pay down the structural debt while the service boundaries are still understandable and before more execution-engine features pile on top.
