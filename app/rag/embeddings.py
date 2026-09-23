"""Local embeddings via sentence-transformers — no API dependency/cost for embedding,
keeping the only paid API call in the system the final LLM synthesis call."""
from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings


@lru_cache
def _get_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(get_settings().embedding_model)


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    model = _get_model()
    vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return [v.tolist() for v in vectors]


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]
