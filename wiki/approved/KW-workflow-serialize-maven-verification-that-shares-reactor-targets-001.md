---
id: KW-workflow-serialize-maven-verification-that-shares-reactor-targets-001
title: Serialize Maven verification that shares reactor targets
type: workflow
status: approved
summary: When parallel verification children target overlapping Maven reactor modules,
  serialize their Maven commands so they do not concurrently write the same target
  directories.
scope:
  repos:
  - dk-fullstack/server
  services:
  - domain-backend
  paths:
  - domain-backend
  languages:
  - Java
  phases:
  - verify
tags:
- maven
- verification
- concurrency
- target-directory
owners:
- dk-fullstack-server
reviewers:
- admin
created_at: 2026-08-15
reviewed_at: 2026-08-15
review_after: 2026-11-15
sources:
- kind: run
  ref: RUN-20260815-164129-d65c14
supersedes: []
conflicts_with: []
---
# Serialize overlapping Maven verification

When multiple verification children run Maven commands against `domain-backend/pom.xml` and their reactor scopes overlap, their modules share `target/` directories. Run those Maven commands through one serialization lock; code review and other read-only checks may still run in parallel.

Treat shared-target symptoms such as transient `NoSuchFileException` or resource-copy permission errors as an environment race until a serialized rerun confirms otherwise. After serialization, evaluate any remaining compiler or test failure as a real finding rather than hiding it as infrastructure noise.

In the source run, serialized execution completed all 11 `domain-backend` compile modules and then ran 14 focused Doris tests with zero failures or errors.
