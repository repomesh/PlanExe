# Recent Changes in PlanExe

## 2026-feb-20

The user can choose what model profile (`baseline`, `premium`, `frontier`, `custom`) to use when creating a plan.
The `baseline` is focused on being cheap/fast and are low quality. 
The `premium` and `frontier` takes longer time, cost more, and yields higher quality.

The `llm_config.json` file has been moved to `llm_config/baseline.json`.

If you have tweaked your `llm_config.json`, then move it into the `llm_config/baseline.json` file.

Old layout:
- `repo/llm_config.json`

New layout:
- `repo/llm_config/baseline.json`  # This was the old `repo/llm_config.json` file.
- `repo/llm_config/premium.json`
- `repo/llm_config/frontier.json`
- `repo/llm_config/custom.json`

## 2025-dec-31

PlanExe is now using Docker.

So you no longer have to be python developer to install it on your own computer.

Over the last month I have migrated PlanExe to [Docker](https://www.docker.com/).

So that I can deploy PlanExe on [Railway](https://railway.com?referralCode=k00uaQ) and similar web providers.

Previously I have been using PythonAnywhere, and I was stuck in a dependency hell, where I couldn't add packages without breaking other packages.

Now with docker, I don't have these incompatibility issues.
However docker have its own issues.

The last version BEFORE the transition to docker is available here:
[PlanExe 2025-dec-31 release](https://github.com/PlanExeOrg/PlanExe/releases/tag/2025-dec-31)

The main branch will be docker from now on:
[PlanExe main branch](https://github.com/PlanExeOrg/PlanExe/tree/main)
