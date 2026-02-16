"""
Phase 4 -- Embedding Generation & Storage for pgvector Semantic Search.

Generates dense vector embeddings for startup descriptions using
sentence-transformers (multilingual MiniLM) and stores them in
the startup_embeddings table (pgvector).

The embedding pipeline:
    1. Concatenate relevant text fields into a single document
    2. Encode via sentence-transformers
    3. Store in PostgreSQL via pgvector for cosine similarity search

Usage:
    python -m backend.embeddings                   # embed all startups
    python -m backend.embeddings --batch-size 100  # custom batch size
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

import numpy as np
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.database import async_session, init_db, DATABASE_URL
from backend.models import Startup, StartupEmbedding

logger = logging.getLogger(__name__)

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384


def _build_document(startup) -> str:
    """Concatenate relevant text fields into a single embedding document."""
    parts = [
        startup.name or "",
        startup.company_description or "",
        startup.project_description or "",
        startup.product_description or "",
        startup.technologies or "",
        startup.industries or "",
        startup.product_names or "",
        startup.cluster or "",
    ]
    return " ".join(p.strip() for p in parts if p.strip())


class EmbeddingService:
    """Generates and manages startup embeddings for pgvector search."""

    def __init__(self, model_name: str = MODEL_NAME):
        self._model_name = model_name
        self._model = None

    def _ensure_model(self):
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)
            logger.info("Loaded embedding model: %s", self._model_name)
        except ImportError:
            logger.error(
                "sentence-transformers not installed. "
                "Install with: pip install sentence-transformers"
            )
            raise

    def encode(self, texts: list[str]) -> np.ndarray:
        """Encode a batch of texts into dense vectors."""
        self._ensure_model()
        embeddings = self._model.encode(
            texts,
            batch_size=32,
            show_progress_bar=len(texts) > 100,
            normalize_embeddings=True,
        )
        return embeddings

    def encode_single(self, text: str) -> list[float]:
        """Encode a single text into a vector (for query embedding)."""
        self._ensure_model()
        embedding = self._model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    async def embed_all_startups(self, batch_size: int = 100):
        """
        Generate embeddings for all startups that don't have one yet.
        Stores results in the startup_embeddings table.
        """
        self._ensure_model()

        async with async_session() as session:
            # Get startups without embeddings
            existing_ids_subq = select(StartupEmbedding.startup_id).subquery()
            stmt = (
                select(Startup)
                .where(Startup.id.notin_(select(existing_ids_subq.c.startup_id)))
                .where(Startup.status != "")
            )
            startups = (await session.execute(stmt)).scalars().all()

            if not startups:
                logger.info("All startups already have embeddings")
                return 0

            logger.info("Generating embeddings for %d startups ...", len(startups))

            total_embedded = 0
            for i in range(0, len(startups), batch_size):
                batch = startups[i:i + batch_size]
                documents = [_build_document(s) for s in batch]

                # Filter out empty documents
                valid = [(s, doc) for s, doc in zip(batch, documents) if doc.strip()]
                if not valid:
                    continue

                valid_startups, valid_docs = zip(*valid)
                embeddings = self.encode(list(valid_docs))

                for startup, embedding in zip(valid_startups, embeddings):
                    emb_record = StartupEmbedding(
                        startup_id=startup.id,
                        embedding=embedding.tolist(),
                        model_version=self._model_name,
                    )
                    session.add(emb_record)

                await session.flush()
                total_embedded += len(valid_startups)

                if (i + batch_size) % 500 == 0 or i + batch_size >= len(startups):
                    logger.info("  Embedded %d/%d startups", total_embedded, len(startups))

            await session.commit()
            logger.info("Embedding complete: %d startups", total_embedded)
            return total_embedded

    async def update_embedding(self, startup_id: str, session: AsyncSession):
        """Re-compute and update embedding for a single startup."""
        self._ensure_model()

        startup = (
            await session.execute(
                select(Startup).where(Startup.id == startup_id)
            )
        ).scalar_one_or_none()

        if not startup:
            return

        document = _build_document(startup)
        if not document.strip():
            return

        embedding = self.encode_single(document)

        existing = (
            await session.execute(
                select(StartupEmbedding).where(StartupEmbedding.startup_id == startup_id)
            )
        ).scalar_one_or_none()

        if existing:
            existing.embedding = embedding
            existing.model_version = self._model_name
        else:
            record = StartupEmbedding(
                startup_id=startup_id,
                embedding=embedding,
                model_version=self._model_name,
            )
            session.add(record)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

async def _main(batch_size: int = 100):
    await init_db()
    service = get_embedding_service()
    count = await service.embed_all_startups(batch_size=batch_size)
    print(f"Done. Embedded {count} startups.")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate startup embeddings for pgvector")
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()
    asyncio.run(_main(args.batch_size))


if __name__ == "__main__":
    main()
