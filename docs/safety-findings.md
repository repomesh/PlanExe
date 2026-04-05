# Safety Findings

## Finding

`Structured Output` bypasses safety guardrails in tested models. When asked to populate a JSON schema, tested models comply even when the context explicitly references murder, assault, and exploitation.

This is an informal findings note, not a comprehensive benchmark or exhaustive evaluation of all models.

The model sees the full plan. It is not being tricked. In the example below, the query contains 45,000 characters including
"amendments to laws against murder", "less lethal formats", and "exploitation of vulnerable individuals".
The model responds with a professionally formatted work breakdown structure.

I tested a substantial set of widely used models and found repeated willingness to generate operational plans for harmful goals.
I did not exhaustively test all available models, and these results should not be read as a universal claim about every model.

Tested across models from Google, OpenAI, Alibaba, DeepSeek, Meta, and Anthropic — cloud APIs and local models. Many of them comply.
Each generated plan's zip file contains metadata showing which model produced each step.
In 2025 Q3, I reported these concerns and received dismissive responses, including `not fixable` from Google and `slop` from AI safety researchers.

Here is an example of a disturbing plan made with PlanExe:
https://planexe.org/20250816_squid_game_usa_report.html

## More red teaming examples

See `simple_plan_prompts.jsonl` for more prompts where the LLMs should have refused to answer.

The corresponding plans are available here
https://planexe.org/examples/

If you want to see the intermediary files, then see the zip files in this repo:
https://github.com/PlanExeOrg/PlanExe-web
These intermediary files show what model generated what output.

## Verdict

In 2026, the ecosystem is moving toward more autonomous execution, which makes this failure mode more concerning. Especially OpenClaw freaks me out.

It cost around 36 cents and 15 minutes generating an operational plan for anything from harmless to harmful.
So far I have received no meaningful engagement on this finding, only dismissive reactions such as being told it is `slop`.
