---
title: Domain Profiles for FermiSanityCheck
---

# Domain Profile Schema

Domain profiles encode the **context** that FermiSanityCheck needs to interpret numerical assumptions correctly. Each profile describes the currency/unit conventions, confidence language, and detection signals for a vertical so the system can normalize any messy input (e.g. invoices, emails, photos) into validated data.

## Schema (YAML)

```yaml
profiles:
  - id: <slug>
    name: <human name>
    description: <what kind of projects this profile covers>
    currency:
      default: <canonical currency code (ISO 4217)>
      aliases:
        - <additional currencies or local abbreviations>
    units:
      metric: true
      convert:
        - from: "sqft"
          to: "m2"
          factor: 0.092903
        - from: "lbs"
          to: "kg"
          factor: 0.453592
    heuristics:
      budget_keywords:
        - budget
        - cost
        - invoice
      timeline_keywords:
        - days
        - weeks
        - timetable
      team_keywords:
        - crew
        - workers
      confidence_keywords:
        high:
          - guarantee
          - have done this
        medium:
          - plan to
          - intend
        low:
          - estimate
          - hope
    detection:
      currency_signals:
        - DKK
        - "kr"
      unit_signals:
        - m2
        - meter
        - hours
      keyword_signals:
        - contractor
        - materials
        - carpentry
```

### Fields explained

- **id / name / description**: human-friendly identifiers for the domain profile.
- **currency**: canonical currency + local aliases (DKK, kr, kroner) so we can map all budgets to one reference value before comparing.
- **units**: flag if metric-first; provide conversion factors to normalize common imperial terms we might still encounter.
- **heuristics**: keyword lists partitioned by topic (budget, timeline, team) plus per-tier confidence keywords.
- **detection**: signals to match incoming documents to this profile (currencies, units, domain-specific keywords). Used by auto-detection logic.

## Examples

### Carpenter (DKK / metric crafts)

```yaml
- id: carpenter
  name: Carpenter / small contractor
  description: Tradespeople working with materials, local currencies, and hourly estimations.
  currency:
    default: DKK
    aliases: ["kr", "dkk", "kroner"]
  units:
    metric: true
    convert:
      - from: "sqft"
        to: "m2"
        factor: 0.092903
      - from: "ft"
        to: "m"
        factor: 0.3048
  heuristics:
    budget_keywords: ["material", "invoice", "estimate", "quote", "project cost"]
    timeline_keywords: ["days", "weeks", "duration", "weather delay", "delivery"]
    team_keywords: ["crew", "workers", "carpenter", "helper"]
    confidence_keywords:
      high: ["I've done this", "guarantee", "know"]
      medium: ["plan to", "expect"]
      low: ["estimate", "maybe", "roughly"]
  detection:
    currency_signals: ["DKK", "kr", "kroner"]
    unit_signals: ["m2", "meter", "cm", "mm"]
    keyword_signals: ["carpenter", "wood", "build", "materials", "client site"]
```

### Dentist (clinical services)

```yaml
- id: dentist
  name: Dental clinic
  description: Small medical/dental practices with patient capacity and procedural budgets.
  currency:
    default: USD
    aliases: ["usd", "$", "dollars", "clinic credit"]
  units:
    metric: true
    convert:
      - from: "chair"
        to: "unit"
        factor: 1
  heuristics:
    budget_keywords: ["treatment", "insurance", "revenue", "procedure cost"]
    timeline_keywords: ["week", "patient", "appointment", "quarter"]
    team_keywords: ["doctor", "assistant", "hygienist"]
    confidence_keywords:
      high: ["patient guarantee", "clinically proven", "always"]
      medium: ["plan to", "expect"]
      low: ["estimate", "maybe"]
  detection:
    currency_signals: ["USD", "$", "dollars", "USD/per"]
    keyword_signals: ["patient", "clinic", "treatment", "appointment", "revenue"]
```

### Personal Project (family trip / weight loss)

```yaml
- id: personal
  name: Personal project/goal
  description: Non-commercial plans with budgets, timelines, and behavioral commitments.
  currency:
    default: USD
    aliases: ["usd", "$", "personal budget"]
  units:
    metric: true
  heuristics:
    budget_keywords: ["budget", "cost", "ticket", "transport"]
    timeline_keywords: ["days", "weeks", "schedule"]
    team_keywords: ["family", "participants", "people"]
    confidence_keywords:
      high: ["definitely", "committed"]
      medium: ["plan to", "expect"]
      low: ["maybe", "hope to"]
  detection:
    keyword_signals: ["family", "trip", "weight loss", "goal", "personal"]
```

## Domain detection logic (overview)

1. **Scan incoming data** (assumptions metadata, extracted keywords, currency mentions, units).  
2. **Score each profile** by counting matches across the `detection` sections (`currency_signals`, `unit_signals`, `keyword_signals`).  
3. **Pick the highest scoring profile** above a configurable threshold (default: majority signal). If no profile wins, fall back to `default` (e.g., "general business").  
4. **Tag the assumption** with the chosen profile so the normalizer/validator applies the correct heuristics and conversions.

This schema can be extended when new domains appear (A2A tokenization, manufacturing, etc.). Once the detection logic tags a profile, the normalizer can apply metric conversions, currency mapping, and confidence heuristics that align with the domain's expectations.
