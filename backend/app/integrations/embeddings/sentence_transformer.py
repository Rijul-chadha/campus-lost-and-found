"""Neural sentence embeddings via sentence-transformers (install with `pip install .[ml]`).

Loaded lazily once per process. CPU inference of bge-small is ~5-15 ms per short text, so it
runs inside the worker (via a thread) and never on the request path for found items.
"""

from __future__ import annotations

import threading
from typing import Any

from app.domain.matching import SemanticCalibration
from app.integrations.embeddings.base import EMBEDDING_DIM


class SentenceTransformerEmbedder:
    dim = EMBEDDING_DIM
    # bge-small puts unrelated short texts around 0.45-0.55 cosine; tune with `make eval`.
    calibration = SemanticCalibration(floor=0.50, ceiling=0.88)

    def __init__(self, model_name: str) -> None:
        self.name = f"st:{model_name}"
        self._model_name = model_name
        self._model: Any = None
        self._lock = threading.Lock()

    def _load(self) -> Any:
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from sentence_transformers import SentenceTransformer

                    model = SentenceTransformer(self._model_name, device="cpu")
                    dim = model.get_sentence_embedding_dimension()
                    if dim != EMBEDDING_DIM:
                        raise RuntimeError(
                            f"{self._model_name} produces {dim}-d vectors; schema expects "
                            f"{EMBEDDING_DIM}. Pick a 384-d model or add a migration."
                        )
                    self._model = model
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._load().encode(texts, normalize_embeddings=True, batch_size=32)
        return [v.tolist() for v in vectors]
