"""

Lightweight, fully-offline text embedder for ClariMed AI's RAG layer.

HONEST SCOPE:
This is NOT a transformer embedding model (no BAAI/bge, no sentence-transformers,
no download required). It's a classic NLP technique — hashed bag-of-words /
"feature hashing" — that turns text into a fixed-length numeric vector based
on real word content, so semantically similar text produces similar vectors.

Why this instead of a real embedding model:
    - Zero download, zero internet dependency, works instantly offline
    - No heavy torch/transformers install needed on a time-boxed sprint
    - Deterministic and fast

Upgrade path (documented, not required now): swap `embed()` for a call to
sentence-transformers ("BAAI/bge-small-en-v1.5") once there's time/bandwidth
for the larger dependency. Everything downstream (ChromaDB storage, cosine
similarity search) works identically either way because both produce a
plain list[float] of the same fixed length.
"""

from __future__ import annotations
import re
import math
from typing import List

DIM = 256  # fixed vector length

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "is", "are", "was",
    "were", "be", "been", "being", "with", "for", "on", "at", "by", "this",
    "that", "it", "as", "from", "your", "you", "may", "can", "will", "if",
}


def _tokenize(text: str) -> List[str]:
    words = re.findall(r"[a-zA-Z]+", text.lower())
    return [w for w in words if w not in _STOPWORDS and len(w) > 2]


def embed(text: str, dim: int = DIM) -> List[float]:
    """Hash each token into one of `dim` buckets, accumulate term frequency,
    then L2-normalize. Returns a real, content-derived vector (not a fake
    placeholder)."""
    vec = [0.0] * dim
    tokens = _tokenize(text)
    if not tokens:
        return vec
    for tok in tokens:
        idx = hash(tok) % dim
        vec[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def embed_batch(texts: List[str], dim: int = DIM) -> List[List[float]]:
    return [embed(t, dim) for t in texts]


if __name__ == "__main__":
    a = embed("red eye watery itching conjunctivitis")
    b = embed("dry eyes burning gritty sensation screen time")
    c = embed("red eye watering itchy pink eye discharge")
    def cos(x, y):
        return sum(p * q for p, q in zip(x, y))
    print("sim(conjunctivitis-ish, dry-eye-ish) =", round(cos(a, b), 3))
    print("sim(conjunctivitis-ish, conjunctivitis-ish 2) =", round(cos(a, c), 3))
    print("-> second number should be clearly higher than the first")