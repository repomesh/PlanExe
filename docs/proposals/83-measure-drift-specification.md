Agent-Facing Specification: Drift Evaluation Between Initial Prompt and Generated Plan

1. Purpose

This specification defines a strict, operational procedure for evaluating drift between an initial prompt and a generated plan.

It is written for AI agents that must perform the evaluation without prior conversational context.

The evaluator’s job is not to judge whether the plan is impressive, polished, or well-written. The evaluator’s job is to determine whether the generated plan remains faithful to the prompt’s intended meaning, constraints, boundaries, priorities, and uncertainty posture.

This spec is designed to be executable as an internal evaluation procedure, a QA rubric, or a regression test for planning systems.

⸻

2. Core Rule

A generated plan passes only if it becomes more usable without becoming less true.

That is the governing principle.

If the output is richer, clearer, more complete, and more structured, but also introduces unsupported claims, weakens constraints, changes the product, changes the customer, or inflates confidence, then it has failed.

⸻

3. Definitions

3.1 Initial prompt

The source instruction, description, or concept from which the plan was generated.

3.2 Generated plan

The long-form output artifact produced from the initial prompt. This may be a strategic plan, roadmap, business plan, proposal, implementation plan, report, or similar document.

3.3 Drift

Any meaningful departure from the source prompt’s commitments, exclusions, logic, scope, or uncertainty.

3.4 Fidelity

The degree to which the generated plan preserves the source prompt’s content and posture.

3.5 Prompt contract

A normalized structured representation of what the initial prompt actually commits to.

The prompt contract is mandatory. No drift evaluation may proceed without it.

⸻

4. Non-Negotiable Evaluation Rules

The evaluator must follow these rules exactly.

Rule 1: Extract a prompt contract before evaluating

Do not compare the raw prompt and plan loosely. First convert the prompt into a structured contract.

Rule 2: Evaluate meaning, not wording

Rephrasing is not drift unless meaning changes.

Rule 3: Treat explicit exclusions as high-priority

Anything the prompt says not to do, not to claim, not to position, or not to include must be treated as critical.

Rule 4: Unsupported specificity is suspicious by default

Specific tools, numbers, budgets, timelines, roles, locations, legal claims, metrics, and market claims are presumed unsafe unless supported or clearly flagged as assumptions.

Rule 5: Optional features must remain optional

If the prompt says something is optional, deferred, layered, or future-phase, the generated plan must not silently promote it to a core feature.

Rule 6: Preserve uncertainty

If the prompt is cautious, provisional, or incomplete, the generated plan must preserve that. It must not replace uncertainty with smooth confidence.

Rule 7: Negative space matters

A prompt’s non-goals and omitted claims matter. The model must not fill every gap with plausible strategic filler.

Rule 8: One critical contradiction is enough to fail

A high enough weighted score does not rescue a plan that materially changes the customer, business model, regulatory posture, or explicit non-goals.

⸻

5. Required Inputs

The evaluating agent must receive:
	•	the initial prompt
	•	the generated plan
	•	optionally, metadata such as generation settings, section structure, or intermediate notes

The evaluator must not assume any external knowledge beyond what is in these materials.

⸻

6. Required Outputs

The evaluator must produce all of the following:
	1.	Prompt contract
	2.	Output claim map
	3.	Drift incident log
	4.	Dimension scores
	5.	Pass/fail decision
	6.	Revision actions
	7.	Confidence statement about the evaluation

No partial format is acceptable.

⸻

7. Mandatory Evaluation Procedure

Step 1: Build the Prompt Contract

Convert the initial prompt into the following structure.

7.1 Prompt Contract Schema
	•	Core intent
	•	Primary problem
	•	Product/tool/system definition
	•	Primary buyer
	•	Primary user
	•	Other relevant entities
	•	Target context/domain
	•	Core value claim
	•	Business model / GTM
	•	Implementation scope
	•	Core features
	•	Optional features
	•	Deferred features
	•	Explicit non-goals
	•	Explicit exclusions
	•	Hard constraints
	•	Risk / uncertainty posture
	•	Success metrics
	•	Legal / regulatory posture
	•	Key assumptions allowed by the prompt
	•	Claims the prompt explicitly avoids

