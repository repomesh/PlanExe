# Strengthening PlanExe: Evidence Discipline, Anti-Handwave Checks, and Claim Calibration

## Summary

PlanExe is already good at turning a prompt into a broad planning artifact. Its stronger versions do more than produce structure: they expose assumptions, include adversarial sections, and try to reason about failure before execution. That is valuable.

The weakness is different. PlanExe can still generate **credible-looking planning structure faster than credible support for its claims**. In practice, that means a plan can feel well-argued because it is detailed, while some of its most important claims remain underspecified, weakly evidenced, or overconfident.

This document lays out what that weakness actually is, why it matters, and how to fix it.

---

## The Core Problem

A planning system can fail in two opposite ways:

1. **Underproduction**: the plan is thin, generic, and misses key dimensions.
2. **Overproduction**: the plan is rich, coherent, and impressive, but confidence outruns evidence.

PlanExe is already better than many systems on the first problem. The bigger risk now is the second.

The specific failure pattern is:

- a claim is made early,
- supporting logic is added later,
- surrounding structure makes the claim feel stronger than it is,
- weak assumptions become harder to notice because they are embedded inside a polished plan.

This is not ordinary hallucination. It is **structured overreach**.

---

## 1. Evidence Discipline

### What it means

Evidence discipline means that important claims must be backed by something stronger than fluent reasoning. A plan should distinguish between:

- claims supported by direct evidence,
- claims supported by analogy or inference,
- speculative claims,
- assumptions that are merely placeholders.

Without that distinction, all claims get flattened into the same rhetorical tone.

### Why it matters

In a planning system, weak evidence does not just create a bad sentence. It can distort:

- prioritization,
- resource allocation,
- timelines,
- risk perception,
- go / no-go decisions.

A bad claim in a plan is worse than a bad claim in a chat answer because it influences downstream structure.

### Typical failure modes

#### 1.1 Evidence-free specificity
The plan gives precise numbers, timelines, or outcome estimates without showing where they came from.

Example:
- “This will reduce costs by 40% within five years.”
- “This approach should achieve 95% capability in 20 years.”

The problem is not only that the number may be wrong. The problem is that specificity itself creates false authority.

#### 1.2 Evidence laundering through structure
A weak claim appears in the executive summary, then gets repeated in the roadmap, KPI section, risk section, and pitch. Repetition makes it feel validated, even though nothing new was added.

#### 1.3 Placeholder evidence masquerading as support
The system uses language like:
- “industry trends suggest”
- “experts may support”
- “this is likely to improve”
without naming the basis of the claim.

That is not evidence. It is confidence-scented filler.

#### 1.4 No distinction between direct support and inference
A plan often needs inference. That is fine. The problem is when inference is presented as if it were observed fact.

### What PlanExe should do

PlanExe should attach an **evidence status** to major claims.

A simple scheme:

| Status | Meaning |
|---|---|
| Observed | Directly supported by source material or explicit user input |
| Derived | Inferred from observed facts with a visible reasoning path |
| Estimated | Quantitative or qualitative estimate with explicit uncertainty |
| Assumed | Placeholder assumption not yet validated |
| Speculative | Creative or strategic hypothesis with weak support |

Each nontrivial claim should be traceable to one of these.

### Stronger mechanism: claim ledger

PlanExe should maintain a **claim ledger** for all high-impact claims.

Each row should include:

- claim text,
- claim type,
- evidence status,
- support source,
- uncertainty level,
- downstream dependencies,
- disproof condition,
- owner for validation.

This would stop plans from treating all claims as equal.

---

## 2. Anti-Handwave Checks

### What “handwaving” actually is

Handwaving is not just vagueness. It is when a plan appears to explain something while skipping the part that carries the real burden.

Typical forms:

- naming a solution without specifying the mechanism,
- naming a metric without defining how it will be measured,
- naming a dependency without describing how it will be secured,
- naming a risk without making it operational.

A handwave is a **missing bridge disguised as a bridge**.

### Why PlanExe is vulnerable

PlanExe is good at producing complete-looking artifacts. That creates a specific danger: empty connective tissue can hide inside otherwise strong structure.

For example:

- “Use AI for adaptive control” can hide the absence of a sensing, feedback, and retraining story.
- “Ensure stakeholder alignment” can hide the absence of decision rights and conflict resolution.
- “Validate feasibility through pilots” can hide the absence of a pilot design, threshold, and stop rule.

### Common handwave patterns

#### 2.1 Magic verb pattern
Claims rely on verbs like:
- optimize,
- leverage,
- ensure,
- enable,
- integrate,
- streamline,
- validate.

