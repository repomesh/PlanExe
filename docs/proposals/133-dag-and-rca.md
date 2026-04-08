Insights on the DAG JSON Format and How RCA Can Work

Executive summary

The current JSON format has improved from a simple DAG export into a usable artifact-level provenance map.

That is a meaningful shift.

Earlier, the graph mainly described node-to-node dependency structure. Now it describes which concrete artifacts flow into which nodes. That makes the format much more useful for investigation, debugging, and root cause analysis.

The current format is now strong enough for:
	•	tracing likely upstream sources of a false claim in the final report
	•	narrowing the search to a small set of relevant artifacts
	•	identifying which node and source files are likely responsible
	•	distinguishing between a claim that was inherited versus a claim that was introduced later

However, it is still not enough for perfect claim-level attribution. It can identify likely culprit artifacts and nodes, but it cannot yet prove exactly which transformation step introduced a specific false sentence.

What the JSON format currently does well

1. It models the pipeline as dataflow, not just control flow

The biggest improvement is replacing broad dependency links with explicit inputs.

Instead of saying:
	•	node A depends on node B

it now says:
	•	node A consumes artifact X from node B

That is much more useful for debugging.

For RCA, this matters because a false claim is usually carried by data, not just by execution order.

2. It makes artifact lineage inspectable

Each node now exposes:
	•	its produced artifacts
	•	its consumed artifacts
	•	the source files associated with its implementation

This allows backward tracing from the final report to upstream intermediate artifacts.

3. It provides a practical bridge from output to code

The source_files section helps connect:
	•	the artifact chain
n- the node
	•	the relevant Python files

That means the JSON is useful not only for graph inspection, but also for code-level investigation.

4. It is now usable for structured debugging

A false claim in the final report can now be investigated as a graph traversal problem:
	1.	find the report node
	2.	inspect its input artifacts
	3.	search those artifacts for the false claim
	4.	when the claim is found upstream, recurse into that node’s inputs
	5.	continue until reaching the earliest artifact that contains the false claim
	6.	inspect that node’s source files

That is already a workable investigation process.

What the format still lacks

1. Artifact semantics are too thin

Artifacts currently have only a path.

That is useful, but weak.

The format would be stronger if artifacts also had explicit metadata such as:
	•	id
	•	format
	•	role
	•	is_intermediate
	•	audience

Example:

{
  "id": "executive_summary_markdown",
  "path": "executive_summary.md",
  "format": "md",
  "role": "summary_markdown"
}

This would make it easier to reason about whether a false claim likely originated in:
	•	raw generation
	•	normalized machine-readable output
	•	markdown rendering
	•	final report assembly

2. Claim-level provenance is missing

The current graph can tell us:
	•	which artifacts fed into a node
	•	which nodes likely influenced the report

But it cannot tell us:
	•	which sentence in the report came from which artifact section
	•	whether a sentence was synthesized from several artifacts
	•	whether the final renderer introduced a fresh falsehood

This is the main gap between good artifact-level RCA and true claim-level RCA.

3. Runtime behavior is not captured

The JSON describes intended structure, not actual execution.

It does not capture:
	•	prompt inputs actually loaded at runtime
	•	truncation behavior
	•	model configuration
	•	retries
	•	prompt templates
	•	hashes of input and output artifacts
	•	whether source files were actually included in prompt context

For LLM-heavy systems, this missing runtime provenance is important.

4. The graph does not encode why an input was used

Right now, an input edge says:
	•	this artifact was used

But not:
	•	what it was used for

A stronger format could allow fields like:

{
  "from_node": "executive_summary",
  "artifact_path": "executive_summary.md",
  "used_for": "decision-maker summary section"
}

That would improve interpretability during investigation.

How RCA can work with the current format

Goal

The goal of RCA is to answer questions like:
	•	Why is a false claim shown in report.html?
	•	Which upstream artifact first contained it?
	•	Which node likely introduced it?
	•	Which source file should be inspected first?

Investigation strategy

Step 1: Start from the final artifact

Begin with the final output artifact, such as:
	•	report.html

Find the node that produces it.

Step 2: Inspect direct inputs to the final node

Look at the report node’s inputs.

These are the first suspects.

Check whether the false claim exists in any of those artifacts.