7.2 Contract Extraction Standard

Each field must be written in concise declarative language.

Bad:
	•	“It seems to maybe be about…”

Good:
	•	“Primary buyer: institutional funders with high-volume, inconsistent application pipelines.”

7.3 Mandatory Classification

Each contract item must be tagged as one of:
	•	explicit
	•	strongly implied
	•	weakly implied

Only explicit and strongly implied items may be used as safe support for output claims.

Weakly implied items may support only cautious derived claims.

⸻

Step 2: Extract the Generated Plan Claim Map

The evaluator must identify all major commitments in the generated plan.

At minimum, extract claims about:
	•	product identity
	•	target customer
	•	target user
	•	domain/context
	•	problem statement
	•	mechanism of value
	•	business model
	•	GTM
	•	implementation phases
	•	team roles
	•	timelines
	•	tools/stack
	•	metrics
	•	legal/regulatory claims
	•	expansion paths
	•	assumptions
	•	causal claims
	•	outcome claims

Each extracted claim must be tagged by importance:
	•	critical
	•	important
	•	secondary

Only critical and important claims affect pass/fail directly. Secondary claims mainly affect quality scores.

⸻

Step 3: Align Output Claims to Prompt Support

For each claim in the generated plan, assign exactly one support label:
	•	source-stated
	•	source-derived
	•	speculative-but-flagged
	•	unsupported
	•	contradictory

8.1 Support Label Rules

source-stated
The claim is directly present in the prompt.

source-derived
The claim is a reasonable inference from multiple prompt elements and does not exceed their strength.

speculative-but-flagged
The claim is added, but clearly marked as assumption, possibility, or item needing validation.

unsupported
The claim is not grounded in the prompt and is presented without clear uncertainty marking.

contradictory
The claim conflicts with the prompt’s content, exclusions, or structure.

8.2 Strictness rule

If there is any doubt whether a claim is source-derived or unsupported, default to unsupported.

⸻

Step 4: Detect Drift Incidents

Each drift incident must be logged individually.

9.1 Drift Incident Schema

For every incident, record:
	•	incident_id
	•	drift_type
	•	severity
	•	plan_section
	•	output_claim
	•	prompt_contract_reference
	•	support_label
	•	explanation
	•	repair_action

9.2 Allowed Drift Types
	•	scope_expansion
	•	constraint_erosion
	•	unsupported_invention
	•	confidence_inflation
	•	business_model_drift
	•	customer_drift
	•	mechanism_drift
	•	priority_drift
	•	regulatory_drift
	•	style_induced_semantic_drift
	•	unsupported_metrics
	•	invented_operational_detail
	•	optional_to_core_promotion
	•	uncertainty_erasure

The evaluator must not invent its own drift categories unless absolutely necessary.

⸻

8. Severity Rules

Every incident must receive one severity score from 0 to 4.

Severity 0 — No drift

Harmless elaboration or faithful restatement.

Severity 1 — Minor drift

Slight inflation or unnecessary elaboration that does not alter the plan’s core meaning.

Examples:
	•	mild jargon creep
	•	superficial strategic language
	•	harmless extra section titles

Severity 2 — Moderate drift

A meaningful but not fatal change in emphasis, specificity, or interpretation.

Examples:
	•	optional feature overemphasized
	•	light unsupported operational detail
	•	caveat softened but not removed

Severity 3 — Major drift

A substantial change to what the plan claims, how it works, who it is for, or how certain it is.

Examples:
	•	workflow tool reframed as intelligence engine
	•	ungrounded specific metrics used as proof
	•	platform expansion dominates narrow wedge
	•	unsupported legal certainty

