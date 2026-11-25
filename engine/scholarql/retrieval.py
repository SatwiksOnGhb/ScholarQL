"""Rank document evidence using BM25, TF-IDF cosine, or MiniLM cosine."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from threading import Lock

import numpy as np

from .config import RUNTIME

WORD = re.compile(r"[a-z0-9][a-z0-9+-]+", re.I)
STOP = frozenset(
    """
a an and are as at be been by can could for from has have how i in into is it its may
of on or paper papers show study than that the their them they this to using was
we what when where which who will with work would you about find published research
""".split()
)
MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
MODEL_VARIANTS = {
    "onnx/model_quint8_avx2.onnx": "b941bf19f1f1283680f449fa6a7336bb5600bdcd5f84d10ddc5cd72218a0fd21",
}
TOKENIZER_SHA256 = "be50c3628f2bf5bb5e3a7f17b1f74611b2561a3a27eeab05e5aa30f411572037"


def words(text: str) -> list[str]:
    return [word for word in WORD.findall(text.casefold()) if word not in STOP]


def unit_rows(rows: np.ndarray) -> np.ndarray:
    return rows / np.maximum(np.linalg.norm(rows, axis=1, keepdims=True), 1e-12)


def document_text(document: dict) -> str:
    return f"{document.get('title') or ''}. {document.get('abstract') or ''}"


class MiniLM:
    name = "MiniLM cosine"

    def __init__(self, directory: Path):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        path = directory / "model.onnx"
        if not path.is_file() or not (directory / "tokenizer.json").is_file():
            raise ValueError("Run python -m scripts.download_model before selecting MiniLM.")
        self.fingerprint = _sha256(path)
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(
            str(path), sess_options=options, providers=["CPUExecutionProvider"]
        )
        self.input_names = {item.name for item in self.session.get_inputs()}
        self.tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=256)
        self.tokenizer.enable_padding()

    def encode(self, texts: list[str]) -> np.ndarray:
        batches = []
        for start in range(0, len(texts), 32):
            tokenized = self.tokenizer.encode_batch(texts[start : start + 32])
            mask = np.asarray([t.attention_mask for t in tokenized], dtype=np.int64)
            data = {
                "input_ids": np.asarray([t.ids for t in tokenized], dtype=np.int64),
                "attention_mask": mask,
                "token_type_ids": np.asarray([t.type_ids for t in tokenized], dtype=np.int64),
            }
            (hidden, *_) = self.session.run(None, {name: data[name] for name in self.input_names})
            if hidden.ndim != 3 or hidden.shape[2] != 384:
                raise ValueError(
                    "The configured model must produce MiniLM token embeddings with 384 dimensions."
                )
            mean = (hidden * mask[:, :, None]).sum(axis=1) / np.maximum(
                mask.sum(axis=1, keepdims=True), 1
            )
            batches.append(unit_rows(mean).astype(np.float32))
        return np.concatenate(batches) if batches else np.empty((0, 384), dtype=np.float32)


def _sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def model_directory() -> Path:
    return Path(os.getenv("SCHOLARQL_MODEL_DIR", str(RUNTIME / "model")))


class TextIndex:
    def __init__(self, documents: list[dict], encoder: MiniLM | None = None):
        self.documents = sorted(documents, key=lambda item: item["paper_id"])
        self.positions = {doc["paper_id"]: idx for idx, doc in enumerate(self.documents)}
        self.encoder = encoder
        self._dense = None
        self._lock = Lock()
        counts = [Counter(words(document_text(doc))) for doc in self.documents]
        self.lengths = np.asarray([sum(doc.values()) for doc in counts], dtype=float)
        self.avg_length = max(float(self.lengths.mean()), 1.0) if counts else 1.0
        postings = defaultdict(list)
        for idx, doc in enumerate(counts):
            for word, count in doc.items():
                postings[word].append((idx, count))
        n = len(self.documents)
        self.idf = {
            term: 1 + math.log((n + 1) / (len(items) + 1)) for term, items in postings.items()
        }
        norm_squares = np.zeros(n)
        self.lexical = {}
        for term, items in postings.items():
            ids, tf = np.asarray(items, dtype=np.int64).T
            weights = (1 + np.log(tf)) * self.idf[term]
            norm_squares[ids] += weights * weights
            self.lexical[term] = (ids, tf, weights)
        self.norms = np.maximum(np.sqrt(norm_squares), 1e-12)

    def _matrix(self) -> np.ndarray:
        with self._lock:
            if self._dense is not None:
                return self._dense
            texts = [document_text(doc) for doc in self.documents]
            digest = hashlib.sha256(self.encoder.fingerprint.encode())
            for document, text in zip(self.documents, texts):
                digest.update(document["paper_id"].encode() + b"\0" + text.encode() + b"\0")
            RUNTIME.mkdir(exist_ok=True, parents=True)
            cache = RUNTIME / f"embeddings-{digest.hexdigest()[:20]}.npy"
            try:
                matrix = np.load(cache, allow_pickle=False)
                if matrix.shape != (len(texts), 384):
                    raise ValueError("Unexpected embedding cache shape")
            except (OSError, ValueError):
                matrix = self.encoder.encode(texts)
                with tempfile.NamedTemporaryFile(
                    dir=RUNTIME, suffix=".npy", delete=False
                ) as output:
                    np.save(output, matrix, allow_pickle=False)
                    temp = Path(output.name)
                try:
                    temp.replace(cache)
                finally:
                    temp.unlink(missing_ok=True)
            self._dense = matrix
            return matrix

    def embeddings(self) -> np.ndarray:
        if not self.encoder:
            raise ValueError("MiniLM must be configured to produce dense embeddings.")
        return self._matrix()

    def _lexical_scores(self, query: str, mode: str) -> np.ndarray:
        q = Counter(words(query))
        scores = np.zeros(len(self.documents))
        normalizer = math.sqrt(
            sum(
                ((1 + math.log(tf)) * self.idf[term]) ** 2
                for term, tf in q.items()
                if term in self.idf
            )
        )
        for term, query_tf in q.items():
            if term not in self.lexical:
                continue
            idx, tf, weight = self.lexical[term]
            if mode == "bm25":
                idf = math.log1p((len(self.documents) - len(idx) + 0.5) / (len(idx) + 0.5))
                length_penalty = 1.2 * (0.25 + 0.75 * self.lengths[idx] / self.avg_length)
                scores[idx] += idf * tf * 2.2 / (tf + length_penalty)
            elif normalizer:
                query_weight = (1 + math.log(query_tf)) * self.idf[term]
                scores[idx] += weight * query_weight / (normalizer * self.norms[idx])
        return scores

    def rank(self, query: str, *, eligible: set[str] | None, k: int, mode: str) -> list[dict]:
        candidates = np.asarray(
            list(range(len(self.documents)))
            if eligible is None
            else sorted(self.positions[key] for key in eligible if key in self.positions),
            dtype=np.int64,
        )
        if not candidates.size or not query.strip():
            return []
        if mode == "minilm":
            scores = (self.embeddings()[candidates] @ self.encoder.encode([query])[0]).astype(float)
        else:
            scores = self._lexical_scores(query, mode)[candidates]
        order = np.argsort(-scores, kind="stable")
        result = []
        for index in order[:k]:
            score = float(scores[index])
            if score <= 0:
                break
            doc = self.documents[int(candidates[index])]
            result.append({"paper_id": doc["paper_id"], "score": score})
        return result


def load_documents(path: Path) -> list[dict]:
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))["documents"]
    with path.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]
