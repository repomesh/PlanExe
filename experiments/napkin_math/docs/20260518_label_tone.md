# Slideshow label tone recommendations

## Context

The current slideshow uses verdict labels such as `DOOM`, `FRAGILE`, `MARGINAL`, and `ROBUST` to summarize plan risk. These labels work well for internal debugging and stress testing because they are memorable, short, and emotionally clear.

However, `DOOM` in particular is too theatrical for some audiences. It can make the deck feel less serious, even when the underlying analysis is rigorous. The issue is not the model or the verdict logic; the issue is presentation tone.

The same numerical bands can be preserved while changing only the displayed labels.

## Problem with current labels

### `DOOM`

`DOOM` is useful internally because it communicates “this plan has a fatal blocker.” But it has several problems in a stakeholder-facing deck:

- It sounds dramatic rather than analytical.
- It may read as hostile toward the plan author.
- It can distract from the actual gate-level evidence.
- It may make the slideshow feel like a game/debug interface rather than a review artifact.
- It compresses nuance: one catastrophic gate and five catastrophic gates both sound equally doomed.

### `FRAGILE`

`FRAGILE` is better than `DOOM`, but still slightly informal. It is understandable, but it sounds more like a metaphor than a formal assessment category.

### `MARGINAL`

`MARGINAL` is acceptable. It is a normal analytical term and maps well to “passes sometimes, but not reliably.”

### `ROBUST`

`ROBUST` is good. It is clear, technical, and positive without sounding like a guarantee.

## Recommended label modes

The generator should support at least two label modes:

```text
internal
external
```

The underlying risk bands should remain unchanged. Only the display labels should change.

## Recommended mapping

| Internal label | External label | Meaning | Pass-rate band |
|---|---|---|---|
| `DOOM` | `Critical` | Gate rarely passes; plan has a severe blocker | `<20%` |
| `FRAGILE` | `High risk` | Gate passes sometimes, but failure is likely | `20–50%` |
| `MARGINAL` | `Watchlist` | Gate is near viability but not reliable | `50–80%` |
| `ROBUST` | `Resilient` | Gate usually passes under current bounds | `≥80%` |

Alternative for `ROBUST`: keep `Robust`. This may be better than `Resilient` if the deck should preserve more technical language.

Preferred external mapping:

```json
{
  "DOOM": "Critical",
  "FRAGILE": "High risk",
  "MARGINAL": "Watchlist",
  "ROBUST": "Robust"
}
```

## Why this mapping

### `Critical` instead of `DOOM`

`Critical` keeps the severity without the theatrical tone. It is common in risk management, incident response, security, QA, and project reviews.

It still tells the reader: this is not a minor issue.

### `High risk` instead of `FRAGILE`

`High risk` is plain and stakeholder-friendly. It directly names the assessment rather than using metaphor.

### `Watchlist` instead of `MARGINAL`

`Watchlist` is slightly more actionable than `Marginal`. It says: this is not failing hard, but it needs attention.

`Marginal` is also acceptable and may be preferable for a more technical audience.

### `Robust` stays `Robust`

`Robust` is already appropriate. It should not be changed unless the deck wants all labels to be less technical.

## Suggested UI behavior

The data model should keep canonical internal band IDs:

```json
{
  "risk_band": "DOOM",
  "display_label": "Critical"
}
```

Do not replace the internal enum everywhere. Keep the internal values stable for sorting, coloring, tests, and backwards compatibility.

Recommended structure:

```js
const LABEL_SETS = {
  internal: {
    DOOM: "DOOM",
    FRAGILE: "FRAGILE",
    MARGINAL: "MARGINAL",
    ROBUST: "ROBUST"
  },
  external: {
    DOOM: "Critical",
    FRAGILE: "High risk",
    MARGINAL: "Watchlist",
    ROBUST: "Robust"
  }
};
```

The generator can accept a configuration option:

```json
{
  "label_mode": "internal"
}
```

or:

```json
{
  "label_mode": "external"
}
```

Default recommendation:

```text
internal
```

because the current use case is PlanExe diagnostic review.

## Color mapping

Keep the existing colors. The color system is already readable:

| Band | Color role |
|---|---|
| `DOOM` / `Critical` | red |
| `FRAGILE` / `High risk` | orange |
| `MARGINAL` / `Watchlist` | yellow |
| `ROBUST` / `Robust` | green |

Do not change colors unless there is an accessibility pass.

## Copy changes for external mode

### Current title/question

```text
How many plans are doomed?
```

External version:

```text
How many plans have critical blockers?
```

Alternative:

```text
Risk-band distribution
```

### Current verdict explanation

```text
DOOM <20%
FRAGILE 20–50%
MARGINAL 50–80%
ROBUST ≥80%
```

External version:

```text
Critical <20%
High risk 20–50%
Watchlist 50–80%
Robust ≥80%
```

### Current title-slide band strip

Internal:

```text
DOOM: 9
FRAGILE: 5
```

External:

```text
Critical: 9
High risk: 5
```

### Per-plan verdict card

Internal:

```text
Overall verdict
DOOM
Worst gate: manual intervention
```

External:

```text
Overall risk band
Critical
Worst gate: manual intervention
```

## Important: do not soften the analysis

Changing labels must not weaken the verdict. This is a tone adjustment, not a scoring adjustment.

Do not change:

- pass-rate thresholds
- worst-gate-wins logic
- base-case failure flags
- gate-level pass rates
- unmodelled-gate warnings
- first-fix recommendations

Only change the words shown to the audience.

## Avoid these labels

### Avoid `Failed`

`Failed` sounds binary and final. Some plans may be one fix away from viability, so `Critical` is better.

### Avoid `Bad`

Too informal and judgmental.

### Avoid `Unsafe`

May imply physical safety or compliance risk where the issue is financial, operational, or market-based.

### Avoid `Rejected`

Sounds like a governance decision rather than an analytical result.

### Avoid `Green / Yellow / Red`

Too vague. The current model has four bands, and color-only language loses detail.

## Recommended implementation tasks for Claude

1. Add a `label_mode` option to the slideshow generator.
2. Keep canonical enum values as `DOOM`, `FRAGILE`, `MARGINAL`, `ROBUST` internally.
3. Add a label mapping layer for display text.
4. Apply the mapping consistently in:
   - title strip
   - verdict distribution chart
   - legends
   - roster tables
   - per-plan verdict cards
   - gate detail tables
   - navigation labels, if applicable
5. Update surrounding copy in external mode, especially “How many plans are doomed?”
6. Keep colors and thresholds unchanged.
7. Add a small test/snapshot check that external mode contains no visible `DOOM` text except possibly in debug JSON.

## Suggested acceptance criteria

Internal mode:

- The slideshow looks essentially like the current version.
- `DOOM`, `FRAGILE`, `MARGINAL`, and `ROBUST` remain visible.

External mode:

- No visible slide text says `DOOM`.
- The verdict distribution uses `Critical`, `High risk`, `Watchlist`, `Robust`.
- The question “How many plans are doomed?” is replaced.
- Pass-rate thresholds and counts remain identical.
- Colors remain identical.
- Debug data may still contain internal enum names.

## Recommendation

Keep `DOOM` mode for internal PlanExe development. It is useful and memorable.

Add an external/stakeholder-safe label mode before showing the deck outside the development context.

Do not remove the internal labels entirely. They are good for debugging and fast triage.
