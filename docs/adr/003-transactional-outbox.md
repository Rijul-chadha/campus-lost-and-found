# ADR 003: Transactional outbox for all async side effects

**Status:** accepted · **Date:** 2026-11-17

## Context
Reporting an item must trigger photo processing, embedding and reverse matching; creating a
notification must trigger an email. Writing to Postgres and then enqueueing to Redis is a
dual write: a crash in between silently loses the side effect ("notify me later" never fires).

## Decision
Services write an `outbox_events` row in the same transaction as the state change. A relay
loop in each worker claims unpublished rows with `FOR UPDATE SKIP LOCKED`, enqueues an arq job
with `_job_id = evt:<id>`, and marks the row published. All consumers are idempotent (unique
constraints on match pairs and notification dedupe keys, status checks before work). A cron
job re-queues items stuck in `REPORTED`.

The claim-completion flow deliberately updates items, claims, matches and watches in one
transaction instead of via events: it is a single user action that must be atomic.

## Consequences
+ No lost events; at-least-once delivery with effectively-once effects.
+ Relay scales with worker replicas; sub-second latency from the 50-500 ms poll.
− Extra table plus cleanup cron (published events are pruned after 7 days).
− Postgres LISTEN/NOTIFY could remove polling; not needed at this scale.
