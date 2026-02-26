# Proposal 74 — Rename `TaskItem` to `PlanItem`

## Status

Draft

## Relationship to Proposal 73

Proposal 73 covers renaming the public MCP tool names (e.g. `task_create` → `plan_create`).
That proposal explicitly deferred renaming the internal `TaskItem` model. This proposal addresses that deferred work.

---

## Problem

The internal SQLAlchemy model is named `TaskItem` (defined in `database_api/model_taskitem.py`). The associated state enum is `TaskState`. Both names carry `Task` — the same word that:

- Clashes with the MCP protocol's own "task" concept (addressed in proposal 73 for public tool names).
- Clashes with Claude Code's built-in `Task` tool (visible to any agent working in this codebase).
- Adds confusion for contributors: "TaskItem" sounds like a to-do list item, not a long-running strategic plan generation run.

`PlanItem` is the natural equivalent: each row represents one invocation of the PlanExe planning pipeline — i.e., one *plan* being generated.

---

## Goals

1. Rename the Python class `TaskItem` → `PlanItem` throughout the codebase.
2. Rename the Python enum `TaskState` → `PlanState`.
3. Rename the source file `model_taskitem.py` → `model_planitem.py` and the test file accordingly.
4. Keep the production **database table name unchanged** (`task_item`) so that no database migration is required.
5. Update all imports, usages, docstrings, and documentation.

## Non-goals

- Renaming the `task_id` UUID field exposed in MCP API responses (covered as a separate decision in proposal 73).
- Changing any database column names or table structure.
- Renaming the `task_id` column in `model_token_metrics.py` or `model_worker.py` (those are foreign-key column names in the database; changing them would require a migration).

---

## Critical: Database Table Name

`TaskItem` has **no explicit `__tablename__`** in its class definition. SQLAlchemy derives the table name automatically by converting the class name to snake_case:

- `TaskItem` → table `task_item`
- `PlanItem` → table `plan_item` ← **wrong; this would break all queries against the live database**

Therefore, when the class is renamed to `PlanItem`, an explicit `__tablename__` must be added at the same time:

```python
class PlanItem(db.Model):
    __tablename__ = "task_item"   # ← keep existing DB table name
    ...
```

This single line preserves full backward compatibility with the existing database — no migration script needed.

---

## Scope of Changes

### Core model file

| File | Change |
|------|--------|
| `database_api/model_taskitem.py` → rename to `model_planitem.py` | Rename file; rename class `TaskItem` → `PlanItem`; add `__tablename__ = "task_item"`; rename enum `TaskState` → `PlanState`; rename listener function `_sanitize_taskitem_fields` → `_sanitize_planitem_fields`; update all internal references |

### Files that import `TaskItem` or `TaskState`

| File | Change |
|------|--------|
| `mcp_cloud/app.py` | Update import (`from database_api.model_planitem import PlanItem, PlanState`); rename `TaskItem` → `PlanItem`, `TaskState` → `PlanState` throughout; rename helper functions `find_task_by_task_id` → `find_plan_by_task_id` (or keep as-is since `task_id` is the UUID field name) |
| `mcp_cloud/tests/test_task_create_tool.py` | Update import; rename `TaskItem` mock |
| `mcp_cloud/tests/test_task_file_info_tool.py` | Update import; rename `TaskState` → `PlanState` |
| `mcp_cloud/tests/test_task_status_tool.py` | Update import; rename `TaskState` → `PlanState` |
| `frontend_multi_user/src/app.py` | Update import; rename `TaskItem` → `PlanItem`, `TaskState` → `PlanState`; rename `TaskItemView` → `PlanItemView`; update all method signatures and variable names |
| `worker_plan_database/app.py` | Update import; rename `TaskItem` → `PlanItem`, `TaskState` → `PlanState` throughout |

### Test file

| File | Change |
|------|--------|
| `database_api/tests/test_taskitem_model.py` → rename to `test_planitem_model.py` | Rename file; update import from `model_planitem`; rename `TaskItem` → `PlanItem`, `TaskState` → `PlanState` in all tests |

### Documentation files

