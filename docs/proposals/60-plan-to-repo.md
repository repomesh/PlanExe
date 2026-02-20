---
title: Plan-to-Repo
date: 2026-02-21
status: draft
author: Larry (via Mark Barney)  
---

# Plan-to-Repo

## Summary

Every plan that PlanExe generates automatically provisions a GitHub repository under PlanExe's own organization. No user token required. Users who want the repo in their own GitHub account can either provide a token upfront, or pay credits to trigger a native GitHub repo transfer.

This creates a frictionless experience: **generate a plan, immediately get a repo, optionally pay to own it.**

## Why

**Persistent Starting Point:** AI agents (and humans) need a structured, version-controlled home for each plan. Without a repo, agents have no shared baseline to fork from, improve, or build upon.

**Zero Friction:** By default, PlanExe creates the repo under its own org. No user needs to provide a GitHub token—plan generation completes instantly with a public repo link.

**Natural Monetization:** Plan generation is the hook (free). Repo ownership is the upsell (pay credits). This is clean and native—GitHub's repo transfer feature preserves full history, issues, and stars.

**Execution Continuity:** The plan repo IS the plan's home. Future agents can fork it, submit PRs with improvements, execution results, or modifications. It creates a natural workflow:
- Agent A generates plan → PlanExe creates repo (under PlanExe org)
- User gets link, can fork or request transfer to own account (paid)
- Agent B picks up the repo → builds website → PRs changes
- Agent C picks up the updated repo → executes plan → PRs execution results
- Humans review and merge improvements

**Traceability:** Every modification to the plan is version-controlled, auditable, and reversible.

## What Lands in the Repo

1. **Plan Artifact**
   - Generated plan in Markdown or JSON format
   - Timestamped and signed by the generating agent

2. **README**
   - Summary of the plan's purpose and goals
   - Next steps and immediate actions
   - Links to related documents or repos

3. **Folder Structure**
   - `/website` — for web-based presentation, design, or deployment files
   - `/execution` — for execution scripts, logs, and progress tracking
   - `/docs` — for detailed specifications, requirements, and notes

4. **Metadata**
   - `.planexe.yml` or similar config: plan ID, generator, creation timestamp, owner

## Default Flow (No Token Required)

1. User generates a plan in PlanExe
2. PlanExe immediately creates a public GitHub repo under its own org (`github.com/PlanExeOrg/plan-{slug}-{timestamp}`)
3. Plan artifact, README, and folder scaffold pushed to the repo in an initial commit
4. User receives a link to the repo (view, fork, or clone)
5. **Plan generation complete** — no GitHub account required

## Optional Flow: User Token (Repo Created Directly in User's Account)

For users who want the repo in their own GitHub account from the start:

1. User provides their GitHub token during or after plan generation
2. PlanExe creates the repo directly under the user's account
3. Same artifact, README, and scaffold pushed
4. User owns the repo immediately—no transfer needed

**Trade-off:** Slightly slower (requires token + GitHub API call), but immediate ownership.

## Monetization: Repo Transfer (Premium Feature)

Users who started with a PlanExe-owned repo can **pay credits to trigger a transfer**:

1. User selects plan repo from their PlanExe dashboard
2. Chooses "Transfer to my GitHub account"
3. Pays X credits (tiered: basic, pro, enterprise)
4. PlanExe triggers GitHub's native repo transfer API
5. Repo moves from `PlanExeOrg/{repo}` → `{UserOrg}/{repo}`
6. **Full history, stars, issues, and collaborators preserved**
7. Transfer completes in seconds

**Why This Works:**
- **GitHub native:** Repo transfers are built-in; they preserve everything
- **Instant:** No data migration, no API polling
- **Clean upsell:** Free plan → free repo → paid ownership
- **No friction:** User doesn't need a token upfront
- **Trust builder:** User sees the plan works before paying to own it

## API Design Sketch

### Endpoint 1: Create Repo on Plan Completion (Default - PlanExe Org)

When a plan is generated, PlanExe triggers:

```
POST /api/v1/plans/:planId/create-repo
```

**Payload:**
```json
{
  "planId": "plan-uuid",
  "planTitle": "Website Redesign Q1 2026",
  "planContent": "...",
  "planFormat": "markdown",
  "repoName": "plan-website-redesign-q1-2026",
  "repoDescription": "Auto-generated plan repo",
  "isPrivate": false,
  "githubToken": null,
  "ownerOrg": "PlanExeOrg"
}
```

**Actions:**
1. Call GitHub API (`POST /orgs/PlanExeOrg/repos`) using PlanExe service account token
2. Initialize repo with plan files (plan artifact, README, folder scaffold)
3. Create initial commit with plan content
4. Return repo URL and clone instructions
5. Store repo URL in PlanExe database (linked to `planId`, flag as "PlanExe-owned")

---

### Endpoint 2: Create Repo in User's Account (Optional Token)

If user provides a GitHub token:

```
POST /api/v1/plans/:planId/create-repo
```

**Payload:**
```json
{
  "planId": "plan-uuid",
  "planTitle": "Website Redesign Q1 2026",
  "planContent": "...",
  "planFormat": "markdown",
  "repoName": "plan-website-redesign-q1-2026",
  "repoDescription": "Auto-generated plan repo",
  "isPrivate": false,
  "githubToken": "ghp_...",
  "ownerOrg": null
}
```

**Actions:**
1. Validate token (ensure `public_repo` or `repo` scope)
2. Call GitHub API (`POST /user/repos` or `/orgs/{org}/repos` depending on token scope)
3. Initialize repo with same plan files and commit
4. Return repo URL and clone instructions
5. Store repo URL in PlanExe database (linked to `planId`, flag as "user-owned")

