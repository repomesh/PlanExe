Agent Specification: Iterative Business Idea Generator with Critique, Revision, and Final Keep/Park/Reject Decision

1. Purpose

This specification defines a strict multi-agent process for refining or rejecting business ideas over 3 to 5 rounds.

The system starts with an initial idea prompt and runs repeated cycles of:
	•	adversarial critique
	•	disciplined revision
	•	progress assessment

The process ends with a forced decision:
	•	KEEPER
	•	PARK
	•	REJECT

This is not a brainstorming tool. It is a pressure-testing and convergence tool.

Its purpose is to answer:

Does this idea get stronger under repeated criticism, or does it collapse when forced to become specific?

⸻

2. Core Operating Principle

The system must optimize for:

truth-seeking, narrowing, and decisive judgment

It must not optimize for:
	•	making every idea sound impressive
	•	endless refinement without convergence
	•	preserving user ego
	•	turning weak ideas into polished nonsense
	•	adding complexity to escape criticism

A strong idea should survive pressure by becoming clearer, narrower, and more grounded.

A weak idea should be rejected quickly.

⸻

3. Final Outputs

Every run must end in exactly one of these states:

3.1 KEEPER

The idea is worth real-world testing.

3.2 PARK

The idea has some real substance, but its current framing is not yet strong enough. It needs a different wedge, market, delivery model, or human reframing.

3.3 REJECT

The idea is not worth further iteration in its current conceptual lineage. Further prompt refinement is unlikely to save it.

No run may end in “unclear,” “maybe,” or “continue indefinitely.”

⸻

4. Agent Roles

The system uses three roles.

4.1 Critic Agent

The critic attacks the current version of the idea.

Its job is to identify:
	•	false assumptions
	•	fake demand
	•	vague buyers
	•	bad GTM
	•	overbuilt product shape
	•	dependency on unrealistic behavior
	•	poor economics
	•	fatal trust/regulatory issues
	•	generic solution syndrome

The critic must be harsh, specific, and willing to kill the idea.

4.2 Reviser Agent

The reviser creates the next version.

Its job is to:
	•	preserve only what survives critique
	•	remove weak assumptions
	•	narrow the idea
	•	simplify the product
	•	carry forward explicit constraints and non-goals
	•	produce the next prompt version

The reviser must not defend the old version.

4.3 Judge Agent

The judge determines whether the idea should continue, be parked, or be rejected.

Its job is to:
	•	inspect progress across rounds
	•	detect fake improvement
	•	decide whether convergence is real
	•	force a final outcome by round 5

The judge must not avoid a hard decision.

⸻

5. State Machine

The system operates as a strict finite-state process.

5.1 States
	•	INIT
	•	CRITIQUE_ROUND
	•	REVISION_ROUND
	•	INTERMEDIATE_DECISION
	•	FINAL_DECISION
	•	END_KEEPER
	•	END_PARK
	•	END_REJECT

5.2 Allowed Transitions

INIT -> CRITIQUE_ROUND

Start with Prompt V1.

CRITIQUE_ROUND -> REVISION_ROUND

If the critic verdict is:
	•	continue
	•	continue with major pivot

CRITIQUE_ROUND -> FINAL_DECISION

If the critic verdict is:
	•	reject now

REVISION_ROUND -> INTERMEDIATE_DECISION

After a new version is generated.

INTERMEDIATE_DECISION -> CRITIQUE_ROUND

If:
	•	round count < max rounds
	•	no stop condition triggered

INTERMEDIATE_DECISION -> FINAL_DECISION

If:
	•	convergence reached
	•	no-progress stop triggered
	•	fatal flaw persists
	•	round cap reached

FINAL_DECISION -> END_KEEPER / END_PARK / END_REJECT

Exactly one terminal state.

5.3 Hard Limits
	•	minimum rounds before keeper decision: 3
	•	maximum total rounds: 5
	•	early reject allowed: yes
	•	early keeper before round 3: not allowed

Reason:
A single good-looking rewrite is not enough evidence that the idea is genuinely strong.

⸻

6. Required Inputs