Severity 4 — Critical drift

A central contradiction or material corruption of the prompt.

Examples:
	•	target customer changed
	•	business model changed
	•	explicit non-goal violated
	•	banned framing reintroduced
	•	unsupported invented detail repeated across important sections
	•	uncertainty replaced by fact in core areas
	•	advisory product inserted where prompt forbids it

⸻

9. Scoring Dimensions

The evaluator must score all 10 dimensions on a 0 to 5 scale.

9.1 Scale definition
	•	5 = excellent fidelity
	•	4 = good fidelity, minor issues only
	•	3 = mixed fidelity, notable drift
	•	2 = weak fidelity
	•	1 = severe drift
	•	0 = failed completely

9.2 Required dimensions

A. Scope Fidelity

Did the output stay within the intended scope?

B. Constraint Fidelity

Did the output preserve exclusions, banned concepts, and hard boundaries?

C. Claim Strength Fidelity

Did the output preserve the strength of claims rather than escalating them?

D. Evidence Grounding Fidelity

Are material claims supported by the prompt?

E. Entity Fidelity

Did the output preserve buyer, user, applicant, stakeholder, and product identity?

F. Causal Fidelity

Did the output preserve why the product matters and how it creates value?

G. Epistemic Fidelity

Did the output preserve uncertainty, assumptions, and unresolved issues?

H. Source-Trace Fidelity

Can major claims in the plan be linked back to source content?

I. Structural Priority Fidelity

Did the output preserve what is core, optional, and deferred?

J. Language Posture Fidelity

Did the language remain appropriately restrained and true to the source posture?

⸻

10. Weights

The evaluator must compute a weighted fidelity score using these weights.
	•	Constraint Fidelity: 20%
	•	Scope Fidelity: 15%
	•	Evidence Grounding Fidelity: 15%
	•	Entity Fidelity: 10%
	•	Causal Fidelity: 10%
	•	Epistemic Fidelity: 10%
	•	Structural Priority Fidelity: 8%
	•	Claim Strength Fidelity: 5%
	•	Source-Trace Fidelity: 4%
	•	Language Posture Fidelity: 3%

Total: 100%

⸻

11. Automatic Failure Conditions

Regardless of weighted score, the plan must be marked FAIL if any of the following are true.

11.1 Explicit exclusion violation

A banned concept, forbidden framing, or explicit non-goal is materially reintroduced.

11.2 Customer identity drift

The target customer or buyer materially changes.

11.3 Business model drift

The product’s commercial model, product category, or GTM is materially changed without source basis.

11.4 Regulatory posture drift

The generated plan materially misstates or overstates the legal or regulatory posture.

11.5 Repeated unsupported quantitative claims

The plan introduces unsupported numerical claims in multiple important sections.

Threshold:
	•	3 or more important unsupported numeric claims = automatic fail

11.6 Optional-to-core promotion in central product definition

A feature marked optional, deferred, or layered becomes core in the main product narrative.

11.7 Uncertainty erasure in core assumptions

The source identifies major uncertainty, but the generated plan treats it as settled in core reasoning.

11.8 Unsupported invention in critical areas

Unsupported tools, teams, locations, legal assumptions, or implementation requirements appear in critical sections and materially shape the plan.

11.9 Loss of traceability

The generated plan makes critical claims that cannot be linked to source content or clearly flagged assumptions.

⸻

12. Pass / Borderline / Fail Thresholds

If no automatic-fail condition is triggered, use these thresholds.

PASS

All of the following:
	•	weighted fidelity score >= 4.2 / 5
	•	no dimension below 3
	•	no severity 4 incidents
	•	at most 2 severity 3 incidents
	•	unsupported important claim count <= 3
	•	confidence inflation count <= 2

BORDERLINE

Any of the following:
	•	weighted fidelity score between 3.4 and 4.19
	•	one dimension scored 2
	•	up to 4 severity 3 incidents
	•	unsupported important claim count between 4 and 7
	•	confidence inflation count between 3 and 5

