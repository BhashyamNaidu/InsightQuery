"""pgvector cosine-similarity retrieval over document_chunks."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document, DocumentChunk
from app.rag.embeddings import embed_query

DEFAULT_TOP_K = 5


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_title: str
    document_source: str
    content: str
    similarity: float  # cosine similarity, 1.0 = identical, 0.0 = orthogonal


def retrieve(session: Session, question: str, top_k: int = DEFAULT_TOP_K) -> list[RetrievedChunk]:
    query_vector = embed_query(question)

    distance = DocumentChunk.embedding.cosine_distance(query_vector)
    stmt = (
        select(DocumentChunk, Document, distance.label("distance"))
        .join(Document, DocumentChunk.document_id == Document.id)
        .order_by(distance)
        .limit(top_k)
    )
    rows = session.execute(stmt).all()

    results: list[RetrievedChunk] = []
    for chunk, document, dist in rows:
        # pgvector's <=> operator returns cosine distance (1 - cosine similarity)
        # directly, regardless of whether the stored vectors are normalized;
        # embeddings are normalized here for a different reason (so the alternative
        # <#> inner-product operator would also be a valid cosine-equivalent index
        # strategy), not because it's required for this formula to hold.
        similarity = max(0.0, min(1.0, 1.0 - float(dist)))
        results.append(
            RetrievedChunk(
                chunk_id=str(chunk.id),
                document_title=document.title,
                document_source=document.source,
                content=chunk.content,
                similarity=round(similarity, 4),
            )
        )
    return results
