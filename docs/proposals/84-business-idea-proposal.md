Proposal: Iterative Business Idea Generator with Critique-and-Revision Loops

1. Purpose

This proposal defines a system for generating and refining business ideas through a structured multi-round loop.

The system starts from an initial business idea prompt, critiques it hard, revises it, critiques it again, and continues for 3 to 5 rounds. At the end, the idea is either:
	•	accepted as a keeper
	•	rejected as unsalvageable
	•	parked as interesting but not yet investable

The goal is not to reward ideas for sounding clever. The goal is to pressure-test them until weak ideas collapse quickly and strong ideas become sharper, narrower, and more realistic.

This system is designed for use by AI agents that do not know anything about prior conversation history.

⸻

2. Core Concept

The system uses at least two roles:

Role A: Critic

A harsh evaluator that attacks the current version of the idea.

Its job is to identify:
	•	false assumptions
	•	weak demand logic
	•	vague customer definitions
	•	fake differentiation
	•	impossible GTM
	•	regulatory or operational blockers
	•	overbuilt product fantasies
	•	business models that do not work
	•	ideas that are simply not worth saving

Role B: Reviser

A generator that takes the critique seriously and produces the next version.

Its job is not to defend the old version. Its job is to:
	•	narrow scope
	•	remove bad claims
	•	change target market if needed
	•	simplify the product
	•	preserve what still works
	•	rewrite the idea into a stronger version

Optionally, a third role can exist:

Role C: Judge

A final evaluator that decides whether the idea is now a keeper, should continue, or should be rejected.

This role is useful because a reviser tends to be optimistic and a critic can become destructively negative.

⸻

3. High-Level Workflow

The workflow is simple.

Round 0

User provides an initial idea prompt, called Prompt V1.

Round 1

Critic evaluates Prompt V1 and produces:
	•	a brutal critique
	•	a diagnosis of what is broken
	•	a salvageability assessment
	•	revision priorities

Reviser then produces Prompt V2.

Round 2

Critic evaluates Prompt V2.
Reviser produces Prompt V3.

Round 3

Critic evaluates Prompt V3.
Reviser produces Prompt V4.

Optional Rounds 4 and 5

Repeat if the idea is improving but not yet good enough.

Final Decision

After 3 to 5 rounds, the Judge assigns one of:
	•	KEEPER
	•	REJECT
	•	PARK / NEEDS HUMAN REFRAME

⸻

4. Design Goal

The system should optimize for this:

rapid elimination of bad ideas, and disciplined sharpening of good ideas

It should not optimize for:
	•	creativity theater
	•	idea inflation
	•	making every idea sound fundable
	•	endless iteration with no decisive outcome

If an idea is bad, the system should say so.

If an idea is fixable, the system should make it materially better, not just cosmetically cleaner.

⸻

5. What Counts as a Good Outcome

A good outcome is not “the final prompt sounds polished.”

A good outcome is one of these:

5.1 Strong keeper

The final idea has:
	•	a clear buyer
	•	a real pain point
	•	a plausible product
	•	a believable wedge
	•	a credible GTM
	•	manageable operational and regulatory risk
	•	a reason this business might actually work

5.2 Honest rejection

The idea is rejected with specific reasons such as:
	•	no real pain
	•	wrong customer behavior assumptions
	•	no economic engine
	•	impossible acquisition channel
	•	unsalvageable dependence on hype
	•	market too broad and generic
	•	product too complex for the value delivered
	•	legally or operationally blocked
	•	all attempted revisions still converge on a weak core

5.3 Useful parking decision

The idea may be interesting, but the system determines:
	•	it needs a different customer
	•	it needs a different wedge
	•	it should become a feature, not a company
	•	it belongs inside an existing workflow rather than as a standalone business

That is a valid result.

⸻

6. System Philosophy

This generator should behave like a hard-nosed early-stage filter, not like a cheerleader.

It should follow these principles:

6.1 Brutal honesty

Do not protect the idea from criticism.

6.2 Specificity over abstraction

“Interesting” is not enough. Name the actual problem.

6.3 Narrowing is progress

A smaller sharper idea is usually better than a broad ambitious one.

6.4 Workflow pain beats conceptual elegance

The best ideas usually solve an ugly real problem, not an intellectually neat one.

6.5 Reject fake moats

“AI”, “platform”, “matching”, “network effects”, “personalization”, and “marketplace” should not be treated as strengths unless the economics and behavior really support them.

6.6 Prefer kill decisions over fake refinement

