"""Dependency-free embedder based on signed feature hashing.

Not a neural model, but it is deterministic, needs no downloads, runs in microseconds and is
good enough for development, CI and the matching eval baseline. Vocabulary-aware: synonyms
("airpods" -> earbuds) and colour words are expanded into canonical tokens before hashing,
so "navy AirPods case" and "dark blue earbuds" share features.
"""

from __future__ import annotations

import hashlib

import numpy as np

from app.domain.extraction import normalize
from app.domain.matching import SemanticCalibration
from app.domain.vocabulary import CATALOG, COLORS
from app.integrations.embeddings.base import EMBEDDING_DIM

_STOP = frozenset(
    "i my me a an the and or of on in at to with it its is was were this that lost found "
    "left near by from for have has had some please help think".split()
)


def _build_expansions() -> dict[str, list[str]]:
    exp: dict[str, list[str]] = {}
    for cat, types in CATALOG.items():
        for item_type, syns in types.items():
            for s in syns:
                exp.setdefault(s, []).extend([f"type:{item_type}", f"cat:{cat}"])
    for word, (canon, fam) in COLORS.items():
        exp.setdefault(word, []).extend([f"color:{canon}", f"fam:{fam}"])
    return exp


_EXPANSIONS = _build_expansions()
_MULTIWORD = sorted((k for k in _EXPANSIONS if " " in k), key=len, reverse=True)


def _h(token: str) -> tuple[int, float]:
    d = hashlib.blake2b(token.encode(), digest_size=8).digest()
    v = int.from_bytes(d, "little")
    return v % EMBEDDING_DIM, (1.0 if (v >> 63) & 1 else -1.0)


class HashingEmbedder:
    name = "hashing-v1"
    dim = EMBEDDING_DIM
    # Tuned on tests/eval/cases.jsonl (see `make eval`).
    calibration = SemanticCalibration(floor=0.05, ceiling=0.65)

    def _features(self, text: str) -> dict[str, float]:
        norm = normalize(text)
        feats: dict[str, float] = {}

        def add(tok: str, w: float) -> None:
            feats[tok] = feats.get(tok, 0.0) + w

        padded = f" {norm} "
        for phrase in _MULTIWORD:
            if f" {phrase} " in padded:
                for t in _EXPANSIONS[phrase]:
                    add(t, 2.0)
        words = [w for w in norm.split() if w not in _STOP]
        for w in words:
            add(f"w:{w}", 1.0)
            for t in _EXPANSIONS.get(w, ()):
                add(t, 2.0)
            if len(w) > 3:
                for i in range(len(w) - 2):
                    add(f"c:{w[i:i + 3]}", 0.25)
        for a, b in zip(words, words[1:], strict=False):
            add(f"b:{a}_{b}", 0.5)
        return feats

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for tok, w in self._features(text).items():
                idx, sign = _h(tok)
                out[row, idx] += sign * w
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return (out / norms).tolist()  # type: ignore[no-any-return]
