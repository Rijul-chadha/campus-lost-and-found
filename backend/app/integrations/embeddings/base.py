from __future__ import annotations

from typing import Protocol

from app.domain.matching import SemanticCalibration

# Fixed so the pgvector column never changes when swapping providers.
# bge-small-en-v1.5 and all-MiniLM-L6-v2 are both 384-d; the hashing embedder is sized to match.
EMBEDDING_DIM = 384


class Embedder(Protocol):
    name: str
    dim: int
    calibration: SemanticCalibration

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return L2-normalised vectors, one per input text. Synchronous / CPU-bound."""
        ...
