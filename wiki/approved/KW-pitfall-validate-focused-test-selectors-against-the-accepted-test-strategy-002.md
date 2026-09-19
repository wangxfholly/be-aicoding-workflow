---
id: KW-pitfall-validate-focused-test-selectors-against-the-accepted-test-strategy-002
title: Validate focused-test selectors against the accepted test strategy
type: pitfall
status: approved
summary: Before Verify dispatch, compare every required focused test class with the
  repository adapter test selectors so a successful command cannot omit required evidence.
scope:
  repos:
  - dk-fullstack-server
  services:
  - domain-webpush
  - domain-backend
  - domain-order
  paths:
  - .ai-workflow.yaml
  languages:
  - yaml
  phases:
  - plan
  - verify
tags:
- ai-workflow
- maven
- surefire
- test-strategy
- verification
owners:
- ai-workflow
reviewers:
- human
created_at: 2026-08-20
reviewed_at: 2026-08-20
review_after: 2026-11-20
sources:
- kind: run
  ref: RUN-20260819-150732-b97d7f
supersedes: []
conflicts_with: []
---
# Focused-test selector completeness

## Pitfall

An accepted test strategy may require more test classes than the repository adapter includes in its `-Dtest` selectors. A test command can then exit successfully while required acceptance evidence is missing. The Test Runner must not repair this by inventing commands.

## Required check

Before dispatching `verify.unit_test`, read the accepted test strategy and `ai-workflow config show`, normalize the required test class names and configured selectors, and compare them as sets. If any required class is absent, update the repository adapter through an authorized configuration change before beginning Verify. Regenerate the packet, then confirm the packet contains every required class.

## Verification evidence

Record the generated packet command, final exit code, and Surefire testcase totals for every required class. Keep shared Maven reactor execution serialized under the repository lock; selector completeness complements, rather than replaces, the existing serialization rule.

## Run evidence

In RUN-20260819-150732-b97d7f, Verify first passed 36 selected testcases but returned UT-PACKET-001 because four strategy-required classes were absent. After the adapter selectors were corrected, the regenerated packet ran 13 classes and 48 testcases with exit code 0.
