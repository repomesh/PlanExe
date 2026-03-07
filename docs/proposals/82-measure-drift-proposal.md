Proposal: Measuring Drift Between an Initial Prompt and a Generated Plan

1. Purpose

This proposal defines a rigorous framework for measuring drift between an initial prompt and a generated plan.

The goal is not to score writing quality in the abstract. The goal is to determine whether the generated plan remains faithful to the source intent, scope, constraints, and epistemic posture of the initial prompt.

This proposal is written so that an AI agent can apply it without any prior knowledge of the conversation that produced it.

It is designed for systems that transform an initial prompt into a long-form structured artifact such as a strategic plan, project plan, proposal, roadmap, report, or multi-section analysis.

⸻

2. Definition of Drift

2.1 Core definition

Drift is the degree to which a generated plan departs from the source prompt in meaningfully important ways.

Drift is not mere rewording.
Drift occurs when the generated plan changes what the prompt was trying to say, protect, avoid, limit, or leave uncertain.

2.2 What counts as drift

A generated plan drifts when it does one or more of the following:
	•	expands scope beyond the source prompt
	•	weakens or ignores explicit constraints
	•	introduces unsupported assumptions as if they were true
	•	inflates confidence beyond what the prompt justified
	•	changes the target user, buyer, or customer
	•	changes the product type or business model
	•	adds invented details that look plausible but were not grounded
	•	turns cautious claims into strong claims
	•	reintroduces ideas the prompt explicitly excluded
	•	changes priorities or success criteria
	•	launders ambiguity into false coherence

2.3 What does not count as drift

These should not be treated as drift by default:
	•	rephrasing
	•	reorganizing content
	•	summarizing with preserved meaning
	•	elaborating on source-backed ideas while clearly marking assumptions
	•	adding implementation detail that is directly implied and remains consistent
	•	making the structure more readable without changing claims

⸻

3. Why Drift Measurement Matters

Prompt-to-plan systems often fail in a specific way: they generate artifacts that are more polished, more complete-sounding, and more “strategic” than the source material, but less faithful.

This creates a dangerous illusion of quality. The output may look stronger while actually being less true.

A drift measurement framework is needed to detect failures such as:
	•	scope inflation disguised as helpful elaboration
	•	fictional detail disguised as completeness
	•	premature certainty disguised as rigor
	•	business model mutation disguised as strategy refinement
	•	constraint erosion disguised as flexibility
	•	institutional jargon creep disguised as professionalism

A good planner should not merely produce rich output. It should preserve the source prompt’s structure of commitments and non-commitments.

⸻

4. Design Principles

Any drift evaluation framework should follow these principles.

4.1 Fidelity over polish

A faithful awkward plan is better than a polished unfaithful one.

4.2 Constraint preservation is first-class

Explicit exclusions, caveats, warnings, banned concepts, and scope limits are not minor details. They are often the most important parts of the prompt.

4.3 Unsupported specificity is a major error

Invented tools, budgets, team roles, metrics, legal assumptions, office locations, and market claims should be treated as risk, not as value.

4.4 Epistemic posture matters

If the source prompt is cautious, conditional, or uncertain, the generated plan should preserve that posture. Replacing uncertainty with smooth confident language is drift.

4.5 Negative space matters

What the prompt deliberately does not claim is often as important as what it does claim.

4.6 Evaluation must distinguish severity

Not all drift is equally harmful. Small stylistic deviation is not the same as changing the customer, business model, or regulatory posture.

⸻

5. What Should Be Measured

Drift should be measured across multiple dimensions, not as a single vague judgment.

5.1 Scope fidelity

Does the generated plan stay within the intended scope?

Questions:
	•	Did the output add adjacent markets, sectors, or customer types not present in the source?
	•	Did the output expand from a narrow tool into a broad platform, ecosystem, marketplace, or transformation story?
	•	Did the output introduce future ambitions as if they were part of the core plan?

Failure examples:
	•	a workflow tool becomes a marketplace
	•	a pilot becomes a broad industry rollout
	•	a single-vertical plan becomes multi-sector strategy

5.2 Constraint fidelity

Does the generated plan preserve hard constraints and exclusions?

Questions:
	•	Were banned concepts reintroduced indirectly?
	•	Were explicit limitations softened or omitted?
	•	Were “do not claim X” instructions ignored?
	•	Were boundaries between optional and core features preserved?

Failure examples:
	•	“not a venture product” becomes venture-adjacent language
	•	“do not market as AI” becomes “AI-powered intelligence platform”
	•	“optional scoring” becomes core algorithmic ranking

5.3 Claim strength fidelity

