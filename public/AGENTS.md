# public agent instructions

Scope: static files under `public/`.

## Purpose of `llms.txt`
- `llms.txt` is PlanExe's AI-agent discovery metadata.
- It explains what PlanExe does, how agents connect, and which endpoints/tools exist.
- This file is product-level metadata, not service-specific metadata.

## Canonical source
- Canonical file path:
  `public/llms.txt`
- Keep exactly one source-of-truth file for this content.
- Do not add near-duplicate copies such as:
  - `mcp_cloud/llms.txt`
  - `mcp_cloud/llm.txt`
  - `docs/llms.txt`

## Intended public endpoints
- `https://home.planexe.org/llms.txt`
- `https://mcp.planexe.org/llms.txt`

Legacy compatibility endpoint:
- `https://mcp.planexe.org/llm.txt`
- This should remain an alias redirect to:
  `https://mcp.planexe.org/llms.txt`

## Implementation intent
- `mcp_cloud` should serve `/llms.txt` from the canonical file in `public/`.
- If container packaging needs it, copy the canonical file at build time.
- Do not fork content per service unless explicitly required.

## Change policy
- When updating agent-discovery text, edit only:
  `public/llms.txt`
- Then verify both endpoints still serve the same content:
  - `https://home.planexe.org/llms.txt`
  - `https://mcp.planexe.org/llms.txt`
