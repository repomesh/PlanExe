---
name: validate-parameters
description: Use when the user wants to validate, lint, or check the JSON output of the extract-parameters stage against the schema, hard caps, percentage rules, formula-id declaration rules, and source-text cleanliness rules
---

# Validate extract-parameters JSON

## Overview

Wraps the validation system prompt at `system-prompt.txt` (next to this file) and applies it to a JSON document produced by the `extract-parameters` skill. Output is a strict JSON validation report with stable rule IDs (e.g., `F001`, `C005`, `V001`) so downstream tooling can parse violations programmatically.

## When to Use

- User asks to "validate", "check", "lint", or "audit" an extracted-parameters JSON file
- User wants to verify a JSON file conforms to the extract-parameters schema and rules before feeding it to downstream code generation
- User mentions one of the rule categories explicitly (caps, percentages, formula identifiers, source-text cleanliness)

Not for: regenerating the parameters (use `extract-parameters`), normalising or fixing the JSON, or generating Python from it. Validation is read-only and reports findings only.

## Workflow

1. **Get the input JSON path.** If the user did not provide one, ask. Do not guess.
2. **Read `system-prompt.txt`** (sibling of this SKILL.md). Treat its rules and rule IDs as authoritative.
3. **Read the JSON file** to be validated.
4. **Produce the validation report** following the exact output shape in the system prompt.
5. **Output destination.** Default: print the report JSON to the chat. If the user asks for a file, write to the path they specify. Suggested default file path: `<input-basename>.validation.json` next to the input.

## Output Shape (re-stated for emphasis — see system prompt for full detail)

```
{
  "valid": <bool>,
  "error_count": <int>,
  "warn_count": <int>,
  "violations": [ { "rule_id", "severity", "path", "message", "suggested_fix" }, ... ],
  "summary": { "counts": {...}, "rule_id_breakdown": {...} }
}
```

`valid` is true if and only if `error_count == 0`. WARN-level findings do not invalidate the document.

## Rule Categories (rule IDs in system-prompt.txt)

| Prefix | Category | Severity bias |
|---|---|---|
| `S00x` | Structural (top-level keys, required fields per entry) | ERROR |
| `C00x` | Caps (8/5/5/5, 25-word comment, 20-word source_text) | ERROR |
| `E00x` | Enums (value_type, category, modelling_priority, uncertainty) | ERROR |
| `V00x` | Unit / value (fractions in [0,1], missing_but_needed → null) | ERROR + 1 WARN |
| `I00x` | Id uniqueness and snake_case format | ERROR |
| `F00x` | Formula RHS identifier declaration, depends_on consistency | Mostly ERROR |
| `Q00x` | Triage quality (suggested_low/base/high, duplicates) | WARN |
| `T00x` | Source text cleanliness (citations, replacement chars) | WARN |

## Common Mistakes

| Mistake | Fix |
|---|---|
| Wrapping the validation report in ```` ```json ```` fences | Raw JSON only |
| Listing rules that passed | Report only rules that fired |
| Treating WARN findings as invalidating | `valid` is gated only on ERROR count |
| Treating LHS of `name = expr` as needing declaration | LHS names the output; only RHS identifiers are checked (rule F002 documents this) |
| Treating numeric literals as undeclared identifiers | Literals on the RHS are allowed and not checked |
| Treating `P(...)`, `max(...)`, `log(...)` etc. as undeclared identifiers | Common lowercase function names are allowed; their arguments are the identifiers to check |

## Reference

- System prompt (authoritative): `system-prompt.txt`
- Companion skill that produces the input: `../extract-parameters/SKILL.md`
- Example inputs for testing: `/tmp/extract-params-heatwave-v6.json`, `/tmp/extract-params-heatwave-v5.json`, etc.