A borderline plan requires revision and re-evaluation. It is not approved for final use.

FAIL

Any of the following:
	•	automatic-fail condition triggered
	•	weighted fidelity score < 3.4
	•	any dimension scored 0 or 1
	•	more than 4 severity 3 incidents
	•	any severity 4 incident
	•	unsupported important claim count > 7
	•	confidence inflation count > 5

⸻

13. Counting Rules

The evaluator must track these counts.

13.1 Unsupported Important Claim Count

Count all unsupported claims tagged critical or important.

13.2 Unsupported Numeric Claim Count

Count all unsupported numerical values, percentages, estimates, timing claims, budget claims, ROI claims, market share claims, staffing counts, or quantified performance claims.

13.3 Constraint Violation Count

Count all places where the plan weakens, ignores, or bypasses an explicit prompt constraint.

13.4 Confidence Inflation Count

Count each time:
	•	tentative becomes assertive
	•	assumption becomes fact
	•	exploratory becomes settled
	•	“may/could/conditional” becomes “will/is”

Only count material occurrences, not every wording instance.

13.5 Optional-to-Core Promotion Count

Count each time an optional, deferred, or layered feature becomes part of the central product definition, core GTM, or main value proposition.

⸻

14. Revision Rules

If the output is BORDERLINE or FAIL, the evaluator must provide repair actions.

Each repair action must be concrete and localized.

Bad:
	•	“Make it more faithful.”

Good:
	•	“Replace unsupported claim that London office proximity is required for execution with a conditional note that London location may help relationship-building but is not operationally necessary.”

14.1 Allowed repair action types
	•	delete unsupported claim
	•	downgrade claim strength
	•	restore uncertainty
	•	relabel assumption as speculative
	•	move feature from core to optional/deferred
	•	reinsert excluded framing
	•	restore original customer definition
	•	restore original business model
	•	remove invented numbers
	•	add source-trace note
	•	split source-provided vs system-derived content
	•	compress future expansion to deferred roadmap

⸻

15. Required Final Output Format

The evaluator must return the result in a structured format that contains all required sections.

15.1 Mandatory JSON-like schema

{
  "evaluation_metadata": {
    "spec_version": "1.0",
    "evaluation_mode": "strict",
    "confidence": "high | medium | low"
  },
  "prompt_contract": {
    "core_intent": "",
    "primary_problem": "",
    "product_definition": "",
    "primary_buyer": "",
    "primary_user": "",
    "target_context": "",
    "core_value_claim": "",
    "business_model_gtm": "",
    "implementation_scope": "",
    "core_features": [],
    "optional_features": [],
    "deferred_features": [],
    "explicit_non_goals": [],
    "explicit_exclusions": [],
    "hard_constraints": [],
    "risk_uncertainty_posture": [],
    "success_metrics": [],
    "legal_regulatory_posture": [],
    "allowed_assumptions": [],
    "claims_explicitly_avoided": []
  },
  "claim_map": [
    {
      "claim_id": "C1",
      "claim_text": "",
      "importance": "critical | important | secondary",
      "support_label": "source-stated | source-derived | speculative-but-flagged | unsupported | contradictory",
      "prompt_reference": ""
    }
  ],
  "dimension_scores": {
    "scope_fidelity": 0,
    "constraint_fidelity": 0,
    "claim_strength_fidelity": 0,
    "evidence_grounding_fidelity": 0,
    "entity_fidelity": 0,
    "causal_fidelity": 0,
    "epistemic_fidelity": 0,
    "source_trace_fidelity": 0,
    "structural_priority_fidelity": 0,
    "language_posture_fidelity": 0
  },
  "weighted_fidelity_score": 0.0,
  "counts": {
    "unsupported_important_claim_count": 0,
    "unsupported_numeric_claim_count": 0,
    "constraint_violation_count": 0,
    "confidence_inflation_count": 0,
    "optional_to_core_promotion_count": 0,
    "severity_3_count": 0,
    "severity_4_count": 0
  },
  "drift_incidents": [
    {
      "incident_id": "D1",
      "drift_type": "",
      "severity": 0,
      "plan_section": "",
      "output_claim": "",
      "prompt_contract_reference": "",
      "support_label": "",
      "explanation": "",
      "repair_action": ""
    }
  ],
  "automatic_fail_conditions_triggered": [],
  "decision": {
    "status": "PASS | BORDERLINE | FAIL",
    "usable_as_is": false,
    "requires_revision": true,
    "rationale": ""
  },
  "revision_actions": [
    ""
  ],
  "summary": {
    "preserved_well": [],
    "major_failures": [],
    "overall_verdict": ""
  }
}


