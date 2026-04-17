# Worker Plan API

Lightweight shared code used by `worker_plan_internal`, `worker_plan_database`, and `frontend_multi_user`.

## Why keep this lightweight?

Each service that imports `worker_plan_api` has its own set of dependencies. Some of these are already incompatible with each other (e.g., `worker_plan_internal` vs `frontend_multi_user`). Adding dependencies here forces every consumer to pull them in, increasing the risk of conflicts.

**Rule:** Avoid 3rd party dependencies in `worker_plan_api`. If you need external packages, put that code in the service that needs it, not here.