"""Bounded modules of the monolith.

Rules that keep each module extractable into its own service later:
  * Writes to a module's tables go through that module's `service` (or an outbox event).
  * Other modules may READ another module's models only in presenters/repositories
    (joins for display), never mutate them directly. The one deliberate exception is the
    claims workflow closing a watch, which is a single transaction by design (see ADR 003).
  * Routers never import other modules' routers.
"""