---

### Endpoint 3: Transfer Repo to User's Account (Credit Purchase)

When user wants to take ownership of a PlanExe-owned repo:

```
POST /api/v1/plans/:planId/transfer-repo
```

**Payload:**
```json
{
  "planId": "plan-uuid",
  "targetGitHubOrg": "user-org-or-username",
  "creditsToDeduct": 50,
  "transferReason": "User purchased repo ownership"
}
```

**Actions:**
1. Verify user has sufficient credits (deduct before transfer to avoid partial state)
2. Retrieve current repo details from PlanExe database
3. Call GitHub API (`POST /repos/PlanExeOrg/{repo}/transfer`) with target owner
4. Wait for transfer completion (typically instant)
5. Update PlanExe database: mark repo as "transferred to user", store new URL
6. Return success response with new repo URL
7. Send user notification: "Repo successfully transferred!"

---

## Auth & Token Management

**Default Case (No Token):**
- PlanExe uses its own service account GitHub token (stored securely)
- User provides zero credentials
- Fastest, most frictionless experience

**User Token Case (Optional):**
- User supplies personal GitHub token in settings or per-request
- Token scoped to `public_repo` or `repo` (validate before use)
- Store token securely (encrypted, with user consent)
- Delete token after repo creation (no need to retain it for default flow)

**Repo Transfer Case:**
- No new token needed (PlanExe owns the repo, so it has transfer rights)
- User pays credits; transfer is authenticated via PlanExe account
- GitHub API handles the transfer; no user token required

## Scenarios

### Scenario 1: Quick Plan + Free Repo (Default)
1. User generates a plan
2. PlanExe repo created instantly under `PlanExeOrg`
3. User forks it to their own account (free, native GitHub fork)
4. Starts working immediately
5. Later, can pay credits to officially transfer the original repo to their account

### Scenario 2: Plan + Immediate User Ownership (Optional Token)
1. User provides GitHub token during plan generation
2. Repo created directly in user's account
3. User owns it immediately
4. No transfer needed
5. No credits required

### Scenario 3: Plan → Free Repo → Paid Transfer
1. User generates plan
2. PlanExe creates repo under `PlanExeOrg` (free)
3. User forks it and starts work
4. Repo gains stars, issues, PRs, collaborators
5. User pays credits to transfer the original repo to their account
6. GitHub's native transfer preserves all history and metadata
7. User now officially owns the repo

## Future: Agent Workflow

```
┌─────────────────┐
│ PlanExe         │ Generates plan
│ generates plan  │ → creates repo under PlanExeOrg
└────────┬────────┘
         │
         v
    [plan repo on GitHub (PlanExeOrg)]
         │
    ┌────┴────┬──────────┬─────────┐
    │          │          │         │
    v          v          v         v
  [Agent A]  [Agent B]  [Agent C]  [User]
  (fork)     (fork)     (fork)     (owns)
    │          │          │         │
    │          │          │    Transfer to own account?
    │          │          │         │ (pay credits)
    │          v          v         v
    │       Build      Execute   [user-org/plan-repo]
    │       website    plan
    │         & PR     & PR
    │         │         │
    └─────────┴─────────┬──────────┘
                        v
              [Updated Plan Repo]
              (versioned, auditable,
               improvement history)
```

## Implementation Considerations

1. **Error Handling**
   - If GitHub API fails, gracefully degrade (log error, notify user, allow manual repo creation)
   - For transfers, ensure credits are not deducted if transfer fails

2. **Rate Limiting**
   - GitHub API has rate limits; queue or batch repo creation if needed
   - Provide feedback on quota status to user

3. **Naming Strategy**
   - Repo name: `plan-{slugified-title}-{timestamp}` or similar
   - Ensure uniqueness (check for existing repos under PlanExeOrg)
   - User can override repo name if desired

4. **Initial Commit Message**
   - `Initial commit: Auto-generated plan by PlanExe`
   - Include plan metadata and generation timestamp
   - Sign commit with PlanExe service account

5. **UI/UX**
   - Add "Transfer to Your Account" button on plan view (if PlanExe-owned)
   - Show credit cost before confirming transfer
   - Provide clear status: "Owned by PlanExeOrg" vs "Your account"
   - Link to transferred repo once complete

6. **Future Integrations**
   - Link to PlanExe UI: clickable "View Repo" button on generated plans
   - Webhooks: sync plan updates back to PlanExe if repo is modified
   - Agent SDK: provide helper function for agents to fork and submit PRs

## Success Criteria

- [x] Plan generation automatically creates repo under PlanExeOrg (no user token required)
- [x] Repo contains plan artifact, README, and scaffold folders
- [x] User can optionally provide GitHub token for direct user-account ownership
- [x] Repo is public and discoverable
- [x] User can fork repo to their own account (free, native GitHub)
- [x] User can pay credits to transfer original repo to their account
- [x] GitHub repo transfer API preserves history, stars, issues
- [x] Agents can fork, branch, and submit PRs to plan repo
- [x] Plan repo URL is accessible and linked in PlanExe UI
- [x] Version history is preserved and auditable
- [x] Transfer UI shows cost and confirmation before charging credits

## Open Questions

1. What credit tier for repo transfer? (Basic: 10 credits, Pro: 50 credits, Enterprise: custom?)
2. Should users be able to transfer repos they created with their own token back to PlanExeOrg? (Unlikely, but possible resale/donation flow)
3. Should we auto-create issues/labels for tracking plan execution?
4. Should plan updates trigger repo commits/tags?
5. How do we handle plan deletion (repo archival or full deletion)?
6. Should we support GitLab, Gitea, or other Git hosting platforms in the future?