Did the plan escalate the strength of claims?

Questions:
	•	Did tentative claims become assertive?
	•	Did workflow improvement become outcome prediction?
	•	Did operational hypotheses become commercial certainty?
	•	Did local advantages become decisive strategic moats?

Failure examples:
	•	“may reduce review time” becomes “will revolutionize decisions”
	•	“structured comparison helps triage” becomes “identifies best projects”
	•	“pilot may validate demand” becomes “positions company as category leader”

5.4 Evidence grounding fidelity

Are output claims grounded in the prompt?

Questions:
	•	Can each major claim be traced back to source content?
	•	Are derived claims clearly marked as derived?
	•	Are speculative additions labeled as speculative?
	•	Were numbers invented without support?

Failure examples:
	•	added ROI figures
	•	fabricated efficiency percentages
	•	invented market size or conversion claims
	•	inserted tools, staff roles, or locations not in source

5.5 Entity fidelity

Does the plan preserve the identity of core entities?

This includes:
	•	customer
	•	user
	•	buyer
	•	applicant
	•	regulator
	•	product
	•	business model
	•	channel
	•	pilot partner
	•	success metric owner

Failure examples:
	•	analysts become investors
	•	applicants become founders
	•	institutional sales becomes self-serve signup
	•	tool becomes advisory service

5.6 Causal fidelity

Does the generated plan preserve the source logic of why the product matters?

Questions:
	•	Did the main problem statement change?
	•	Did the proposed mechanism of value shift?
	•	Did the output subtly replace workflow value with intelligence value?
	•	Did it switch from operational efficiency to predictive superiority?

Failure examples:
	•	“saves normalization time” becomes “improves capital allocation quality”
	•	“supports comparison” becomes “predicts project success”

5.7 Epistemic fidelity

Does the output preserve uncertainty, caution, and limits?

Questions:
	•	Are assumptions still framed as assumptions?
	•	Are unknowns still visible?
	•	Are risk areas still treated as unresolved?
	•	Were caveats collapsed into false coherence?

Failure examples:
	•	uncertain regulatory positioning becomes settled
	•	slow procurement risk disappears
	•	variable intake quality becomes smooth process
	•	hard-to-measure outcomes become precise targets

5.8 Source-trace fidelity

Can important parts of the plan be linked back to the prompt?

Questions:
	•	Can an evaluator identify which prompt statements justify which plan sections?
	•	Does the plan distinguish source-stated vs derived vs speculative content?
	•	Are critical sections unsupported by the input?

This dimension is especially important for agentic planning systems.

5.9 Structural priority fidelity

Does the generated plan preserve what the prompt treated as primary versus secondary?

Questions:
	•	Did the output overemphasize optional layers?
	•	Did it bury the core value proposition under secondary features?
	•	Did it promote future possibilities into central strategy?

Failure examples:
	•	optional scoring dominates normalization
	•	long-term expansion dominates immediate beachhead
	•	market narrative dominates workflow problem

5.10 Language posture fidelity

Does the style of language distort meaning?

Questions:
	•	Did plain operational language become inflated strategic language?
	•	Did cautious descriptions become grandiose?
	•	Did jargon obscure the original discipline?

Failure examples:
	•	“tool” becomes “ecosystem”
	•	“workflow support” becomes “transformational platform”
	•	“structured comparison” becomes “intelligent decision engine”

⸻

6. A Practical Drift Taxonomy

For reliable evaluation, drift should be categorized.

6.1 Type A: Scope expansion drift

The output widens the plan beyond the intended product, market, or phase.

6.2 Type B: Constraint erosion drift

The output ignores, weakens, or bypasses explicit constraints.

6.3 Type C: Unsupported invention drift

The output introduces detail without source support.

6.4 Type D: Confidence inflation drift

The output upgrades tentative or conditional language into confident claims.

6.5 Type E: Business model drift

The output changes how the product makes money, reaches customers, or creates value.

6.6 Type F: Customer drift

The output changes who the product is for or who uses it.

6.7 Type G: Mechanism drift

The output changes how the product supposedly works or why it matters.

6.8 Type H: Priority drift

The output misorders what is core versus optional.

6.9 Type I: Governance/regulatory drift

The output changes compliance posture, legal assumptions, or decision responsibility.

6.10 Type J: Style-induced semantic drift

The wording becomes more strategic, polished, or “professional,” but at the cost of changing the actual content.

⸻

7. Severity Model

Every drift issue should be assigned a severity level.

7.1 Severity 0 — No drift

Faithful restatement or harmless elaboration.

7.2 Severity 1 — Minor drift

