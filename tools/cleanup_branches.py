#!/usr/bin/env python3
"""Cross-reference GitHub PRs with local/remote git branches to find stale branches.

Phase 1:  python3 cleanup_branches.py scan -o stale.jsonl
Phase 2:  python3 cleanup_branches.py delete stale.jsonl
"""

import argparse
import json
import subprocess
import sys


PROTECTED_BRANCHES = {"main", "railway-production"}


def run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout


def get_closed_and_merged_prs(limit: int = 200) -> list[dict]:
    """Fetch closed + merged PRs from GitHub via gh CLI."""
    prs = []
    for state in ("closed", "merged"):
        raw = run([
            "gh", "pr", "list",
            "--state", state,
            "--limit", str(limit),
            "--json", "number,title,headRefName,state",
        ])
        prs.extend(json.loads(raw))
    return prs


def get_local_branches() -> set[str]:
    raw = run(["git", "branch", "--format", "%(refname:short)"])
    return {b.strip() for b in raw.splitlines() if b.strip()}


def get_remote_branches(remote: str = "origin") -> set[str]:
    raw = run(["git", "branch", "-r", "--format", "%(refname:short)"])
    prefix = f"{remote}/"
    return {
        b.strip().removeprefix(prefix)
        for b in raw.splitlines()
        if b.strip().startswith(prefix)
    }


def scan(args: argparse.Namespace) -> None:
    prs = get_closed_and_merged_prs(limit=args.limit)
    local = get_local_branches()
    remote = get_remote_branches()

    # Group PRs by branch — keep the highest PR number per branch
    branch_to_pr: dict[str, dict] = {}
    for pr in prs:
        branch = pr["headRefName"]
        if branch in PROTECTED_BRANCHES:
            continue
        existing = branch_to_pr.get(branch)
        if existing is None or pr["number"] > existing["number"]:
            branch_to_pr[branch] = pr

    results = []
    for branch, pr in sorted(branch_to_pr.items()):
        in_local = branch in local
        in_remote = branch in remote
        if not in_local and not in_remote:
            continue  # branch already cleaned up
        results.append({
            "branch": branch,
            "pr_number": pr["number"],
            "pr_state": pr["state"],
            "pr_title": pr["title"],
            "local": in_local,
            "remote": in_remote,
        })

    out = sys.stdout if args.output is None else open(args.output, "w")
    try:
        for entry in results:
            out.write(json.dumps(entry) + "\n")
    finally:
        if out is not sys.stdout:
            out.close()

    dest = args.output or "stdout"
    print(f"Found {len(results)} stale branches → {dest}", file=sys.stderr)


def delete(args: argparse.Namespace) -> None:
    with open(args.file) as f:
        entries = [json.loads(line) for line in f if line.strip()]

    if not entries:
        print("Nothing to delete.", file=sys.stderr)
        return

    print(f"Will delete {len(entries)} branches:", file=sys.stderr)
    for e in entries:
        where = []
        if e["local"]:
            where.append("local")
        if e["remote"]:
            where.append("remote")
        print(f"  {e['branch']}  ({', '.join(where)})  PR #{e['pr_number']} {e['pr_state']}", file=sys.stderr)

    if not args.yes:
        answer = input("\nProceed? [y/N] ")
        if answer.lower() != "y":
            print("Aborted.", file=sys.stderr)
            return

    for e in entries:
        branch = e["branch"]
        if branch in PROTECTED_BRANCHES:
            print(f"  SKIP (protected): {branch}", file=sys.stderr)
            continue

        if e["local"]:
            try:
                run(["git", "branch", "-D", branch])
                print(f"  Deleted local:  {branch}", file=sys.stderr)
            except subprocess.CalledProcessError as exc:
                print(f"  FAILED local:  {branch}  ({exc.stderr.strip()})", file=sys.stderr)

        if e["remote"]:
            try:
                run(["git", "push", "origin", "--delete", branch])
                print(f"  Deleted remote: {branch}", file=sys.stderr)
            except subprocess.CalledProcessError as exc:
                print(f"  FAILED remote: {branch}  ({exc.stderr.strip()})", file=sys.stderr)

    print("Done.", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="Scan for stale branches and output JSONL")
    p_scan.add_argument("-o", "--output", help="Output file (default: stdout)")
    p_scan.add_argument("--limit", type=int, default=200, help="Max PRs to fetch per state (default: 200)")
    p_scan.set_defaults(func=scan)

    p_del = sub.add_parser("delete", help="Delete branches listed in a JSONL file")
    p_del.add_argument("file", help="JSONL file from scan")
    p_del.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt")
    p_del.set_defaults(func=delete)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
