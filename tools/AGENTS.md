# Agent instructions for tools

Developer and maintenance utilities. These scripts are run manually, not as part of CI or the pipeline.

## cleanup_branches.py

Finds and removes stale git branches that belong to closed or merged GitHub PRs.

### When to use

When the user asks to clean up old branches, remove stale PR branches, or tidy up the repo.

### Two-phase workflow

**Phase 1 — Scan.** Generate a JSONL file listing stale branches for the user to inspect before anything is deleted.

```bash
python3 tools/cleanup_branches.py scan -o /tmp/stale_branches.jsonl
```

Each JSONL line contains: `branch`, `pr_number`, `pr_state` (CLOSED/MERGED), `pr_title`, `local` (bool), `remote` (bool).

Show the user the contents and wait for confirmation before proceeding.

**Phase 2 — Delete.** After the user confirms the JSONL looks correct, delete the branches.

```bash
python3 tools/cleanup_branches.py delete /tmp/stale_branches.jsonl
```

The script prints a summary and prompts `[y/N]` before deleting. Pass `-y` to skip the prompt only if the user has already confirmed.

After deletion, run `git remote prune origin` to clean up any stale tracking refs.

### Safety

- Protected branches (`main`, `railway-production`) are always excluded regardless of JSONL contents.
- Only branches with an associated closed or merged PR are included. Orphan branches (no PR) are intentionally skipped.
- The `--limit` flag (default 200) controls how many PRs per state are fetched. Increase if the repo has a long PR history.

### Requirements

- `gh` CLI, authenticated with repo access
- `git` with the target repo as the working directory
