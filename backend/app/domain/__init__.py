"""Framework-free domain core.

Nothing in this package may import FastAPI, SQLAlchemy, Redis or any I/O library.
That keeps the business rules (state machines, matching, extraction, privacy) fast to
test, easy to reason about, and reusable from both the API and the workers.
"""