The system must accept:
	•	initial business idea prompt
	•	optional user constraints
	•	optional banned words
	•	optional banned framings
	•	optional region/market focus
	•	optional team/budget/timeline assumptions

The system must preserve these inputs across all rounds.

⸻

7. Persistent Constraint Register

Before round 1, the system must create a Persistent Constraint Register.

This register stores:
	•	explicit non-goals
	•	banned concepts
	•	banned language framings
	•	target geography limits
	•	user-imposed scope limits
	•	positioning constraints
	•	technical/legal/business assumptions that must persist

This register is immutable unless the user explicitly changes it.

Every round must reference it.

⸻

8. Mandatory Data Stored Per Version

Each idea version must be stored as a structured object.

8.1 Version schema
	•	version_id
	•	round_created
	•	full_prompt_text
	•	one-paragraph summary
	•	target buyer
	•	target user
	•	core pain
	•	proposed product
	•	business model
	•	GTM hypothesis
	•	main assumptions
	•	known risks
	•	explicit non-goals
	•	open questions

This is necessary so later agents can compare actual business changes, not just wording.

⸻

9. Mandatory Critique Output Per Round

The critic must produce all of the following.

9.1 Current Idea Summary

A concise summary of the current idea in plain language.

9.2 Scores

Each from 0 to 5:
	•	Problem Reality
	•	Buyer Clarity
	•	User Need
	•	Value Proposition
	•	Differentiation
	•	GTM Credibility
	•	Operational Feasibility
	•	Economic Viability
	•	Regulatory/Trust Risk
	•	Scope Discipline

9.3 Top 3 Fatal Issues

The deepest reasons the idea may fail.

9.4 Top 3 Salvageable Strengths

The parts worth preserving into the next round.

9.5 Non-Salvageable Elements

Elements that should be deleted, not repaired.

9.6 Revision Priorities

The minimum changes required in the next version.

9.7 Drift Check vs Previous Version

From round 2 onward, the critic must assess:
	•	what actually improved
	•	what merely got reworded
	•	whether the idea narrowed or sprawled
	•	whether complexity increased without justification

9.8 Round Verdict

Exactly one:
	•	continue
	•	continue with major pivot
	•	reject now

⸻

10. Mandatory Revision Output Per Round

The reviser must produce all of the following.

10.1 Revision Summary

What changed and why.

10.2 Full Revised Prompt

The next prompt version in complete form.

10.3 What Was Intentionally Removed

A list of elements cut due to critique.

10.4 What Was Preserved

The surviving core elements.

10.5 Unresolved Risks

The risks still not solved by this revision.

10.6 Constraint Compliance Check

A short confirmation that the revision preserved:
	•	persistent constraints
	•	banned framings
	•	non-goals
	•	scope limits

If the reviser changed any of these, it must explicitly declare it as a violation.

⸻

11. Mandatory Judge Output at Intermediate and Final Decision Points

The judge must produce:

11.1 Progress Assessment

Has the idea materially improved?

11.2 Convergence Assessment

Is the idea getting sharper, or just changing costume?

11.3 Persistent Fatal Flaw Check

What deep flaw remains unresolved across rounds?

11.4 Recommendation

Exactly one:
	•	continue
	•	continue only if major pivot occurs
	•	park
	•	reject
	•	keeper

At intermediate stages, only continue, continue only if major pivot occurs, or reject may be used.

At final stage, only keeper, park, or reject may be used.

⸻

12. Evaluation Dimensions and Weights

Each critique round must compute a weighted score.

12.1 Dimensions
	•	Problem Reality — 20%
	•	Buyer Clarity — 15%
	•	User Need — 5%
	•	Value Proposition — 15%
	•	Differentiation — 10%
	•	GTM Credibility — 15%
	•	Operational Feasibility — 10%
	•	Economic Viability — 10%
	•	Regulatory/Trust Risk — 5%
	•	Scope Discipline — 5%

Total: 100%

12.2 Scale
	•	5 = very strong
	•	4 = strong
	•	3 = mixed but plausible
	•	2 = weak
	•	1 = very weak
	•	0 = failed / absent