Slight wording inflation or weakly supported elaboration that does not alter the core plan.

Examples:
	•	mild jargon creep
	•	extra but harmless formatting detail

7.3 Severity 2 — Moderate drift

A meaningful change in emphasis, detail, or interpretation, but core identity remains intact.

Examples:
	•	optional feature treated as more important than intended
	•	localized unsupported tooling detail
	•	softening of caveats

7.4 Severity 3 — Major drift

A significant shift in scope, claims, or product framing.

Examples:
	•	workflow tool becomes decision engine
	•	institutional pilot becomes marketplace narrative
	•	unsupported metrics presented as if grounded

7.5 Severity 4 — Critical drift

The generated plan no longer faithfully represents the source prompt in one or more central ways.

Examples:
	•	customer changed
	•	business model changed
	•	explicit exclusions ignored
	•	speculative fiction treated as fact
	•	core cautious thesis replaced with stronger but unsupported thesis

⸻

8. Evaluation Procedure

This section defines a workflow an AI agent can follow.

Step 1: Extract the Source Prompt Contract

The evaluator should first convert the source prompt into a structured “contract.”

The contract should include:

8.1 Core intent

What is the plan fundamentally about?

8.2 Primary problem

What exact problem is being solved?

8.3 Proposed solution

What is the actual product or system?

8.4 Non-goals

What is explicitly not being claimed or targeted?

8.5 Constraints

Hard limits, banned terms, prohibited framings, scope boundaries.

8.6 Core entities

Who are the users, buyers, applicants, reviewers, regulators, etc.?

8.7 Causal logic

Why should the product help?

8.8 Optional vs core features

What is required, optional, phased, deferred, or excluded?

8.9 Risk and uncertainty posture

What is still uncertain or conditional?

8.10 Success metrics

What outcomes actually matter?

This “prompt contract” is the baseline against which the generated plan should be judged.

Step 2: Extract the Generated Plan Claims

The evaluator should parse the generated plan into its actual commitments.

At minimum, extract:
	•	product definition
	•	customer definition
	•	business model
	•	mechanism of value
	•	implementation assumptions
	•	roles and teams
	•	metrics
	•	legal/regulatory posture
	•	market claims
	•	future roadmap
	•	operational dependencies

Step 3: Align Source and Output

For each major claim in the output, assign one of these labels:
	•	Source-stated: explicitly present in the prompt
	•	Source-derived: reasonable inference from the prompt
	•	Speculative but flagged: added by the plan and clearly identified as assumption
	•	Unsupported: added without prompt support or explicit uncertainty marking
	•	Contradictory: conflicts with the prompt

Step 4: Identify Drift Incidents

Each drift incident should include:
	•	drift type
	•	affected passage or section
	•	source prompt reference
	•	explanation of mismatch
	•	severity score

Step 5: Score by Dimension

Assign scores for each drift dimension.

Recommended scale: 0 to 5, where:
	•	5 = excellent fidelity
	•	4 = good fidelity with minor drift
	•	3 = mixed fidelity with notable issues
	•	2 = weak fidelity
	•	1 = severe drift
	•	0 = failed completely

Dimensions:
	•	scope fidelity
	•	constraint fidelity
	•	claim strength fidelity
	•	evidence grounding fidelity
	•	entity fidelity
	•	causal fidelity
	•	epistemic fidelity
	•	source-trace fidelity
	•	structural priority fidelity
	•	language posture fidelity

Step 6: Produce Composite Scores

Suggested outputs:
	•	Overall Fidelity Score
	•	Overall Drift Risk Score
	•	Critical Drift Count
	•	Unsupported Claim Count
	•	Constraint Violation Count
	•	Confidence Inflation Count

Step 7: Produce a Human-Readable Verdict

The evaluator should summarize:
	•	what the plan preserved well
	•	where drift occurred
	•	whether the plan is usable as-is
	•	whether the output should be revised or rejected

⸻

9. Recommended Scoring Model

A weighted model is better than a flat average.

Suggested weights:
	•	Constraint fidelity: 20%
	•	Scope fidelity: 15%
	•	Evidence grounding fidelity: 15%
	•	Causal fidelity: 10%
	•	Entity fidelity: 10%
	•	Epistemic fidelity: 10%
	•	Structural priority fidelity: 8%
	•	Claim strength fidelity: 5%
	•	Source-trace fidelity: 4%
	•	Language posture fidelity: 3%

Reasoning:
	•	constraint violations and unsupported invention are more dangerous than stylistic inflation
	•	changing the product/customer/mechanism is worse than wording drift
	•	preserving uncertainty matters a lot in planning systems

