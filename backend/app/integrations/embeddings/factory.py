from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import TYPE_CHECKING

from app.integrations.embeddings.base import Embedder

if TYPE_CHECKING:
    from app.core.config import Settings


async def embed_texts(settings: Settings, texts: list[str]) -> tuple[list[list[float]], str]:
    """Embed off the event loop (model inference is CPU-bound). Returns (vectors, model name)."""
    emb = get_embedder(settings.embedding_provider, settings.embedding_model)
    vectors = await asyncio.to_thread(emb.embed, texts)
    return vectors, emb.name


@lru_cache(maxsize=4)
def get_embedder(provider: str = "hashing", model: str = "") -> Embedder:
    if provider == "sentence_transformers":
        from app.integrations.embeddings.sentence_transformer import SentenceTransformerEmbedder

        return SentenceTransformerEmbedder(model or "BAAI/bge-small-en-v1.5")
    if provider == "hashing":
        from app.integrations.embeddings.hashing import HashingEmbedder

        return HashingEmbedder()
    raise ValueError(f"Unknown embedding provider: {provider}")