| File | Change |
|------|--------|
| `database_api/README.md` | Update model name and import example |
| `frontend_multi_user/AGENTS.md` | Update `TaskItem` references |
| `worker_plan_database/AGENTS.md` | Update `TaskItem` references |
| `mcp_cloud/AGENTS.md` | Update `TaskItem ↔ MCP task` mapping description |
| `mcp_cloud/README.md` | Update `TaskItem` references |
| `worker_plan_database/README.md` | Update `TaskItem` references |
| `docs/proposals/55-taskitem-activity-log-decomposition-and-secure-downloads.md` | Historical — leave filename as-is; prose can be left unchanged (it is a completed proposal) |

### Comment-only references (no import needed)

| File | Change |
|------|--------|
| `worker_plan/worker_plan_internal/llm_util/token_instrumentation.py` | Update comments referencing `TaskItem.id` → `PlanItem.id` |
| `worker_plan/worker_plan_internal/llm_util/token_metrics_store.py` | Update comments |
| `database_api/model_token_metrics.py` | Update comments; the `task_id` column name itself stays unchanged |
| `database_api/model_worker.py` | Update comments; the `current_task_id` column name itself stays unchanged |

---

## Step-by-Step Procedure

### Step 1 — Create a feature branch

```bash
git checkout main
git pull
git checkout -b rename-taskitem-to-planitem
```

### Step 2 — Rename and update `model_taskitem.py`

1. Rename the file:
   ```bash
   git mv database_api/model_taskitem.py database_api/model_planitem.py
   ```

2. Inside the new `model_planitem.py`, make the following changes:

   a. Rename the enum:
   ```python
   # Before
   class TaskState(enum.Enum):
   # After
   class PlanState(enum.Enum):
   ```

   b. Rename the class and add the explicit table name:
   ```python
   # Before
   class TaskItem(db.Model):
   # After
   class PlanItem(db.Model):
       __tablename__ = "task_item"
   ```

   c. Update all internal references to `TaskItem` and `TaskState` within the file (the `demo_items` method, event listener, and the `_sanitize_taskitem_fields` function):
   ```python
   # Before
   @classmethod
   def demo_items(cls) -> list['TaskItem']:
       task1 = TaskItem(state=TaskState.failed, ...)
       ...

   @event.listens_for(TaskItem, "before_insert")
   @event.listens_for(TaskItem, "before_update")
   def _sanitize_taskitem_fields(_mapper, _connection, target):

   # After
   @classmethod
   def demo_items(cls) -> list['PlanItem']:
       task1 = PlanItem(state=PlanState.failed, ...)
       ...

   @event.listens_for(PlanItem, "before_insert")
   @event.listens_for(PlanItem, "before_update")
   def _sanitize_planitem_fields(_mapper, _connection, target):
   ```

### Step 3 — Rename and update the test file

```bash
git mv database_api/tests/test_taskitem_model.py database_api/tests/test_planitem_model.py
```

Inside `test_planitem_model.py`:
- Update the import: `from database_api.model_planitem import PlanItem, PlanState`
- Replace `TaskItem(` → `PlanItem(`, `TaskState.` → `PlanState.` throughout.

### Step 4 — Update `mcp_cloud/app.py`

1. Update the import line:
   ```python
   # Before
   from database_api.model_taskitem import TaskItem, TaskState
   # After
   from database_api.model_planitem import PlanItem, PlanState
   ```
2. Replace all `TaskItem` → `PlanItem` and `TaskState` → `PlanState` in the file body.
3. Optionally rename internal helper functions for clarity (e.g. `find_task_by_task_id` → `find_plan_by_task_id`). Note: the `task_id` argument name itself should remain `task_id` since that is the UUID field name in API payloads.

### Step 5 — Update `mcp_cloud` test files

For each of:
- `mcp_cloud/tests/test_task_create_tool.py`
- `mcp_cloud/tests/test_task_file_info_tool.py`
- `mcp_cloud/tests/test_task_status_tool.py`

Update the import from `model_taskitem` to `model_planitem`; rename `TaskItem` → `PlanItem`, `TaskState` → `PlanState`.

### Step 6 — Update `frontend_multi_user/src/app.py`

1. Update the import.
2. Replace `TaskItem` → `PlanItem` and `TaskState` → `PlanState` throughout (~30 occurrences).
3. Rename the admin view class:
   ```python
   # Before
   class TaskItemView(AdminOnlyModelView):
   # After
   class PlanItemView(AdminOnlyModelView):
   ```
4. Update the `add_view` call:
   ```python
   # Before
   self.admin.add_view(TaskItemView(model=TaskItem, ...))
   # After
   self.admin.add_view(PlanItemView(model=PlanItem, ...))
   ```
