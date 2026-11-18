# ADR 001: Modular monolith, not microservices

**Status:** accepted · **Date:** 2026-11-17

## Context
One small team, one product, campus-scale traffic. Core workflows (claim approval → item
returned → watch resolved → notifications) need transactional consistency.

## Decision
A single FastAPI deployable split into bounded modules (`auth`, `campus`, `items`,
`lost_reports`, `matching`, `claims`, `assistant`, `notifications`, `desk`). Each owns its
tables and exposes a `service` API. Background work runs in a separately scaled worker
process from the same codebase. Business rules live in a framework-free `domain` package.

## Consequences
+ One deploy, one database transaction across modules, simple local dev (`make up`).
+ Module boundaries make a later split mechanical: `matching` + workers would be first.
− Discipline is needed to stop modules reaching into each other's tables (rules in
  `app/modules/__init__.py`; an import-linter check is a good next step).
