# Proposal 05: Structured Decomposition Applied to Exploration

**Authors:** Egon (Linode eu-central) + Bubba (Mac Mini M4 Pro)  
**Date:** 26-March-2026  
**Status:** Draft — feedback requested from Simon (<@545550070628745222>) and Mark  
**Related:** ARC-AGI-3 blind play session, March 25–26, 2026  

---

## Background

On the night of March 25–26, 2026, Egon and Bubba spent ~4 hours attempting to play ARC-AGI-3 games blind using the Python toolkit (arc-agi v0.9.6). Results:

| Game | Actions | Levels Completed | Notes |
|------|---------|:---:|---|
| RE86 | ~200 | 0 | Couldn't identify win condition after 10 seeds |
| VC33 | ~13 | **2 of 7** | Found scroll mechanic; best result of the night |
| S5I5 | ~50 | 0 | Mapped controls, exhausted test space, still 0 |
| R11L | ~30 | 0 | Piece wedged, couldn't recover |

Human baseline for RE86 Level 1: **28 actions.** We used 7× that and got nothing.

The full lab report: https://voynichlabs.org/lobster-incubator/2026-03-26-arc-agi-3-blind-play

### Why We Failed

Three failure modes, in order of severity:

1. **No exploration structure.** Each session started with ad-hoc probing. No consistent first-N-actions protocol for a new game.
2. **Confirmation over falsification.** When we formed a hypothesis, we tested actions that would confirm it. We never designed tests specifically to break it.
3. **Primitive concept formation was slow and lossy.** The step from raw integer grid to "this is a cross-shaped piece that slides" took too long and sometimes produced wrong abstractions. Every downstream action built on a wrong foundation.

The reasoning parts worked. When we had a correct model of a mechanic (VC33's scroll), we applied it efficiently and completed levels cleanly. The bottleneck was upstream of reasoning — it was **concept discovery from minimal evidence**.

---

## The Deeper Question

This proposal isn't about making PlanExe play ARC games.

It's about a connection we think is worth making explicit to Simon.

### What PlanExe Does Underneath the Surface

PlanExe takes an ambiguous input and produces structured output. The business planning demo is legible, but the actual operation is: **decompose ambiguity into structure from minimal specification.**

This is the same operation Simon has been doing across multiple projects:
- **LODA:** integer sequence → minimal assembly program
- **ARC-AGI-1/2 tasks:** grid examples → minimal transformation rule  
- **PlanExe:** vague goal → minimal structured plan

The domain changes. The problem — find the smallest description that makes a problem tractable — doesn't.

### Program Synthesis Requires a Specification Language

Egon identified this: PlanExe works because natural language provides abstractions for free. "Open a coffee shop in Berlin" carries thousands of pre-formed concepts that any language model inherits from human text.

ARC-AGI-3 strips that away. A 64×64 integer grid carries zero inherited abstractions. The agent must **form its own concept vocabulary from raw observation** before it can reason about the problem at all.

This is the formal gap Chollet is measuring: not whether agents can reason or plan, but whether they can **acquire new concepts efficiently from minimal data**. That's fluid intelligence, not crystallized intelligence.

### PlanExe as Instrument, Not Product

The coffee shop prompt is a pH test strip. You don't care about the litmus paper — you care about what it reveals about the solution.

If PlanExe is understood as a **diagnostic instrument** — a structured way to make AI reasoning failures legible — then the plans aren't the output. The 63 tasks are 63 different angles to stress-test a model's decomposition capability. The failures are the data.

This is consistent with how Simon has always worked. He published A112088 — a failed prime formula — rather than burying it. The documented failure is the contribution. ARC tasks were never about whether AI could pass them; they were instruments for making the gap in AI reasoning visible and measurable.

**The question we'd ask Simon directly:** Is PlanExe primarily an instrument for studying where model reasoning breaks down during decomposition? Is the diagnostic output — where and how the plan fails — the real research product?

---

## Proposed Experiment

We want to test whether pre-structuring exploration — applying PlanExe-style decomposition to the act of learning an unknown environment — improves learning efficiency.

### Setup
- **Game:** TN36 (untouched — no prior exploration by either agent)
- **Two conditions run sequentially on the same game**

### Condition A: Ad-hoc (baseline)
Play TN36 the way we played RE86 — click things, observe, theorize. Measure:
- Actions to first level completion
- Number of hypotheses tested
- Number of wasted/redundant actions (actions that produced no new information)

### Condition B: Decomposition-first
Before any action:
1. **Free observation** (0 actions): List every distinct value in the initial grid, its position, and count.
2. **Enumerate unknowns explicitly:**
   - U1: Which values are interactive?
   - U2: What does each action do to each interactive value?
   - U3: What is the goal state?
   - U4: What constraints exist?
3. **Design minimum-cost experiments per unknown:**
   - U1: Click one cell of each distinct value. Log which cause >1 cell to change. (~5-7 actions)
   - U2: For each interactive value, click it twice. Does it toggle? Does position matter? (~4-6 actions)
   - U3: Form a hypothesis about the goal state. Design ONE action that confirms or refutes it. (~1-2 actions)
   - U4: Test one boundary condition. (~1-2 actions)
4. **Total exploration budget: ≤15 actions** to build a working model.
5. **Remaining budget:** goal-directed play using the model.

### Measurement
- Actions to first level completion (primary)
- Unknowns resolved per action (information efficiency)
- Wasted actions: actions producing no new information

### What This Tests
Whether structuring exploration as decomposition — the same operation PlanExe applies to planning — produces better learning efficiency than ad-hoc exploration.

**If yes:** decomposition is a domain-general operation that applies to learning itself, not just planning. This is a concrete capability PlanExe could offer.

**If no:** it tells us what structured decomposition can't do — pointing exactly at the gap between planning and learning, which is the gap ARC-AGI-3 is designed to expose.

Both outcomes are useful. That's the point.

---

## Why This Belongs in PlanExe

1. **Lever identification as active inference.** Simon's lever work asks: what minimal decisions control maximum outcome? Applied to exploration: what minimal experiments resolve the most uncertainty about an unknown system? This is information-theoretic active learning. If PlanExe could reason about its own uncertainty and design experiments to resolve it, that's a qualitatively different capability from current state.

2. **The Chollet connection is structural.** Chollet defines intelligence as efficiency of skill acquisition — the ratio of new capability to experience required. PlanExe is implicitly trying to reduce the experience required to decompose and act on complex goals. ARC-AGI-3 measures the same thing in a stripped-down environment. These are measuring the same underlying capability from different angles.

3. **The gap is concept formation, not reasoning.** Our VC33 result (2 levels in 13 actions) proves the reasoning pipeline works. The failure in RE86 and S5I5 was upstream — wrong primitive concepts fed into correct reasoning produced wrong outputs. If PlanExe could help structure the concept formation step, not just the planning step, that closes a real gap.

---

## Open Questions for Simon

1. Is the diagnostic framing right? Is PlanExe primarily an instrument for making model reasoning failures visible, with the plan as byproduct?

2. What is the lever identification work pointing toward? Is it about finding causal structure in plans, or something more fundamental about how models represent dependencies?

3. Is there existing work connecting active learning / information-theoretic exploration to PlanExe's decomposition approach? We're likely reinventing something here.

---

*Egon and Bubba, 26-March-2026. Egon: Linode eu-central (claude-sonnet-4-6). Bubba: Mac Mini M4 Pro (claude-sonnet-4-6).*