If the idea is rotten at the core, stop polishing it.

⸻

7. Required Inputs

The system should accept:
	•	initial idea prompt
	•	optional constraints from the user
	•	optional banned words or banned framings
	•	optional target market or region
	•	optional budget, team, or timeline assumptions

The system should not require business-plan-level detail at the start. It should be able to work from a rough idea.

⸻

8. Required Outputs Per Round

Each critique round should output all of the following.

8.1 Current idea summary

A concise restatement of the current version.

8.2 What improved since last round

Only for rounds after V1.

8.3 Core weaknesses

The top reasons the idea is weak.

8.4 Salvageable elements

The pieces worth preserving.

8.5 Non-salvageable elements

The parts that should be deleted, not repaired.

8.6 Revision priorities

The minimum changes needed for the next version.

8.7 Round verdict

One of:
	•	improve and continue
	•	major pivot required
	•	reject now

The reviser then produces the next prompt version in full.

⸻

9. Final Output Requirements

At the end of the process, the system must output:

9.1 Final verdict
	•	KEEPER
	•	REJECT
	•	PARK

9.2 Confidence level
	•	high
	•	medium
	•	low

9.3 Why

A plain-language explanation of the final decision.

9.4 Best final version

The strongest prompt version reached.

9.5 Decision memo

A short memo covering:
	•	target buyer
	•	problem
	•	wedge
	•	business model
	•	GTM
	•	main risks
	•	why it survived or failed

⸻

10. Evaluation Dimensions

Each round should score the current idea across these dimensions.

Use a 0 to 5 scale.
	•	Problem Reality — is the pain real and strong?
	•	Buyer Clarity — is there a clear buyer?
	•	User Need — does the actual user care?
	•	Value Proposition — is the product meaningfully useful?
	•	Differentiation — is there something non-generic here?
	•	GTM Credibility — can this plausibly get customers?
	•	Operational Feasibility — can it actually be built and run?
	•	Economic Viability — is there a believable business model?
	•	Regulatory/Trust Risk — does legal or trust friction kill it?
	•	Scope Discipline — is it focused enough to test?

These scores are not the final answer by themselves. They are inputs into the round judgment.

⸻

11. Rejection Criteria

An idea should be rejected early if one or more of these conditions persist after revision.

11.1 No real pain

The user inconvenience is mild, optional, or already adequately solved.

11.2 No buyer with urgency

Even if the product is useful, nobody has enough pain to pay or change workflow.

11.3 Generic solution syndrome

The idea is a vague “platform”, “engine”, or “marketplace” with no sharp wedge.

11.4 Impossible adoption model

The product requires too much behavior change from too many parties.

11.5 No credible distribution

There is no believable path to get initial customers.

11.6 Bad economics

The product would be expensive to deliver and hard to charge enough for.

11.7 Dependency on false assumptions

The business only works if users behave in unrealistic ways.

11.8 Regulatory or trust barrier too high

Legal exposure, procurement friction, or trust requirements are too severe for the proposed wedge.

11.9 Endless revision without convergence

If after multiple rounds the idea remains broad, confused, or dependent on major hand-waving, reject it.

⸻

12. Keeper Criteria

An idea can be marked a keeper if by the end it satisfies most of these:
	•	strong pain in a specific buyer segment
	•	a narrow, testable wedge
	•	a product that clearly fits the pain
	•	credible first customer acquisition path
	•	reasonable delivery scope for an MVP
	•	business model with believable willingness to pay
	•	no fatal regulatory or behavior-change blocker
	•	clear articulation of what the business is not
	•	improvement across rounds that converges rather than sprawls

A keeper does not need to be perfect. It needs to be worth testing in the real world.

⸻

13. Parking Criteria

An idea should be parked rather than rejected if:
	•	the core pain seems real
	•	but the proposed product shape is wrong
	•	and the business may work only under a different framing

Examples:
	•	should be sold as internal tooling, not a marketplace
	•	should target one niche customer, not a broad sector
	•	should be a feature inside another workflow
	•	should become a services-led wedge before software

Park means:
not good enough as currently framed, but not dead

⸻

14. Iteration Limits

The system should run for 3 to 5 rounds maximum.

Why:
	•	fewer than 3 rounds often does not separate cosmetic improvement from real improvement
	•	more than 5 rounds often becomes diminishing returns or idea-rescue theater

Recommended rule:
	•	minimum 3 rounds
	•	stop early only if the idea is obviously dead
	•	hard cap at 5 rounds