⸻

13. Stop Conditions

The process must stop when any of these conditions is met.

13.1 Early Reject Stop

Triggered when:
	•	the idea has a fatal flaw that critique shows is structural, not fixable through revision
	•	or the critic explicitly says the core business is unsalvageable

Allowed from round 1 onward.

13.2 No-Progress Stop

Triggered when two consecutive revision rounds produce:
	•	mostly wording changes
	•	no meaningful business improvement
	•	no sharper wedge
	•	no better buyer clarity
	•	no better GTM logic

This results in final decision, usually REJECT or PARK.

13.3 Persistent Fatal Flaw Stop

Triggered when the same fatal flaw survives into round 3 or later with no serious resolution.

Examples:
	•	no urgent buyer pain
	•	no plausible distribution
	•	dependency on unrealistic two-sided adoption
	•	business model still vague
	•	compliance/trust barrier still central and unaddressed

13.4 Convergence Stop

Triggered when by round 3 or later:
	•	the idea has become coherent
	•	the wedge is sharp
	•	remaining changes would be incremental only

This leads to final decision, not more rounds.

13.5 Round Cap Stop

At round 5, final decision is mandatory.

⸻

14. Fatal Flaw List

These flaws can trigger reject decisions.

14.1 No Strong Buyer Pain

The problem is mild, optional, or not important enough to drive purchase.

14.2 No Buyer with Budget or Authority

The supposed user may care, but there is no actual buyer with power to adopt.

14.3 Generic Solution Syndrome

The idea remains a vague platform, engine, marketplace, or tool with no sharp wedge.

14.4 Impossible Adoption Model

The product needs too many actors to change behavior at once.

14.5 No Credible GTM

There is no believable path to land early customers.

14.6 Bad Unit Logic

The delivery cost, sales cost, or implementation burden makes the economics unattractive.

14.7 Regulatory or Trust Barrier Too High

Trust, legal, or procurement burden is central and unresolved.

14.8 Product Complexity Outruns Value

The proposed system is too elaborate for the pain it solves.

14.9 Revision Non-Convergence

The idea keeps mutating but never sharpens.

⸻

15. Keeper Criteria

An idea qualifies as KEEPER only if all are broadly true by the final round.
	•	clear buyer
	•	clear pain
	•	clear wedge
	•	plausible first product
	•	credible early GTM
	•	no fatal unresolved blocker
	•	realistic enough to test
	•	better after critique, not merely more polished
	•	narrower and stronger than earlier versions

Suggested keeper thresholds:
	•	weighted score >= 4.0
	•	no dimension below 3 except Differentiation or Regulatory/Trust Risk, which may be 2 if clearly manageable
	•	no fatal flaw unresolved

⸻

16. Park Criteria

Use PARK when:
	•	there is a real pain
	•	there may be a business here
	•	but the current product framing is wrong, too broad, too early, or commercially weak

Typical PARK patterns:
	•	better as a service than software
	•	better as a feature than a company
	•	needs a narrower customer
	•	needs a different GTM wedge
	•	idea quality improved, but not enough to justify immediate execution

Suggested park thresholds:
	•	weighted score between 3.0 and 3.99
	•	no single fatal flaw that proves the whole lineage dead
	•	but not enough convergence to justify keeper

⸻

17. Reject Criteria

Use REJECT when:
	•	weighted score < 3.0 by final stage
	•	fatal flaw persists after multiple rounds
	•	no meaningful convergence
	•	revisions only decorate the idea
	•	business still depends on unrealistic assumptions
	•	there is no credible route to actual adoption

A good rejection must name:
	•	the central reason
	•	why revisions failed to fix it
	•	why further iteration is unlikely to help

⸻

18. Anti-Gaming Rules

The system must explicitly resist fake improvement.

18.1 Do not reward length

Longer prompts are not better.

18.2 Do not reward jargon

Words like platform, ecosystem, intelligence, optimization, thesis, transformation, scalable, or data-driven do not count as business quality.

18.3 Do not reward complexity

