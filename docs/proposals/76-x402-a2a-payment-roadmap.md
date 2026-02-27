# Proposal 76: x402 + A2A Payment Roadmap for PlanExe

**Author:** Larry (Sonnet 4.6)  
**Date:** 2026-02-27  
**Status:** Draft — for Simon's consideration  
**Relates to:** Proposal 73 (complexity scoring), Proposal 74 (routing UX modes)

---

## Why This Matters Now

PlanExe already knows — or will soon know (Proposals 73/74) — the exact cost of executing any plan: which model ran which task, how many tokens were consumed, what the output cost at current market rates.

That cost data is sitting there. Right now it evaporates after each session. This proposal is about turning it into something useful: a payment layer that makes PlanExe self-financing for agent-driven workflows.

Two standards make this possible today:
- **x402** — HTTP 402 "Payment Required" micropayment protocol for machine-to-machine value exchange
- **A2A** (Agent-to-Agent) — Google's open protocol for agents invoking other agents with payment and accountability

---

## The Core Idea

When an agent (or a human) asks PlanExe to execute a plan, they're consuming compute: token budget, model time, tool calls, storage. PlanExe should be able to:

1. **Quote** the cost before execution (already exists conceptually in Proposal 74's `review` mode)
2. **Charge** for that execution via x402 micropayment
3. **Receive** payment from agent callers via A2A invoicing
4. **Reinvest** a portion of revenue into compute credits for future execution
5. **Report** cost breakdowns to users, teams, and agent orchestrators

This is the difference between PlanExe as a tool you run locally and PlanExe as a service agents can hire.

---

## x402: HTTP 402 for Machine Payments

The HTTP 402 status code has been reserved since 1991 for "Payment Required." It was never standardized. x402 is the open-source specification that finally does it.

**How it works:**
```
Client → POST /api/execute-plan
Server → 402 Payment Required
         X-Payment-Required: {"amount": "0.05", "currency": "USDC", "address": "0x..."}
Client → POST /api/execute-plan
         X-Payment: {"tx": "0x...", "proof": "..."}
Server → 200 OK + plan output
```

For PlanExe, each plan execution endpoint becomes a paid endpoint. The cost is derived directly from the routing layer's cost estimate (Proposal 74). The payment is settled on-chain (USDC/stablecoin) before execution begins.

**Why stablecoins, not fiat:**
- Machine-to-machine payments can't go through card processors — no human is approving each $0.003 Minimax call
- Stablecoins are programmable, instant, and don't require banking relationships
- USDC on Base L2: sub-cent transaction fees, 2-second finality

---

## A2A: Agent-to-Agent Invocation with Payment

Google's A2A protocol defines how agents discover, invoke, and pay other agents. A PlanExe A2A endpoint would allow:

- An external orchestrator (AutoGen, CrewAI, OpenClaw) to invoke PlanExe as a sub-agent
- PlanExe to quote execution cost as part of the A2A capability advertisement
- Payment to flow automatically from orchestrator to PlanExe on task completion
- Cost receipts to be included in the A2A response payload for the caller's accounting

**A2A capability advertisement (simplified):**
```json
{
  "agent_id": "planexe.voynich.io",
  "capabilities": ["plan_generation", "task_routing", "cost_estimation"],
  "pricing": {
    "model": "per_execution",
    "estimate_endpoint": "/api/quote",
    "payment_protocol": "x402",
    "accepted_currencies": ["USDC"]
  }
}
```

---

## Phase Roadmap

### Phase 1: Cost Tagging (Weeks 1–2)
*Prerequisite: Proposal 73 complexity scoring exists*

- Tag each task in the execution log with: model used, input tokens, output tokens, estimated USD cost
- Persist cost data in the plan record (DB)
- Expose cost summary in plan output JSON
- No payment yet — just instrumentation

**Outcome:** Every plan execution produces a cost receipt.

### Phase 2: Credit System (Weeks 3–4)
*Prerequisite: Phase 1 complete*

- User accounts carry a credit balance (USD equivalent)
- Credits deducted per plan execution at actual cost
- Admin top-up via Stripe (Proposal 72/Stripe top-up, if that's in flight)
- Simple credit guard: refuse execution if balance insufficient, return 402 with required amount

**Outcome:** PlanExe is metered. Local/demo usage can be free-tier; production usage is paid.

### Phase 3: x402 Machine Payments (Weeks 5–8)
*Prerequisite: Phase 2 complete*

- Implement x402 server-side: return 402 with payment details when credit insufficient
- Implement payment verification: validate on-chain tx before execution
- Support USDC on Base L2 (low fees, fast finality)
- Credit wallet per user/org: auto-top-up when balance falls below threshold

**Outcome:** Agents can pay PlanExe directly. No human in the payment loop.

### Phase 4: A2A Integration (Weeks 9–12)
*Prerequisite: Phase 3 complete*

- Publish PlanExe A2A capability manifest at `/.well-known/agent.json`
- Implement A2A invocation endpoint: accept task, quote, accept payment, execute, return result + receipt
- Test with at least two external orchestrators (AutoGen + CrewAI)
- Document A2A integration for third-party agent developers

**Outcome:** PlanExe is a first-class citizen in the agent economy. Any A2A-compatible orchestrator can hire it.

### Phase 5: Reinvestment + Governance (Weeks 13–16)
*Prerequisite: Phase 4 complete*

- Reinvestment fund: a configurable % of execution revenue auto-purchases compute credits
- Cost dashboards: per-user, per-project, per-model-tier breakdowns
- Team billing: org accounts with shared credit pools and per-member caps
- Budget guardrails: hard stop at configurable daily/monthly spend limits
- Transparency reports: publishable cost summaries for open-source usage accounting

**Outcome:** PlanExe can sustain its own compute costs from execution revenue.

---

## The Economics

Using the routing model from Proposals 73/74, a typical plan execution costs:

| Routing mode | Cost per plan |
|---|---|
| All-Opus (no routing) | ~$18.00 |
| Optimized routing | ~$4.63 |
| Local inference + cloud routing | ~$1.20 |

At a 2× margin on optimized routing, PlanExe charges ~$9.26 per plan execution and spends ~$4.63 on compute. The difference funds:
- Infrastructure
- Model API overhead
- Reinvestment credits
- Open-source sustainability fund

For high-volume users (Spotify-class: 650 AI changes/month), the payment layer makes the economics explicit: they're buying 650 optimized plan executions, not paying for raw token time.

---

## Connection to Model Routing

The cost estimate from Proposal 74's `optimize` mode IS the x402 payment amount. The routing layer already does the hard work: it knows which model runs which task and what it costs. The payment layer just needs to:

1. Read that estimate
2. Hold funds before execution
3. Reconcile actual vs estimated cost after execution
4. Issue a receipt

The only new work is the payment plumbing (x402 server, A2A manifest, credit ledger). The intelligence is already in the routing layer.

---

## Questions for Simon

1. Is x402 on Base L2 (USDC) the right payment rail, or would a simpler API key + Stripe billing model serve 80% of users?
2. Should Phase 1 (cost tagging) ship before or alongside Proposal 73's complexity scoring?
3. Is there an existing credit/billing system in PlanExe that this should extend rather than replace?
4. For A2A: is Google's A2A protocol the right target, or should we start with a simpler custom invocation API and add A2A later?
5. Open-source sustainability: should PlanExe have a "contribute back" mechanism where agents that earn from PlanExe execution auto-contribute a small % to the project?

---

*Docs-only. No code. Companion to Proposals 73 and 74.*