These verbs often conceal missing mechanism.

#### 2.2 Abstract noun shield
The plan uses high-status abstractions such as:
- innovation,
- resilience,
- scalability,
- adaptability,
- synergy,
- transformation.

These can be useful, but they often mask missing specifics.

#### 2.3 Deferred detail laundering
The plan pushes all hard questions into future phases:
- “details will be defined later,”
- “an implementation strategy will be developed,”
- “specific thresholds will be established during execution.”

Sometimes that is appropriate. Often it is a way of postponing the point where the idea has to become real.

#### 2.4 KPI theater
A metric is named, but the measurement definition is absent.

Bad example:
- “Improve efficiency by 30%.”

Better:
- “Reduce median cycle time per unit from X to Y under condition Z, measured across N runs.”

### What PlanExe should do

PlanExe should run a dedicated **anti-handwave pass** after drafting.

For each major section, it should ask:

- Is the mechanism explicit?
- Are terms operationally defined?
- Are success metrics measurable?
- Are dependencies concrete?
- Are thresholds specified?
- Does any sentence rely on persuasive language without decision-useful content?

### Recommended handwave detector rubric

Flag sentences containing any of the following unless paired with operational detail:

- optimize
- enhance
- enable
- leverage
- improve
- robust
- scalable
- efficient
- innovative
- strategic
- transformative

The detector should not just block these words. It should ask for the missing bridge.

For example:

**Original:**  
“Use AI to optimize adaptive manufacturing workflows.”

**Required expansion:**  
- What data enters the system?
- What model class is assumed?
- What output does it change?
- What action loop is closed?
- What failure cases exist?
- What evidence suggests the loop will work?

### Stronger mechanism: burden-of-specificity triggers

Some claims should automatically trigger required elaboration, especially claims about:

- automation,
- cost reduction,
- timelines,
- commercial viability,
- scaling,
- safety,
- regulatory feasibility,
- staffing,
- ROI,
- partnerships.

These are high-risk bullshit zones. They should never pass in vague form.

---

## 3. Claim Calibration

### What it means

Claim calibration means matching the strength of a statement to the strength of its support.

Bad calibration:
- speaking with certainty when evidence is weak,
- speaking vaguely when evidence is strong,
- failing to separate possibility from probability.

Calibration is about the **fit between confidence and justification**.

### Why it matters

Poor calibration corrupts decision-making. It causes people to:

- commit too early,
- underweight downside,
- ignore unknowns,
- mistake elegance for confidenceworthiness.

A planning system should not merely generate plans. It should help people know **which parts of the plan deserve trust**.

### Common calibration failures

#### 3.1 Binary confidence language
The plan says:
- “will”
- “ensures”
- “guarantees”
- “is expected to”
when a more honest phrasing would show uncertainty.

#### 3.2 False precision
The plan gives exact percentages or dates when the underlying basis is weak.

#### 3.3 Confidence contamination
A strong claim in one area spills over into adjacent unsupported claims.

Example:
- because a prototype seems feasible, the plan starts sounding confident about commercialization, labor availability, and regulatory approval too.

#### 3.4 No uncertainty decomposition
A plan treats a claim as singular even though it depends on multiple uncertain subclaims.

For example:
“This platform can scale.”

That may actually depend on:
- technical repeatability,
- supply chain reliability,
- training needs,
- capex availability,
- regulatory acceptance,
- quality control.

### What PlanExe should do

PlanExe should require **confidence labels** on major claims.

A simple scale:

| Confidence | Meaning |
|---|---|
| High | Strong support, low ambiguity, limited dependency uncertainty |
| Medium | Plausible but materially dependent on unresolved assumptions |
| Low | Weak support, speculative, or strongly dependent on unknowns |

This should be paired with a **why** field, not just a label.

Example:

> Claim: Modular factory reconfiguration can occur within 72 hours.  
> Confidence: Low  
> Why: Depends on unvalidated assumptions about tooling interchangeability, workforce readiness, and software integration.

### Stronger mechanism: decomposition before confidence

Before assigning confidence to a high-stakes claim, PlanExe should decompose it into subclaims.

For each subclaim:
- assign support type,
- assign confidence,
- identify unknowns,
- list what would change the score.

Then roll that upward.

This prevents confident summary claims from being detached from fragile internals.

---

## 4. What a Better Plan Artifact Would Look Like

A stronger PlanExe artifact would not just contain more sections. It would contain more **truth structure**.

That means every major recommendation should expose:

