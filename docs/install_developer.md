# Installing PlanExe for developers

I assume that you are a python developer.

You need several open terminals to do development on this project.

### Clone repo

```bash
git clone https://github.com/PlanExeOrg/PlanExe.git
```

### Prepare `.env` file

Create a `.env` file from the `.env.developer-example` file.

Update `OPENROUTER_API_KEY` with your open router api key.

### `worker_plan`

In a new terminal: 
Follow the [worker_plan](developer/worker_plan.md) instructions.

### `database_postgres`

In a new terminal: 
Follow the [database_postgres](developer/database_postgres.md) instructions.

### `worker_plan_database`

In a new terminal: 
Follow the [worker_plan_database](developer/worker_plan_database.md) instructions.

### `frontend_multi_user`

In a new terminal: 
Follow the [frontend_multi_user](developer/frontend_multi_user.md) instructions.

### Tests

In a new terminal: 
Run the tests to ensure that the project works correctly.
```
PROMPT> python test.py
snip lots of output snip
Ran 117 tests in 0.059s

OK
```

`test.py` runs in the project venv and now enforces cross-service dependencies for MCP tests.
If modules like `mcp` are missing, it will try to install from:
`mcp_cloud/requirements.txt`.
If auto-install fails (for example due network restrictions), install manually in the active venv:
```bash
python -m pip install -r mcp_cloud/requirements.txt
```

### Now PlanExe have been installed.