5. Update all method signatures that type-hint `task: TaskItem` → `task: PlanItem`.

### Step 7 — Update `worker_plan_database/app.py`

1. Update the import.
2. Replace `TaskItem` → `PlanItem` and `TaskState` → `PlanState` throughout.

### Step 8 — Update comment-only references

For each of:
- `worker_plan/worker_plan_internal/llm_util/token_instrumentation.py`
- `worker_plan/worker_plan_internal/llm_util/token_metrics_store.py`
- `database_api/model_token_metrics.py`
- `database_api/model_worker.py`

Update prose comments that mention `TaskItem` → `PlanItem`. Do **not** rename database column names (`task_id`, `current_task_id`).

### Step 9 — Update documentation files

For each documentation file in the scope above, replace `TaskItem` → `PlanItem` and `TaskState` → `PlanState` in prose. The `task_id` UUID identifier should remain unchanged.

A grep to check completeness before committing:

```bash
grep -rn "TaskItem\|TaskState\|model_taskitem\|test_taskitem" \
  database_api/ mcp_cloud/ frontend_multi_user/ worker_plan_database/ \
  worker_plan/ docs/ skills/ README.md
```

The only acceptable remaining hits after this step are:
- The historical proposal file `docs/proposals/55-taskitem-activity-log-decomposition-and-secure-downloads.md` (filename and completed-proposal prose — leave unchanged).
- Database column names `task_id` and `current_task_id` in model files and comments (intentionally kept).

### Step 10 — Verify `__tablename__` is set

Before committing, confirm the class definition in `model_planitem.py` contains:

```python
class PlanItem(db.Model):
    __tablename__ = "task_item"
```

This is the most safety-critical line in the entire rename. Without it, every ORM query will target a non-existent `plan_item` table and fail at runtime.

### Step 11 — Run the test suite

```bash
python -m pytest database_api/tests/ -v
python -m pytest mcp_cloud/tests/ -v
python -m pytest frontend_multi_user/tests/ -v
```

All tests must pass.

### Step 12 — Start the application and verify the admin panel

1. Start the full stack locally (database + mcp_cloud + frontend_multi_user).
2. Open the admin panel and confirm the `task_item` table is visible and queryable via `PlanItemView`.
3. Create a test plan run via `plan_create` (after proposal 73 lands) or via the existing UI.
4. Verify the row appears in the admin view under `PlanItem`.

### Step 13 — Open a pull request

Note in the PR summary:
- `__tablename__ = "task_item"` is set — no database migration required.
- `task_id` column names and API field names are intentionally unchanged.
- This PR should land **after** (or together with) proposal 73 to keep naming consistent.

---

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Missing `__tablename__` causes all queries to hit a non-existent `plan_item` table | Step 10 is a mandatory pre-commit check; verified by the test suite and the smoke test in Step 12 |
| Import path `database_api.model_taskitem` still used somewhere | The grep in Step 9 will surface any remaining occurrences |
| `model_taskitem` string appears in string literals (e.g., Alembic migration comments) | Grep covers string literals too; Alembic migration files are not present in this repo (ORM-managed schema), so no migration files to update |
| `TaskState` values (`.pending`, `.processing`, `.completed`, `.failed`) are stored in the database as strings; renaming the enum class does not affect stored values | `PlanState.pending` still stores the string `"pending"` — enum *class name* is not persisted. Safe to rename. |
| Frontend admin panel URL path for TaskItemView changes | Flask-Admin derives the URL endpoint from the class name by default. `TaskItemView` → `PlanItemView` changes the admin endpoint URL (e.g. `/admin/taskitemview/` → `/admin/planitemview/`). Any hardcoded bookmarks or links to the old URL will break. Update any such links. |

---

## Acceptance Criteria

- [ ] `database_api/model_planitem.py` exists; `model_taskitem.py` is deleted.
- [ ] `PlanItem` class contains `__tablename__ = "task_item"`.
- [ ] `TaskState` is replaced by `PlanState` in all Python files.
- [ ] No remaining `TaskItem` or `TaskState` references in non-historical source files and docs (verified by grep).
- [ ] `task_id` field names in API schemas and database column definitions are unchanged.
- [ ] All tests pass.
- [ ] Application starts, the admin panel shows the `PlanItem` view, and existing database rows are readable.
