# Automated #BuildInPublic Twitter Posting from GitHub Commits

**Status:** Draft  
**Author:** Mark (Egon/VoynichLabs)  
**Date:** 2026-02-21  
**Category:** Developer Visibility / Growth

---

## Summary

Automate the posting of `#buildinpublic` tweets directly from PlanExeOrg/PlanExe GitHub commits — no human required in the loop. A cron job polls for new commits, passes the diff/message to an LLM to generate a short tweet, and posts it via the Twitter API. The goal is passive discoverability without asking Simon or Mark to manually post social updates.

---

## Problem

Neither Simon nor Mark wants to manually maintain a social media presence for PlanExe. But steady, technical #buildinpublic updates are one of the most effective organic discovery signals for developer-focused open source projects. The gap: there's genuine daily progress happening in commits, and zero signal going out to Twitter.

This proposal closes that gap with zero ongoing human effort.

---

## Concept

```
PlanExeOrg/PlanExe commits
        │
        ▼
   Cron job polls GitHub API
   (checks since last_commit_sha)
        │
        ▼
   LLM generates tweet
   (technical, not marketing fluff)
        │
        ▼
   Post via Twitter API / bird CLI
   (on designated account)
        │
        ▼
   #buildinpublic feed
```

Key constraint: **fully automated, no human approval step**. The value is in the consistency and zero-friction. If humans need to approve each tweet, it will rot.

---

## Why This Works

1. **Commits already describe what changed** — the signal is already there; this just redistributes it.
2. **#buildinpublic audience is technical** — they want to see actual work, not marketing copy.
3. **LLM-generated summaries scale** — one prompt template handles all commit types gracefully.
4. **Low risk** — if the bot posts something awkward, it's a minor inconvenience, not a crisis. The output is technical commit notes, not opinions.

---

## Architecture

### 1. GitHub API Polling

Poll the `PlanExeOrg/PlanExe` commits endpoint:

```
GET https://api.github.com/repos/PlanExeOrg/PlanExe/commits?since=<ISO_TIMESTAMP>
```

- Store last-processed commit SHA or timestamp in a state file
- On each run: fetch commits since last state, process newest-first or oldest-first (TBD)
- Skip merge commits (configurable)

### 2. State File

```
~/.planexe_twitter_bot/last_commit_sha.txt
```

Stores the SHA of the last successfully tweeted commit. On next run, fetch all commits after this SHA. Prevents duplicate tweets. If missing, use a fixed start date.

### 3. LLM Tweet Generation

Pass commit metadata to a small LLM (Claude haiku / GPT-4o-mini / Gemini Flash — cheapest available):

**Prompt template:**

```
You are generating a short #buildinpublic tweet for an open source AI planning tool.

Repository: PlanExe (AI-powered project planning)
Commit: {commit_sha[:7]}
Message: {commit_message}
Files changed: {changed_files_summary}
Author: {author_name}

Write a tweet under 240 characters. Rules:
- Technical, factual tone — describe what actually changed
- No exclamation marks, no hype, no "excited to announce"
- Include the GitHub commit URL
- End with #buildinpublic #opensource
- If the commit is a tiny fix (typo, whitespace), say so honestly

Tweet:
```

### 4. Posting

