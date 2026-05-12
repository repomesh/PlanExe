---
title: Distributed Physical Task Dispatch Protocol
date: 2026-02-11
status: proposal
author: PlanExe Team
---

# Distributed Physical Task Dispatch Protocol

**Author:** PlanExe Team  
**Date:** 2026-02-11  
**Status:** Proposal  
**Audience:** IoT Architects, Robotics Engineers

---

## Pitch
Define a secure protocol for dispatching physical tasks from the PlanExe Cloud to edge agents and verifying real-world execution.

## Why
Cloud planning is only valuable if it can reliably trigger real actions on devices. A standardized dispatch protocol closes the cloud-to-edge gap.

## Problem

- Gantt tasks are not executable by edge devices.
- No consistent task payload or authentication layer.
- Proof of physical execution is weak or absent.

## Proposed Solution
Implement a pub/sub dispatch protocol that:

1. Publishes `TaskManifest` payloads to secure device channels.
2. Authenticates edge agents with client certs.
3. Verifies task completion with proof-of-physical-work.

## Architecture

```text
PlanExe Cloud
  -> Dispatcher
  -> MQTT/WebSocket Bus
  -> Edge Agent
  -> Proof Upload
  -> Verification
```

## Task Manifest Schema

```json
{
  "task_id": "task_888",
  "command": "capture_image",
  "parameters": {
    "resolution": "1080p",
    "angle": "45_degrees",
    "target": "zone_a"
  },
  "deadline": "2026-02-12T09:00:00Z",
  "auth_token": "jwt_ey..."
}
```

## Proof of Physical Work (PoPW)

- Photo verification with timestamp
- Sensor logs (e.g., humidity spike)
- GPS signature for location-dependent tasks

## Integration Points

- Works with OpenClaw execution skill.
- Feeds into MoltBook gig dispatch.
- Used by assumption drift monitor for real-world signals.

## Success Metrics

- Dispatch latency (cloud -> edge ack).
- % tasks completed with valid PoPW.
- Reduction in false execution claims.

## Risks

- Device spoofing or token leakage.
- Network instability in remote sites.
- High verification cost for complex tasks.

## Future Enhancements

- Hardware attestation support.
- Offline task caching and delayed sync.
- Automated anomaly detection on PoPW.

## Detailed Implementation Plan

### Phase A — Protocol and Security Foundations (2 weeks)

1. Define `TaskManifest` schema versioning.
2. Add mutual-auth model for edge agents:
   - client certs or hardware keys
   - short-lived dispatch tokens

3. Add replay protection and nonce strategy.

### Phase B — Dispatcher and Transport Layer (2–3 weeks)

1. Implement cloud dispatcher with QoS guarantees.
2. Support MQTT/WebSocket transports behind common abstraction.
3. Add delivery semantics:
   - accepted
   - in_progress
   - completed
   - failed

### Phase C — Proof of Physical Work (PoPW) Verification (2 weeks)

1. Define PoPW artifact schema:
   - timestamp
   - geo/location
   - sensor payload
   - media hash

2. Build verifier pipeline:
   - integrity checks
   - anti-spoof heuristics
   - confidence scoring

3. Attach PoPW confidence to task completion status.

### Phase D — Reliability and Operations (2 weeks)

1. Add offline task cache with deferred sync.
2. Add dead-letter queue for failed dispatches.
3. Add anomaly detection for suspicious execution proofs.

### Data model additions

- `physical_task_dispatch`
- `edge_delivery_events`
- `popw_artifacts`
- `popw_verification_results`

### Validation checklist

- End-to-end dispatch latency targets
- Exactly-once/at-least-once behavior verification
- PoPW spoofing simulation tests
- Offline replay consistency checks
