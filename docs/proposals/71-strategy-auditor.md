# From Plan Generator to Autonomous Agent Auditor

**Date:** 26 February 2026  
**Authors:** Larry, Egon, Simon (for review)  
**Status:** Strategic Proposal for Feedback  

---

## Executive Summary

PlanExe was originally positioned as a plan *generator* — take a vague idea, have an LLM dream up a business plan. In 2025, we learned that LLMs hallucinate plans with no grounding. By 2026, the market has moved on: agents don't need another hallucinated plan generator.

**What agents actually need:** A trusted auditing layer that validates whether the assumptions driving their autonomous workflows are sane.

This proposal argues that PlanExe's real value in 2026 is as **the canonical auditing gate for autonomous agent loops** — not as a plan creator, but as a safety layer that prevents hallucinations before they propagate downstream.

---

## The Problem: Autonomous Agents in Bubbles

Agents run in isolation. They have no world model. They can't verify if their assumptions are grounded in reality. They hallucinate:
- Cost estimates that are off by orders of magnitude
- Timelines that ignore real-world constraints
- Team sizes that make no sense

**The consequence:** Bad assumptions → bad downstream decisions → failed autonomy.

Agents need an external oracle that can say: **"This assumption is grounded. Proceed."** or **"This looks hallucinated. Re-evaluate."**

---

## The Opportunity: Validation as a Service

**What we've built in Phase 1-2:**

1. **FermiSanityCheck (Phase 1)**: A validation gate that inspects every quantified assumption:
   - Are bounds present and non-contradictory?
   - Is the span ratio reasonable (≤100×)?
   - Does low-confidence claim have supporting evidence?
   - Do the numbers pass domain heuristics?
   
   **Output:** Structured JSON + Markdown that agents can parse deterministically.

2. **Domain-Aware Auditor (Phase 2)**: Auto-detect the domain (carpenter, dentist, personal project) and normalize to domain standards:
   - Currency → domain default + EUR for comparison
   - Units → metric
   - Confidence keywords → domain-aware signals
   
   **Why it matters:** "Cost 5000" means nothing without context. "5000 DKK for a carpenter project" is verifiable and sane. FermiSanityCheck becomes the translator.

---

## Why This Wins in the Agentic Economy

### 1. **Software Already Won the LLM Game**
Code is verifiable. It compiles or it doesn't. Tests pass or they don't. No trust required.

**Business plans?** No immediate validation. High trust requirement. High risk.

### 2. **Agents Are Untrusted Sources**
The lesson from 2025: don't trust the AI.

In 2026, agents will run in bubbles. External content will be labeled as untrusted to prevent prompt injection. But agents still need *some* external signal they can trust.

**PlanExe becomes that trusted signal.** It's not trying to out-think the agent; it's just saying: "Your assumption passes quantitative grounding. You can rely on it."

### 3. **Auditing is Composable**
Agents will chain together. Agent A's output becomes Agent B's input. Without a validation layer, assumptions compound into hallucinations.

**PlanExe sits in the middle:** catches bad assumptions before they propagate.

---

## The Business Model Shift

### Before (2025 thinking):
- Sell plans to humans
- Revenue: per-plan generation
- Value proposition: "Better plans than manual consulting"
- Problem: Plans are hallucinated; no immediate verification

### After (2026 reality):
- Sell validation to agents
- Revenue: per-assumption audited (or per-agent subscription)
- Value proposition: "Safe, trustworthy validation gate for autonomous loops"
- Advantage: Immediate, deterministic output (JSON); agents can compose it

---

## Implementation Path

### Phase 1: ✅ Done
- FermiSanityCheck validator
- DAG integration (MakeAssumptions → Validate → DistillAssumptions)
- Structured JSON output

### Phase 2: 🔄 In Progress
- Domain profiles (Carpenter, Dentist, Personal, Startup, etc.)
- Auto-detection + normalization
- Ready for integration testing

### Phase 3: Proposed
- Auditing API (agents call `/validate` with assumptions)
- Trust scoring (confidence + grounding + domain consistency)
- Audit logs (track what agents relied on)

---

## Key Questions for Simon

1. **Does this positioning resonate?** Are we solving the right problem for agents?

2. **Should we lean harder into auditor narrative?**
   - Update PRs to frame FermiSanityCheck as "validation gate for agents"
   - Reposition marketing toward agent platforms (not humans)
   - Build toward auditing API (Phase 3)

3. **Or stay hybrid?** Keep the plan-generator story + add auditing as a feature?

4. **What does success look like in 2026?**
   - Agents paying for validation service?
   - PlanExe as a required middleware in agentic workflows?
   - Something else?

---

## Next Steps

1. **Simon's feedback** on positioning (auditor vs. hybrid)
2. **Phase 2 completion** + integration testing
3. **PR updates** (if auditor positioning is approved)
4. **Phase 3 design** (auditing API + trust scoring)

---

**End of proposal.** Ready for Simon's thoughts.