**Option A — bird CLI** (if Mark's account):

```bash
bird tweet post "<generated_tweet>"
```

**Option B — Twitter API credentials** (if Egon account or dedicated @PlanExeBot):

```bash
curl -X POST https://api.twitter.com/2/tweets \
  -H "Authorization: Bearer $TWITTER_BEARER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text": "<generated_tweet>"}'
```

**Option C — twurl / tweepy** (Python script with env-var credentials)

### 5. Cron Schedule Options

| Mode | Schedule | Tweet volume | Notes |
|------|----------|-------------|-------|
| Per-commit | On every commit push (webhook or 15-min poll) | High | Most responsive; noisy on busy days |
| Daily digest | Once/day at 09:00 UTC | 1/day max | Summarise all commits from past 24h |
| Weekly summary | Monday 09:00 UTC | 1/week | Lowest noise; best for slow periods |

**Recommendation:** Start with daily digest. Reduces noise, allows batching, and a once-per-day tweet is sustainable even on quiet days (just posts nothing if no commits).

---

## Implementation Sketch (Pseudocode)

```bash
#!/bin/bash
# planexe_twitter_bot.sh — daily digest mode

STATE_FILE="$HOME/.planexe_twitter_bot/last_run_timestamp.txt"
REPO="PlanExeOrg/PlanExe"
GH_TOKEN="$GITHUB_TOKEN"

# 1. Read last run timestamp (default: 24h ago)
if [ -f "$STATE_FILE" ]; then
  SINCE=$(cat "$STATE_FILE")
else
  SINCE=$(date -u -d "24 hours ago" +%Y-%m-%dT%H:%M:%SZ)
fi

# 2. Fetch commits since last run
COMMITS=$(curl -s \
  -H "Authorization: token $GH_TOKEN" \
  "https://api.github.com/repos/$REPO/commits?since=$SINCE&per_page=50")

COMMIT_COUNT=$(echo "$COMMITS" | jq length)

if [ "$COMMIT_COUNT" -eq 0 ]; then
  echo "No new commits. Skipping."
  exit 0
fi

# 3. Build summary for LLM
SUMMARY=$(echo "$COMMITS" | jq -r '
  .[] | "- \(.commit.message | split("\n")[0]) (\(.sha[:7]))"
' | head -10)

# 4. Call LLM API to generate tweet
TWEET=$(call_llm_api "$SUMMARY")  # abstracted — use Claude/OpenAI/Gemini

# 5. Post tweet
bird tweet post "$TWEET"
# or: python3 post_tweet.py "$TWEET"

# 6. Update state
date -u +%Y-%m-%dT%H:%M:%SZ > "$STATE_FILE"
```

**Python alternative for tweet posting:**

```python
# post_tweet.py
import os, sys, tweepy

client = tweepy.Client(
    bearer_token=os.environ["TWITTER_BEARER_TOKEN"],
    consumer_key=os.environ["TWITTER_API_KEY"],
    consumer_secret=os.environ["TWITTER_API_SECRET"],
    access_token=os.environ["TWITTER_ACCESS_TOKEN"],
    access_token_secret=os.environ["TWITTER_ACCESS_SECRET"],
)
client.create_tweet(text=sys.argv[1])
```

---

## Decisions Needed (Simon to decide)

Before this can be implemented, the following need human sign-off:

| # | Question | Options |
|---|----------|---------|
| 1 | **Which Twitter account posts?** | Mark's personal + bird CLI / Dedicated `@PlanExeAI` bot account / Egon account with Twitter API creds |
| 2 | **Posting frequency?** | Per-commit / Daily digest / Weekly summary |
| 3 | **Which commits to include?** | All commits / Merge PRs only / Non-trivial commits only (exclude docs, typo, whitespace) |
| 4 | **Content guardrails?** | Max 240 chars (hard Twitter limit) / Banned words list / Require commit URL in every tweet |
| 5 | **Hashtags to always include?** | `#buildinpublic` (definitely) / `#opensource` / `#AI` / `#python` |
| 6 | **LLM for generation?** | Claude Haiku (cheapest Anthropic) / GPT-4o-mini / Gemini Flash / Local (ollama) |
| 7 | **Where does the cron run?** | GitHub Actions (free, native) / Railway cron / VPS / Mark's server |
| 8 | **Error handling** | Silent fail (skip tweet on error) / Alert to Discord / Retry once |

---

## Suggested Starting Configuration

If Simon approves with minimal decisions:

- **Account:** Dedicated `@PlanExeBuilds` or similar (avoids mixing personal/project)
- **Frequency:** Daily digest at 09:00 UTC
- **Commits:** All commits, excluding pure merge commits
- **LLM:** Claude Haiku via Anthropic API (already used in PlanExe)
- **Cron host:** GitHub Actions (`.github/workflows/twitter-digest.yml`) — zero infra cost
- **Guardrails:** 240-char limit enforced by LLM prompt, always include `#buildinpublic`

---

## Open Questions

1. Is anyone opposed to fully automated posting with no human approval? (This is the whole point — if we add approval, it dies.)
2. Should failed LLM calls be silent-failed or reported to a Discord channel?
3. Does Simon want to review the tweet prompt template before it goes live?
4. If the project goes quiet for a week (no commits), should the bot post a "still alive" update, or just stay silent?
5. Should the bot ever reply to comments on its tweets, or post-only?

---

## What This Proposal Does NOT Include

- Working implementation code (that comes after Simon decides on account/frequency)
- Twitter API credential setup instructions (depends on which account is chosen)
- Monitoring/analytics (out of scope for v1)

---

## Next Steps (After Simon's Decisions)

1. Create Twitter account / obtain API credentials
2. Store credentials as GitHub Actions secrets (or Railway env vars)
3. Write `.github/workflows/twitter-digest.yml`
4. Write `scripts/twitter_bot.py` (or shell equivalent)
5. Test with dry-run mode (generate tweet, log to file, don't post)
6. Enable live posting

---

*This is a docs-only proposal. No code changes are included.*