9.1 Disqualifying conditions

Regardless of weighted score, the output should be flagged as unacceptable if any of the following occur:
	•	explicit banned concepts are reintroduced
	•	the target customer changes materially
	•	the business model changes materially
	•	unsupported numerical claims are presented as facts in multiple important sections
	•	explicit non-goals are violated
	•	regulatory posture is materially misrepresented
	•	the generated plan cannot distinguish source content from invented content

⸻

10. Suggested Output Schema for AI Agents

An AI evaluator should produce results in a structured format.

{
  "summary": {
    "overall_fidelity_score": 3.4,
    "overall_drift_risk": "medium",
    "usable_as_is": false,
    "requires_revision": true
  },
  "prompt_contract": {
    "core_intent": "...",
    "primary_problem": "...",
    "proposed_solution": "...",
    "non_goals": ["..."],
    "constraints": ["..."],
    "core_entities": {
      "buyer": "...",
      "user": "...",
      "applicant": "..."
    },
    "optional_features": ["..."],
    "uncertainties": ["..."]
  },
  "dimension_scores": {
    "scope_fidelity": 2,
    "constraint_fidelity": 4,
    "claim_strength_fidelity": 2,
    "evidence_grounding_fidelity": 1,
    "entity_fidelity": 4,
    "causal_fidelity": 3,
    "epistemic_fidelity": 2,
    "source_trace_fidelity": 1,
    "structural_priority_fidelity": 3,
    "language_posture_fidelity": 2
  },
  "drift_incidents": [
    {
      "type": "unsupported_invention",
      "severity": 4,
      "section": "budget assumptions",
      "source_reference": "no tooling stack specified",
      "output_claim": "uses Jira and Salesforce",
      "explanation": "specific tools were invented without source support"
    }
  ],
  "counts": {
    "critical_drift_count": 2,
    "unsupported_claim_count": 14,
    "constraint_violation_count": 1,
    "confidence_inflation_count": 6
  },
  "verdict": {
    "preserved_well": ["..."],
    "major_failures": ["..."],
    "recommended_actions": ["..."]
  }
}


⸻

11. Prompt Contract Extraction Template

Before evaluating drift, an agent should rewrite the source prompt into this compact canonical form.

Source Prompt Contract
	•	Core intent:
	•	Primary problem:
	•	Product/tool definition:
	•	Primary buyer:
	•	Primary user:
	•	Target context:
	•	Core value claim:
	•	Explicit non-goals:
	•	Explicit exclusions/banned concepts:
	•	Hard constraints:
	•	Optional features:
	•	Deferred features:
	•	Key uncertainties/assumptions:
	•	Success metrics:
	•	Regulatory/legal posture:
	•	Implementation scope:
	•	Business model/GTM:

This should be mandatory. Most drift failures happen because the evaluator never first formalized what the prompt was actually committing to.

⸻

12. Types of Evidence an Agent Should Use

When evaluating whether a generated claim is valid, the evaluator should classify evidence quality.

12.1 Strong support

Directly stated in the prompt.

12.2 Moderate support

Logically implied by multiple prompt elements.

12.3 Weak support

Plausible but not clearly anchored.

12.4 No support

Not present and not clearly implied.

12.5 Contradicted

Conflicts with explicit prompt content.

Only strong and moderate support should be treated as safe for unflagged inclusion.

⸻

13. Common Drift Patterns in Prompt-to-Plan Systems

AI agents should specifically watch for these recurring failure modes.

13.1 Consultant inflation

The plan becomes more strategic-sounding but less grounded.

Signs:
	•	category creation language
	•	transformation claims
	•	ecosystem/platform inflation
	•	market-share rhetoric
	•	grand positioning language

13.2 Fabricated concreteness

The model invents details to make the plan feel complete.

Signs:
	•	specific tools
	•	specific staff roles
	•	specific offices or neighborhoods
	•	precise percentages
	•	detailed budgets without source basis

13.3 Confidence laundering

The model removes caveats and uncertainty.

Signs:
	•	“may” becomes “will”
	•	pilot assumptions become operating facts
	•	unproven GTM becomes settled strategy

13.4 Future-roadmap takeover

Deferred or optional features dominate the document.

Signs:
	•	future sectors overshadow initial wedge
	•	advanced scoring overshadows core workflow
	•	strategic expansion overtakes initial validation

13.5 Misplaced optimization

The plan improves readability while distorting substance.

Signs:
	•	weak ideas become cleaner but stronger sounding
	•	unsupported assumptions are made consistent instead of being flagged
	•	ambiguity is hidden rather than preserved