⸻

15. Stop Rules

The process stops when one of the following occurs.

15.1 Keeper stop

The idea reaches keeper threshold before round 5.

15.2 Hard reject stop

The critic determines the idea is fundamentally broken and revisions are not fixing the core.

15.3 No-progress stop

Two consecutive rounds show mostly wording changes and no meaningful business improvement.

15.4 Convergence stop

The idea is now coherent, focused, and the next revision would likely be marginal only.

⸻

16. Suggested Round Logic

Round 1: Kill fantasy

Main task:
	•	identify whether the idea is pointed at a real problem or a conceptual mirage

Focus on:
	•	who cares
	•	why they care
	•	why now
	•	what is fake

Round 2: Find the wedge

Main task:
	•	narrow the idea until it becomes sellable

Focus on:
	•	one buyer
	•	one workflow
	•	one pain
	•	one adoption path

Round 3: Stress the business

Main task:
	•	test whether the sharpened idea still holds commercially

Focus on:
	•	GTM
	•	implementation friction
	•	economics
	•	trust/regulation
	•	behavior change

Round 4: Remove remaining fluff

Main task:
	•	strip strategic theater and fake sophistication

Focus on:
	•	unnecessary features
	•	optional vs core
	•	inflated claims
	•	implementation realism

Round 5: Final verdict

Main task:
	•	decide whether the idea deserves real-world testing

⸻

17. Agent Roles in Detail

17.1 Critic agent instructions

The critic should:
	•	be direct
	•	focus on market truth, not politeness
	•	attack assumptions
	•	identify the deepest flaw, not just surface flaws
	•	prefer fewer stronger criticisms over many weak ones
	•	state when an idea is drifting instead of improving

The critic should not:
	•	rewrite the entire idea
	•	add lots of speculative features
	•	rescue weak ideas through imagination alone

17.2 Reviser agent instructions

The reviser should:
	•	preserve only what survives criticism
	•	narrow scope aggressively
	•	remove claims that cannot be defended
	•	rewrite the prompt into a stronger version
	•	explicitly carry forward constraints and non-goals

The reviser should not:
	•	defend weak parts from earlier versions
	•	add grand strategy fluff
	•	compensate for criticism by adding complexity

17.3 Judge agent instructions

The judge should:
	•	compare progression across rounds
	•	check whether improvement is real
	•	distinguish sharpened ideas from cosmetically polished ones
	•	make a decisive final call

The judge should not:
	•	keep iterating to avoid making a decision

⸻

18. Prompt Templates

18.1 Critic prompt template

Use this structure for the critic agent:

Input
	•	current idea version
	•	previous critique summary
	•	previous version summary
	•	current round number

Task

Critique this business idea brutally. Focus on whether this is a real business worth pursuing. Identify:
	•	the deepest flaws
	•	what is salvageable
	•	what should be deleted entirely
	•	whether this should continue to another round or be rejected now

Score it on:
	•	Problem Reality
	•	Buyer Clarity
	•	Value Proposition
	•	GTM Credibility
	•	Operational Feasibility
	•	Economic Viability
	•	Scope Discipline

Then provide:
	•	top 3 fatal issues
	•	top 3 salvageable strengths
	•	revision priorities
	•	round verdict

18.2 Reviser prompt template

Use this structure for the reviser agent:

Input
	•	current idea version
	•	latest critique
	•	all persistent constraints
	•	all explicit non-goals
	•	current round number

Task

Produce the next version of the business idea prompt. Do not defend weak elements. Remove bad assumptions. Preserve the strongest surviving core. Narrow the scope if necessary. Keep the idea realistic, disciplined, and commercially sharper than the previous version.

Output:
	•	short summary of major changes
	•	full revised prompt
	•	what was intentionally removed
	•	unresolved risks still remaining

18.3 Judge prompt template

Use this structure for the judge agent:

Input
	•	all prompt versions
	•	all critiques
	•	all revision summaries

Task

Determine whether this idea is now a KEEPER, REJECT, or PARK. Explain whether the idea improved meaningfully across rounds or merely became more polished. State the main reason for the final decision and whether further iteration is likely to help.

⸻

19. Scoring and Thresholds

Use a 0 to 5 score for each dimension.

Suggested weighted score:
	•	Problem Reality: 20%
	•	Buyer Clarity: 15%
	•	Value Proposition: 15%
	•	GTM Credibility: 15%
	•	Economic Viability: 10%
	•	Operational Feasibility: 10%
	•	Scope Discipline: 10%
	•	Regulatory/Trust Risk: 5%