More layers, features, dashboards, scoring, or matching often indicate weakness.

18.4 Do not reward confidence inflation

Stronger language without stronger logic is negative, not positive.

18.5 Do not reward breadth

Adding sectors, users, or market types usually means the wedge is still weak.

18.6 Penalize decorative pivots

If an idea changes labels but preserves the same broken assumptions, treat that as non-progress.

⸻

19. Round-by-Round Operating Logic

Round 1: Reality Check

Goal:
Determine whether there is any real business worth saving.

Focus:
	•	is the pain real?
	•	who buys?
	•	what is fake or overbuilt?

Expected outcomes:
	•	narrow survival core identified
	•	fantasy elements cut
	•	reject early if core is rotten

Round 2: Wedge Formation

Goal:
Turn the surviving idea into a narrower business.

Focus:
	•	one customer
	•	one pain
	•	one workflow
	•	one believable initial product
	•	one acquisition path

Expected outcomes:
	•	sharper product shape
	•	less conceptual fog
	•	clearer GTM hypothesis

Round 3: Commercial Stress Test

Goal:
Test whether the narrower idea still works as a business.

Focus:
	•	adoption friction
	•	sales reality
	•	economics
	•	delivery model
	•	trust/compliance burden

Expected outcomes:
	•	keeper candidate
	•	park candidate
	•	reject if the core still does not hold

Round 4: De-Fluffing and Hard Choice

Goal:
Remove remaining strategic theater and force realism.

Focus:
	•	strip optional nonsense
	•	compress to real wedge
	•	verify that score improvements are real

Expected outcomes:
	•	convergence or rejection

Round 5: Final Forced Decision

Goal:
No more ideation. Final judgment only.

⸻

20. Revision Rules

The reviser must obey these mandatory rules.

20.1 Preserve only what survives

Do not carry forward features or claims that the critic identified as broken unless directly repaired.

20.2 Prefer subtraction over addition

The default response to critique should be narrowing, not layering.

20.3 Make explicit changes

Do not quietly mutate the business. State what changed.

20.4 Carry forward non-goals

If the previous version correctly established what the idea is not, preserve that unless deliberately changed and justified.

20.5 Do not solve criticism with hype

Do not respond to weak GTM, weak pain, or weak economics by adding platform rhetoric, market size rhetoric, or technological sophistication.

⸻

21. Judge Decision Logic

The judge must compare versions longitudinally.

21.1 Real Improvement Test

A round counts as real improvement only if at least one of these occurred:
	•	clearer buyer
	•	stronger pain logic
	•	narrower wedge
	•	more plausible GTM
	•	simpler and more believable product
	•	lower adoption burden
	•	better economic logic
	•	lower regulatory or trust risk

21.2 Fake Improvement Test

A round counts as fake improvement if changes are mostly:
	•	wording cleanup
	•	jargon replacement
	•	more detail without more truth
	•	added features
	•	broader market story
	•	stronger confidence language
	•	more polished business-plan formatting

21.3 Convergence Test

The idea has converged when:
	•	core identity remains stable across the last two versions
	•	scores improved or stabilized at a high enough level
	•	remaining issues are execution risks, not conceptual incoherence

⸻

22. Required Logging Structure

The system must log each round as a structured record.

22.1 Round log fields
	•	round_number
	•	input_version_id
	•	critic_summary
	•	critic_scores
	•	weighted_score
	•	fatal_issues
	•	salvageable_strengths
	•	non_salvageable_elements
	•	revision_priorities
	•	critic_verdict
	•	reviser_change_summary
	•	revised_version_id
	•	removed_elements
	•	preserved_elements
	•	unresolved_risks
	•	judge_progress_assessment
	•	judge_convergence_assessment
	•	judge_recommendation
	•	continue_flag

This log is required for auditability and for later benchmarking the generator.

⸻

23. Required Final Decision Memo

At the end, the judge must produce a final memo containing:

23.1 Final verdict

KEEPER / PARK / REJECT

23.2 Confidence

high / medium / low

23.3 Best version reached

V2 / V3 / V4 / V5