Typical possibilities include:
	•	executive_summary.md
	•	review_plan.md
	•	questions_and_answers.md
	•	premortem.md
	•	project_plan.md
	•	team.md

Step 3: Find the earliest artifact containing the claim

Once a matching upstream artifact is found, move to the node that produced it.

Then inspect that node’s own inputs.

Repeat the process until reaching the earliest artifact where the false claim appears.

That artifact is the best candidate for the first introduction point.

Step 4: Inspect the producing node’s source files

Once the likely introduction node has been found, inspect its source_files.

In practice, the first files to inspect are often:
	•	the workflow_node file for orchestration and wiring
	•	the business_logic file for actual transformation logic

Step 5: Classify the failure mode

Once the suspect node is identified, classify the false claim into one of these rough categories:
	•	input falsehood: the claim was already present upstream
	•	transformation error: the node misread or distorted upstream content
	•	summarization drift: the claim changed during markdown or summary generation
	•	aggregation error: several true inputs were combined into a false conclusion
	•	renderer error: the final report step introduced or misformatted the claim
	•	prompt-induced hallucination: the LLM invented unsupported content

This classification matters because the fix depends on the failure mode.

Example RCA flow

Suppose the final report contains the false claim:

The project requires 12 full-time engineers.

A practical investigation would look like this:
	1.	search report.html for the claim
	2.	inspect the report node inputs
	3.	search executive_summary.md
	4.	search review_plan.md
	5.	search team.md
	6.	if the claim appears in team.md, inspect the team_markdown node
	7.	inspect that node’s inputs:
	•	enrich_team_members_environment_info.json
	•	review_team_raw.json
	8.	search those artifacts for the same claim or the numeric value
	9.	continue upstream until the earliest occurrence is found
	10.	inspect the producing node’s source_files

This gives a clear investigation trail from report output back to likely code.

What the current format is sufficient for

The current format is sufficient for:
	•	artifact-chain investigation
	•	identifying likely upstream culprit nodes
	•	narrowing debugging scope
	•	inspecting transformation paths
	•	connecting output problems to relevant code files

That is already very useful.

What the current format is not sufficient for

The current format is not sufficient for:
	•	proving which exact sentence transformation introduced a false claim
	•	attributing a sentence to a specific prompt span
	•	reconstructing exact runtime prompt context
	•	distinguishing between listed inputs and actually attended inputs
	•	auditing LLM behavior at a fine-grained level

So the format is good for investigation, but not perfect for forensic proof.

Recommended improvements

1. Give artifacts stable IDs and metadata

Example:

{
  "id": "review_plan_markdown",
  "path": "review_plan.md",
  "format": "md",
  "role": "review_output"
}

2. Add optional purpose information to inputs

Example:

{
  "from_node": "review_plan",
  "artifact_path": "review_plan.md",
  "used_for": "quality review section"
}

3. Add node kind metadata

Examples:
	•	generator
	•	validator
	•	formatter
	•	consolidator
	•	report_assembler
	•	diagnostic

This helps distinguish between nodes that are likely to introduce content versus those that mostly reformat it.

4. Add runtime provenance logs outside the DAG schema

For example:
	•	run id
	•	input artifact hashes
	•	output artifact hashes
	•	prompt inputs used
	•	source files loaded into prompt
	•	model name
	•	prompt template version
	•	temperature

This is likely more important than making the static DAG infinitely rich.

5. Add claim-level citations in generated outputs

The strongest future improvement would be to make generated markdown and report outputs carry explicit source references.

For example, each section or bullet could include:
	•	source artifact ids
	•	source node ids
	•	source spans or source field names

That would make false-claim RCA much easier.

Final assessment

The JSON format has evolved into a strong artifact-level provenance graph.

That is a major improvement over a plain DAG export.

It is now good enough for practical root cause analysis in many cases, especially when the goal is to trace a false claim back to the earliest upstream artifact and likely responsible node.

However, it is still not a full forensic provenance system.

The current format can:
	•	identify suspects
	•	trace evidence flow
	•	narrow the search space
	•	connect artifacts to code

But it still cannot fully:
	•	prove which exact transformation introduced a false sentence
	•	reconstruct the exact model context
	•	show claim-level attribution end to end

So the right conclusion is:
	•	the format is already useful and worth keeping
	•	artifact-level inputs was the right move
	•	the next frontier is runtime provenance and claim-level traceability
