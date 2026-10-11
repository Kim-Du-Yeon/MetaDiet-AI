"""Gemini-only embeddings with separate retrieval query/document instructions."""
import asyncio
import math
import hashlib
import json
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from google import genai
from google.genai import types
from langchain_core.embeddings import Embeddings

from app.core.config import get_settings


class GeminiEmbeddings(Embeddings):
    def __init__(self, *, cache_root: Path | None = None):
        self._provider = None
        self.cache_root = cache_root or Path(__file__).resolve().parents[2] / "artifacts/embedding-cache"

    def _client(self):
        settings = get_settings()
        if settings.embedding_model != "gemini-embedding-2":
            raise ValueError("EMBEDDING_MODEL must be gemini-embedding-2; rebuild old vectors")
        if not 1 <= settings.embedding_dimension <= 3072:
            raise ValueError("EMBEDDING_DIMENSION must be between 1 and 3072")
        if not settings.gemini_api_key.strip():
            raise ValueError("Set GEMINI_API_KEY before embedding")
        if self._provider is None:
            self._provider = genai.Client(
                api_key=settings.gemini_api_key,
                http_options=types.HttpOptions(
                    timeout=int(settings.model_timeout_seconds * 1000),
                    retry_options=types.HttpRetryOptions(attempts=settings.model_max_retries + 1),
                ),
            )
        return self._provider

    def _embed(self, text: str) -> list[float]:
        settings = get_settings()
        # Embedding 2 aggregates list inputs: send exactly one document per call.
        result = self._client().models.embed_content(
            model=settings.embedding_model, contents=text,
            config=types.EmbedContentConfig(output_dimensionality=settings.embedding_dimension),
        )
        if not result.embeddings or len(result.embeddings) != 1:
            raise ValueError("Gemini returned an unexpected embedding count")
        values = result.embeddings[0].values
        if not values or len(values) != settings.embedding_dimension:
            raise ValueError("Gemini returned an unexpected embedding dimension")
        if not all(math.isfinite(v) for v in values):
            raise ValueError("Gemini returned non-finite embedding values")
        norm = math.sqrt(sum(v * v for v in values))
        if not norm:
            raise ValueError("Gemini returned a zero embedding")
        return [v / norm for v in values]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        # Bounded concurrency, never an aggregated list of documents in one call.
        settings = get_settings()
        cache = self.cache_root
        if texts:
            self._client()
        def embed(text):
            formatted = f"title: none | text: {text}"
            key = hashlib.sha256(f"{settings.embedding_model}:{settings.embedding_dimension}:{formatted}".encode()).hexdigest()
            path = cache / f"{key}.json"
            if path.is_file():
                values = json.loads(path.read_text(encoding="utf-8"))
                if len(values) == settings.embedding_dimension and all(math.isfinite(v) for v in values):
                    return values
            values = self._embed(formatted)
            cache.mkdir(parents=True, exist_ok=True)
            from uuid import uuid4
            temporary = path.with_suffix(f".{uuid4().hex}.tmp")
            temporary.write_text(json.dumps(values), encoding="utf-8")
            os.replace(temporary, path)
            return values
        with ThreadPoolExecutor(max_workers=4) as pool:
            return list(pool.map(embed, texts))

    def embed_query(self, text: str) -> list[float]:
        return self._embed(f"task: search result | query: {text}")

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(self.embed_documents, texts)

    async def aembed_query(self, text: str) -> list[float]:
        return await asyncio.to_thread(self.embed_query, text)