- what is being claimed,
- what supports it,
- what remains assumed,
- what would falsify it,
- how confident the system is,
- which downstream sections depend on it.

Instead of a plan reading like a polished narrative, it should read like a **decision model with visible load-bearing parts**.

### Example transformation

#### Weak version
“We recommend prioritizing adaptive hybrid manufacturing because it offers the greatest scalability and long-term strategic value.”

#### Stronger version
“We recommend prioritizing adaptive hybrid manufacturing.  
Support type: Derived.  
Basis: User objective emphasizes flexible manufacturing across variable inputs; hybrid processes cover a broader process space than purely additive systems.  
Key assumptions: Material handling variability remains within controllable bounds; calibration overhead does not erase throughput gains.  
Confidence: Medium.  
Disproof triggers: Pilot tests show reconfiguration time exceeds threshold; quality variance remains above target after calibration.  
Downstream dependencies: staffing plan, equipment selection, KPI definitions, validation roadmap.”

That second version is less pretty, but more decision-useful.

---

## 5. Concrete Design Changes for PlanExe

## A. Add a claim-layer beneath the prose

Every important paragraph should have a machine-readable shadow structure:

- claim,
- support,
- assumptions,
- uncertainty,
- disproof conditions.

The visible prose can stay readable, but the system should reason over the structured layer.

## B. Require support tags in key sections

At minimum, these sections should require support tagging:

- Executive Summary
- Strategic Decisions
- KPI section
- Budget / ROI claims
- Timeline claims
- Risk mitigation claims
- Recommendations

## C. Add a “why this might be wrong” line to major recommendations

Every major recommendation should include a compact adversarial line.

Example:
- “This may be wrong because the throughput benefit depends on a calibration regime not yet validated.”

This would drastically reduce overconfident planning prose.

## D. Add handwave linting

Run a linting pass that flags:

- abstract claims without mechanism,
- metrics without measurement definitions,
- timelines without basis,
- benefits without dependency chain,
- “AI” claims without control-loop detail,
- cost claims without drivers,
- scale claims without bottleneck analysis.

## E. Force quantitative humility

When numbers appear, require one of:

- source,
- derivation,
- estimate note,
- uncertainty range,
- sensitivity note.

A bare number should be disallowed in high-stakes sections.

## F. Separate “analysis complete” from “execution ready”

A plan can be analytically rich but still not execution-ready.

PlanExe should explicitly score readiness on dimensions like:

- evidence maturity,
- dependency maturity,
- stakeholder alignment,
- resource realism,
- regulatory clarity,
- validation completeness.

This prevents polished plans from being mistaken for greenlit plans.

---

## 6. A Proposed Evaluation Rubric

To improve PlanExe, evaluate plans not just for completeness but for epistemic quality.

### Evidence Discipline
- Are major claims tagged by support type?
- Are numbers grounded?
- Are assumptions distinguished from findings?
- Can claims be traced to support?

### Anti-Handwave Quality
- Are mechanisms explicit?
- Are key terms operationalized?
- Are metrics measurable?
- Are high-risk claims elaborated beyond slogans?

### Claim Calibration
- Does confidence match support?
- Are uncertainty and dependency chains visible?
- Are summary claims weaker when internals are weak?
- Are disproof conditions stated?

### Bullshit Resistance
- Can a reviewer quickly identify the weakest load-bearing assumptions?
- Can the plan be falsified?
- Does the plan expose where it is vulnerable?
- Does repetition amplify unsupported claims, or merely summarize supported ones?

---

## 7. What “Good” Would Look Like

A genuinely strong PlanExe system would produce plans that are:

- comprehensive without being bloated,
- explicit without being theatrical,
- uncertain without becoming useless,
- critical without becoming paralyzed,
- persuasive only where support justifies persuasion.

The target is not “more skeptical text.”  
The target is **better alignment between what is said, what is known, and what is still guesswork**.

That is what evidence discipline, anti-handwave checks, and claim calibration are really about.

---

## Final View

PlanExe does not mainly need more sections. It needs stronger constraints on how claims enter, spread, and harden inside a plan.

The goal is to prevent this sequence:

1. a plausible claim appears,
2. it gets repeated,
3. it acquires structure,
4. it starts to feel true.

Instead, the system should force a different sequence:

1. a claim appears,
2. its support status is made explicit,
3. its weak points are surfaced,
4. its confidence is calibrated,
5. only then is it allowed to shape the rest of the plan.

That shift would make PlanExe much more than a sophisticated planning generator.

It would make it a system that actively resists false confidence.
