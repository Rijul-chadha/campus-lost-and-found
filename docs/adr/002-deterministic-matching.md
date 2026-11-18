# ADR 002: Deterministic matcher; the LLM only handles language

**Status:** accepted · **Date:** 2026-11-17

## Context
Owners describe items in messy natural language; we must rank found items and decide when to
push a notification. A false notification costs trust; a missed one costs a reunion.

## Decision
Ranking and notification decisions use a deterministic scorer (`app/domain/matching.py`):
hybrid candidate generation (pgvector ANN ∪ exact item type), vetoes, per-signal scores,
weighted combination over present signals, and hard caps on contradictions. The LLM is used
only to extract structured fields from conversation and to phrase replies, and every LLM
step has a rule-based fallback.

## Consequences
+ Explainable ("Same kind of item", "Found 120 m from where you lost it"), reproducible,
  unit-testable, and measurable offline (`make eval`, gated in CI).
+ Reverse matching (each new item × all open watches) costs ~nothing per pair.
+ The app works with no LLM at all; free-tier rate limits can't take matching down.
− Weights are hand-tuned; with enough "not mine" feedback, learn them (logistic regression
  on component scores) and keep the same explainable structure.