⸻

16. Agent Operating Instructions

The evaluator must follow these behavioral rules.

16.1 Be conservative

Do not give credit for plausibility. Give credit only for support.

16.2 Prefer explicit incompleteness over invented coherence

If the source did not specify something important, the plan should leave it open or label it as an assumption.

16.3 Do not reward strategic polish

A plan does not score higher because it sounds sophisticated.

16.4 Treat invented precision as suspicious

Precise numbers without prompt grounding are almost always drift.

16.5 Distinguish utility from fidelity

A plan may be useful and still drift badly. Fidelity comes first.

16.6 Escalate semantic changes caused by language inflation

If wording inflation changes how strong or broad a claim sounds, treat it as semantic drift, not style only.

⸻

17. Heuristics for Common Failure Modes

The evaluator must explicitly look for these.

17.1 Consultant inflation

Watch for:
	•	ecosystem
	•	category leader
	•	transformation
	•	revolutionize
	•	market capture
	•	strategic moat
	•	substantial market share

These are red flags unless the prompt itself uses them.

17.2 Fabricated concreteness

Watch for invented:
	•	software tools
	•	software stack
	•	exact team composition
	•	exact office setup
	•	exact budgets
	•	exact growth metrics
	•	exact legal interpretations
	•	exact operating assumptions

17.3 Confidence laundering

Watch for:
	•	may -> will
	•	can help -> drives
	•	supports -> ensures
	•	exploratory -> validated
	•	possible -> definitive

17.4 Future-roadmap takeover

Watch for deferred ambitions dominating present scope.

17.5 Optional-to-core promotion

Watch for optional filters, scoring, analytics, or expansion becoming central product identity.

17.6 Workflow-to-intelligence drift

Watch for a workflow tool being reframed as prediction, recommendation, intelligence, or optimization engine.

17.7 Traceability loss

Watch for generated content that no longer clearly maps to user-provided input.

⸻

18. Minimal Acceptability Standard

A generated plan is acceptable only if it satisfies all of the following:
	•	preserves the prompt’s buyer, product type, and value logic
	•	preserves hard exclusions and non-goals
	•	does not introduce critical unsupported invention
	•	preserves uncertainty where it matters
	•	does not convert optional layers into core identity
	•	improves clarity and usability without overstating what is known
	•	remains defensible when compared line by line against the prompt contract

If it fails any of these, it is not acceptable.

⸻

19. Short Decision Template for Agents

When an agent needs to give a concise decision, use this exact structure:

Fidelity verdict

PASS / BORDERLINE / FAIL

Why

One paragraph summarizing whether the plan preserved:
	•	core intent
	•	scope
	•	constraints
	•	uncertainty
	•	product identity

Biggest problems

List the top 3 drift issues only.

Required fixes

List the minimum set of changes needed to reach PASS.

⸻

20. Final Principle

The evaluator must always ask:

Did the generated plan preserve the source prompt’s commitments, limits, and uncertainty while making the result more usable?

If the answer is no, then the plan failed, even if it sounds smarter, richer, or more complete.

That is the whole point of this spec.