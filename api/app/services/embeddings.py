"""Query embeddings with fastembed (same model as jobs/embed, so vectors are comparable).

The model loads on first use (~1 s once cached) and is then shared by all requests.
Embedding is CPU work, so it runs in a worker thread to keep the event loop free.
"""

import asyncio
import os
import threading

from app.config import settings

_model = None
_lock = threading.Lock()


def _get_model():
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                # Windows without Developer Mode can't symlink; the cache still works
                os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
                from fastembed import TextEmbedding

                _model = TextEmbedding(settings.embedding_model, cache_dir=settings.fastembed_cache)
    return _model


def _embed(text: str) -> list[float]:
    # No query prefix: tested on the sample, BGE's instruction prefix didn't improve ranking
    vector = next(iter(_get_model().query_embed(text)))
    return [float(x) for x in vector]


async def embed_query(text: str) -> list[float]:
    return await asyncio.to_thread(_embed, text)
