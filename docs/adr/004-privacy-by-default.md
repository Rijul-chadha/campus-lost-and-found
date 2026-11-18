# ADR 004: Privacy by default for found items

**Status:** accepted · **Date:** 2026-11-17

## Context
Found items include student cards, licences, bank cards and wallets: exactly the things a
bad actor would browse for. Finder-written descriptions may contain names, numbers and contact
details. Photos carry EXIF GPS data.

## Decision
* Store both the original text and a **redacted public copy** computed on write; public APIs
  only ever read the public copy (single serialisation path: `items/presenter.py`).
* Sensitive item types get a generic public title, no public description, no public brand,
  and no public photos until a claim is approved. Matching still uses the full text,
  server-side only.
* The finder's verification detail is never serialised to claimants or the public, never
  enters an LLM prompt, and is only compared by a local similarity function shown to reviewers.
* Every photo is re-encoded by the worker (EXIF stripped) before it is visible.
* **No public browsing.** Only desk staff can list every found item (`GET /items`, the
  desk's *Recently handed in* view). Students see an item only when it matches what they
  describe, so nobody can scroll the pile looking for a phone or wallet to claim.

## Consequences
+ A database or API leak exposes far less; the LLM can't be prompt-injected into leaking secrets.
− Owners of sensitive items see less detail when browsing, which the assistant offsets because
  matching uses the private text.