13.6 Constraint decay

Hard boundaries vanish as the plan expands.

Signs:
	•	banned framings subtly reappear
	•	excluded markets return as “future opportunities”
	•	optional features become implicit requirements

⸻

14. Revision Guidance After Drift Detection

The framework should not only detect drift. It should recommend repairs.

14.1 If unsupported invention is high

Require all material claims to be labeled as:
	•	source-stated
	•	source-derived
	•	speculative

14.2 If scope drift is high

Force the model to regenerate using a locked scope summary.

14.3 If constraint drift is high

Promote constraints into an immutable “must preserve” block.

14.4 If confidence inflation is high

Require modal language restoration:
	•	may
	•	could
	•	assumed
	•	conditional on
	•	unverified
	•	exploratory

14.5 If priority drift is high

Force the model to restate:
	•	core product
	•	optional layers
	•	deferred layers

before writing full sections.

14.6 If source-trace fidelity is low

Require every major paragraph to map to one or more source prompt elements.

⸻

15. Recommendations for System Architecture

To reduce drift in planning systems, the generation pipeline itself should be changed.

15.1 Add a locked source contract layer

Before plan generation, create a compact immutable contract containing:
	•	core intent
	•	non-goals
	•	exclusions
	•	buyer
	•	product
	•	causal logic
	•	uncertainty posture

Every downstream step should reference this.

15.2 Require source attribution tags internally

Each generated section should internally label its claims as:
	•	source-stated
	•	source-derived
	•	speculative

These tags do not always need to appear in the final user document, but they should exist in the system.

15.3 Add a contradiction checker

Run a dedicated pass that asks:
	•	What did the source explicitly reject?
	•	Did the output reintroduce any of it?
	•	What did the source treat as optional that the output treated as core?

15.4 Add an unsupported-specificity checker

Run a pass that flags:
	•	numbers
	•	tools
	•	teams
	•	legal interpretations
	•	geographic advantages
	•	market size claims
	•	operating assumptions

unless grounded in source text.

15.5 Add an epistemic-preservation checker

Run a pass that compares modal language between source and output:
	•	maybe
	•	likely
	•	assumed
	•	uncertain
	•	conditional
	•	possible

If these disappear, the system should flag potential confidence inflation.

15.6 Prefer explicit incompleteness over invented completeness

The system should be allowed to say:
	•	unspecified
	•	not provided
	•	unclear from source
	•	assumption required
	•	should be validated

This is better than filling gaps with plausible fiction.

⸻

16. Benchmarking and Evaluation Dataset Design

To make the framework operational, create a benchmark dataset.

Each evaluation case should contain:
	•	initial prompt
	•	generated plan
	•	gold prompt contract
	•	annotated drift incidents
	•	severity labels
	•	final accept/reject judgment

16.1 Dataset diversity

Include prompts with:
	•	hard exclusions
	•	optional features
	•	explicit uncertainty
	•	banned terms
	•	narrow wedges
	•	legal caveats
	•	phased roadmaps
	•	budget ambiguity
	•	deliberately incomplete information

16.2 Adversarial cases

Include prompts designed to tempt drift:
	•	prompts with prestigious adjacent markets
	•	prompts with missing operational detail
	•	prompts with sharp anti-hype constraints
	•	prompts where the most natural completion would be wrong

16.3 Evaluation metrics for the evaluator

If using AI agents to detect drift, measure:
	•	precision on true drift incidents
	•	recall on critical drift incidents
	•	agreement with expert labels
	•	false positives on harmless elaboration
	•	performance by drift type

⸻

17. Minimal Acceptability Standard

A generated plan should be considered acceptable only if all of the following are true:
	•	no critical constraint violations
	•	no material customer or business model drift
	•	no repeated unsupported invention in important sections
	•	uncertainty is preserved where present in source
	•	optional features are not misrepresented as core
	•	source-grounded value logic remains intact
	•	the output is more useful than the input without becoming less truthful

⸻

18. Final Recommendation

The best way to measure drift is not by asking, “Does the generated plan sound good?”

The right question is:

Does the generated plan remain loyal to the source prompt’s commitments, limits, and uncertainty while making the content more usable?

That requires a structured evaluation system built around:
	•	prompt contract extraction
	•	multi-dimensional fidelity scoring
	•	drift incident logging
	•	severity classification
	•	unsupported claim detection
	•	constraint violation detection
	•	epistemic posture preservation

A planning system should be judged not only by richness, coherence, and completeness, but by its ability to avoid becoming more impressive at the cost of becoming less true.

That is the core principle this proposal recommends.