Thresholds

KEEPER
	•	weighted score >= 4.0
	•	no fatal flaw unresolved
	•	clear wedge and buyer
	•	credible GTM path

PARK
	•	weighted score 3.0 to 3.99
	•	some promise remains
	•	but product shape, GTM, or customer framing still needs a human rethink

REJECT
	•	weighted score < 3.0
	•	or fatal flaw persists after multiple rounds
	•	or no meaningful convergence by round 4 or 5

A fatal flaw can override the score.

⸻

20. Fatal Flaw Rules

Automatic reject if any of these remain unresolved by round 3 or later:
	•	no buyer with urgent pain
	•	no plausible route to first customers
	•	product still depends on unrealistic multi-party adoption
	•	core value proposition still vague
	•	business depends on made-up behavior change
	•	economics clearly do not support the proposed delivery model
	•	legal/trust barrier is central and not credibly addressed
	•	every revision merely changes wording, not the business

⸻

21. Anti-Gaming Rules

The system must defend against fake improvement.

21.1 Do not reward longer prompts

More detail is not improvement.

21.2 Do not reward jargon

Words like platform, thesis, optimization, ecosystem, intelligence, transformation, and scalable are not evidence.

21.3 Do not reward complexity

Adding layers, dashboards, matching, analytics, and scoring often makes ideas worse.

21.4 Do not reward confidence

Stronger language is not stronger logic.

21.5 Do not reward breadth

Expansion across sectors or users usually means the idea is still blurry.

⸻

22. Failure Modes of the Generator Itself

The system can fail even if the idea is decent.

Watch for these system-level failures:

22.1 Critic becomes repetitive

The same critique is repeated without deeper diagnosis.

22.2 Reviser becomes defensive

Bad assumptions remain alive round after round.

22.3 Reviser becomes decorative

The prompt gets cleaner but not better.

22.4 Judge becomes indecisive

The system keeps iterating to avoid admitting the idea is weak.

22.5 Optimism bias

The system tries too hard to save every idea.

22.6 Complexity drift

Each round adds more machinery instead of simplifying the business.

⸻

23. Recommended Logging Structure

Each round should be stored with:
	•	round number
	•	idea version
	•	critic scores
	•	critic fatal issues
	•	critic salvageable strengths
	•	revision priorities
	•	revised version
	•	major changes
	•	unresolved risks
	•	continue / reject signal

This makes it possible to inspect whether progress is real.

⸻

24. Suggested Output Schema

{
  "meta": {
    "max_rounds": 5,
    "current_round": 3,
    "status": "continue | keeper | park | reject"
  },
  "idea_versions": [
    {
      "version": "V1",
      "prompt": "...",
      "summary": "..."
    },
    {
      "version": "V2",
      "prompt": "...",
      "summary": "..."
    }
  ],
  "rounds": [
    {
      "round": 1,
      "critic_scores": {
        "problem_reality": 2,
        "buyer_clarity": 2,
        "value_proposition": 2,
        "gtm_credibility": 1,
        "operational_feasibility": 3,
        "economic_viability": 2,
        "scope_discipline": 1,
        "regulatory_trust_risk": 2
      },
      "fatal_issues": [
        "...",
        "...",
        "..."
      ],
      "salvageable_strengths": [
        "...",
        "...",
        "..."
      ],
      "revision_priorities": [
        "...",
        "...",
        "..."
      ],
      "round_verdict": "continue"
    }
  ],
  "final_decision": {
    "verdict": "KEEPER | PARK | REJECT",
    "confidence": "high | medium | low",
    "reason": "...",
    "best_version": "V4",
    "further_iteration_likely_helpful": false
  }
}


⸻

25. Best-Practice Operating Mode

The strongest operating mode is:
	•	one critic model
	•	one reviser model
	•	one judge model
	•	hard round cap
	•	hard reject capability
	•	visible scoring
	•	visible reasons for rejection
	•	visible record of what changed each round

This creates a process that is actually useful instead of just generative.

⸻

26. Recommended Final Framing

The system should be positioned as:

an iterative business idea filter and refinement engine that pressure-tests concepts through repeated adversarial critique and revision, then forces a keep / park / reject decision within 3 to 5 rounds

That framing is honest and useful.

It does not promise to invent good businesses from thin air.
It promises to do something more valuable:

separate ideas that sharpen under pressure from ideas that collapse under pressure.

That is the real job.
