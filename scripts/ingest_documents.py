"""Chunk, embed, and load the curated RAG document corpus (data/documents/) into
Postgres/pgvector. Idempotent: clears and reloads all documents/chunks each run,
since the corpus is small (~15 files) and hand-curated rather than continuously
growing — re-deriving from source is simpler and safer than incremental upsert
logic for a corpus this size.

Usage:
    python scripts/ingest_documents.py
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from app.db.session import SessionLocal
from app.models import Document, DocumentChunk
from app.rag.chunking import chunk_text
from app.rag.embeddings import embed_texts

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ingest_documents")

DOCS_DIR = Path(__file__).resolve().parent.parent / "data" / "documents"


def main() -> None:
    manifest = json.loads((DOCS_DIR / "manifest.json").read_text(encoding="utf-8"))

    with SessionLocal() as session:
        existing = session.query(Document).count()
        if existing:
            logger.info("Clearing %d existing documents before reload.", existing)
            session.query(DocumentChunk).delete()
            session.query(Document).delete()
            session.commit()

        total_chunks = 0
        for entry in manifest:
            path = DOCS_DIR / entry["file"]
            text = path.read_text(encoding="utf-8")

            document = Document(title=entry["title"], source=entry["file"], category=entry["category"])
            session.add(document)
            session.flush()  # assign document.id

            chunks = chunk_text(text)
            if not chunks:
                logger.warning("No chunks produced for %s (empty file?)", entry["file"])
                continue

            embeddings = embed_texts([c.content for c in chunks])
            for chunk, embedding in zip(chunks, embeddings):
                session.add(
                    DocumentChunk(
                        document_id=document.id,
                        chunk_index=chunk.index,
                        content=chunk.content,
                        embedding=embedding,
                    )
                )
            total_chunks += len(chunks)
            logger.info("Ingested %s: %d chunks", entry["file"], len(chunks))

        session.commit()
        logger.info("Done. %d documents, %d chunks.", len(manifest), total_chunks)


if __name__ == "__main__":
    main()