23.4 Why this idea survived or failed

One clear paragraph.

23.5 Strongest remaining rationale

Why someone might still pursue it.

23.6 Core blocking reason if parked or rejected

The single deepest blocker.

23.7 Whether more iteration is likely useful

true / false

If false, say why.

⸻

24. Mandatory Structured Output Schema

{
  "run_metadata": {
    "spec_version": "1.0",
    "max_rounds": 5,
    "min_rounds_for_keeper": 3,
    "current_state": "INIT | CRITIQUE_ROUND | REVISION_ROUND | INTERMEDIATE_DECISION | FINAL_DECISION | END_KEEPER | END_PARK | END_REJECT"
  },
  "persistent_constraint_register": {
    "user_constraints": [],
    "banned_words": [],
    "banned_framings": [],
    "non_goals": [],
    "scope_limits": [],
    "other_persistent_rules": []
  },
  "idea_versions": [
    {
      "version_id": "V1",
      "round_created": 0,
      "full_prompt_text": "",
      "summary": "",
      "target_buyer": "",
      "target_user": "",
      "core_pain": "",
      "proposed_product": "",
      "business_model": "",
      "gtm_hypothesis": "",
      "main_assumptions": [],
      "known_risks": [],
      "explicit_non_goals": [],
      "open_questions": []
    }
  ],
  "round_logs": [
    {
      "round_number": 1,
      "input_version_id": "V1",
      "critic_output": {
        "current_idea_summary": "",
        "scores": {
          "problem_reality": 0,
          "buyer_clarity": 0,
          "user_need": 0,
          "value_proposition": 0,
          "differentiation": 0,
          "gtm_credibility": 0,
          "operational_feasibility": 0,
          "economic_viability": 0,
          "regulatory_trust_risk": 0,
          "scope_discipline": 0
        },
        "weighted_score": 0.0,
        "top_fatal_issues": [],
        "top_salvageable_strengths": [],
        "non_salvageable_elements": [],
        "revision_priorities": [],
        "drift_check_vs_previous": "",
        "round_verdict": "continue | continue_with_major_pivot | reject_now"
      },
      "reviser_output": {
        "revision_summary": "",
        "revised_version_id": "V2",
        "what_was_intentionally_removed": [],
        "what_was_preserved": [],
        "unresolved_risks": [],
        "constraint_compliance_check": ""
      },
      "judge_output": {
        "progress_assessment": "",
        "convergence_assessment": "",
        "persistent_fatal_flaw_check": "",
        "recommendation": "continue | continue_only_if_major_pivot_occurs | reject"
      },
      "continue_flag": true
    }
  ],
  "final_decision": {
    "verdict": "KEEPER | PARK | REJECT",
    "confidence": "high | medium | low",
    "best_version_id": "V4",
    "why": "",
    "strongest_remaining_rationale": "",
    "core_blocking_reason_if_not_keeper": "",
    "more_iteration_likely_useful": false
  }
}


⸻

25. Minimal Acceptance Standard for the Generator Itself

The generator process is functioning correctly only if:
	•	weak ideas are sometimes rejected early
	•	revisions usually narrow rather than expand
	•	critics identify structural flaws, not just stylistic ones
	•	judges can point to actual convergence, not just cleaner prose
	•	final decisions are forced within 5 rounds
	•	the process produces reasons, not just labels

If the system keeps producing PARK for everything, it is too soft.
If it keeps producing KEEPER for everything, it is delusional.
If it keeps producing endless “needs refinement,” it is broken.

⸻

26. Recommended Practical Configuration

Best default operating mode:
	•	1 Critic model
	•	1 Reviser model
	•	1 Judge model
	•	4 default rounds
	•	round 5 only if judge explicitly says there is meaningful unresolved potential
	•	early reject enabled
	•	hard final decision required

This keeps the process tough and avoids endless polishing.

⸻

27. Final Principle

This system should not ask:

Can this idea be made to sound better?

It should ask:

Does this idea become more real, more focused, and more commercially credible when repeatedly forced to defend itself?

If yes, it may be a keeper.

If not, kill it.