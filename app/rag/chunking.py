"""Fixed-size, word-based chunking with overlap.

We approximate tokens with whitespace-delimited words rather than pulling in a
tokenizer dependency just for chunk boundaries — for English reference prose this is
close enough (roughly 0.75 words/token) and the overlap absorbs boundary effects.
Documented as an approximation, not presented as exact token counting.
"""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_CHUNK_SIZE_WORDS = 220
DEFAULT_OVERLAP_WORDS = 40


@dataclass
class Chunk:
    index: int
    content: str


def chunk_text(
    text: str,
    chunk_size_words: int = DEFAULT_CHUNK_SIZE_WORDS,
    overlap_words: int = DEFAULT_OVERLAP_WORDS,
) -> list[Chunk]:
    if overlap_words >= chunk_size_words:
        raise ValueError("overlap_words must be smaller than chunk_size_words")

    words = text.split()
    if not words:
        return []

    chunks: list[Chunk] = []
    start = 0
    index = 0
    step = chunk_size_words - overlap_words
    while start < len(words):
        window = words[start : start + chunk_size_words]
        chunks.append(Chunk(index=index, content=" ".join(window)))
        index += 1
        if start + chunk_size_words >= len(words):
            break
        start += step
    return chunks
