# Tools

Developer and maintenance utilities for the PlanExe project.

## cleanup_branches.py

Cross-references GitHub closed/merged PRs with local and remote git branches to find stale branches that can be removed.

**Requirements:** `gh` CLI (authenticated), `git`

**Usage:**

```bash
# Phase 1: Scan and output JSONL for review
python3 tools/cleanup_branches.py scan -o stale.jsonl

# Inspect the results
cat stale.jsonl | python3 -m json.tool --json-lines

# Phase 2: Delete confirmed branches (with confirmation prompt)
python3 tools/cleanup_branches.py delete stale.jsonl

# Or skip the confirmation prompt
python3 tools/cleanup_branches.py delete stale.jsonl -y
```

Protected branches (`main`, `railway-production`) are always excluded.
