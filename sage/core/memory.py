"""The knowledge base -- SAGE's ingested understanding of a company.

Retrieval is real vector-space search: each chunk becomes a TF-IDF vector and
queries are ranked by cosine similarity -- implemented in pure stdlib so the
whole system keeps its zero-dependency promise. The interface (`ingest`,
`search`, `context_for`, `summary`) is what matters; a future embedding model
or external vector DB drops in behind `search()` without touching any caller.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List


@dataclass
class Chunk:
    ref: str          # e.g. "doc:requirements.md#2"
    source: str       # filename
    text: str
    tokens: set = field(default_factory=set)
    tf: Counter = field(default_factory=Counter)   # term frequencies


def _tokens(text: str) -> List[str]:
    return re.findall(r"[a-z][a-z0-9\-]{2,}", text.lower())


def _tokenize(text: str) -> set:
    return set(_tokens(text))


class KnowledgeBase:
    def __init__(self) -> None:
        self.chunks: List[Chunk] = []
        self.sources: Dict[str, int] = {}

    def ingest_text(self, source: str, text: str, chunk_chars: int = 600) -> int:
        """Chunk and store raw text. Re-ingestion is first-class."""
        paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        # Re-pack paragraphs into ~chunk_chars windows.
        added = 0
        state = {"buf": "", "idx": 0}

        def flush() -> None:
            nonlocal added
            if state["buf"].strip():
                toks = _tokens(state["buf"])
                self.chunks.append(
                    Chunk(ref=f"doc:{source}#{state['idx']}", source=source,
                          text=state["buf"].strip(), tokens=set(toks),
                          tf=Counter(toks))
                )
                state["idx"] += 1
                added += 1
                state["buf"] = ""

        for p in paras:
            if state["buf"] and len(state["buf"]) + len(p) > chunk_chars:
                flush()
            state["buf"] += ("\n\n" + p) if state["buf"] else p
        flush()  # flush the trailing buffer -- the bug was this never ran

        self.sources[source] = self.sources.get(source, 0) + added
        return added

    def ingest_path(self, path: str) -> int:
        """Ingest a file or every text file in a directory."""
        p = Path(path)
        total = 0
        files = [p] if p.is_file() else sorted(
            f for f in p.rglob("*") if f.suffix.lower() in {".md", ".txt"}
        )
        for f in files:
            total += self.ingest_text(f.name, f.read_text(encoding="utf-8"))
        return total

    def _idf(self) -> Dict[str, float]:
        """Inverse document frequency across all chunks."""
        n = len(self.chunks)
        df: Counter = Counter()
        for c in self.chunks:
            df.update(c.tokens)
        return {t: math.log((n + 1) / (d + 1)) + 1.0 for t, d in df.items()}

    @staticmethod
    def _tfidf_vec(tf: Counter, idf: Dict[str, float]) -> Dict[str, float]:
        return {t: f * idf.get(t, 0.0) for t, f in tf.items()}

    @staticmethod
    def _cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
        if not a or not b:
            return 0.0
        # iterate the smaller dict for the dot product
        small, big = (a, b) if len(a) <= len(b) else (b, a)
        dot = sum(w * big.get(t, 0.0) for t, w in small.items())
        if dot == 0.0:
            return 0.0
        na = math.sqrt(sum(w * w for w in a.values()))
        nb = math.sqrt(sum(w * w for w in b.values()))
        return dot / (na * nb) if na and nb else 0.0

    def search(self, query: str, k: int = 4) -> List[Chunk]:
        """Rank chunks by TF-IDF cosine similarity to the query."""
        if not self.chunks:
            return []
        q_tokens = _tokens(query)
        if not q_tokens:
            return self.chunks[:k]
        idf = self._idf()
        q_vec = self._tfidf_vec(Counter(q_tokens), idf)
        scored = []
        for c in self.chunks:
            sim = self._cosine(q_vec, self._tfidf_vec(c.tf, idf))
            if sim > 0:
                scored.append((sim, c))
        scored.sort(key=lambda x: x[0], reverse=True)
        hits = [c for _, c in scored[:k]]
        return hits or self.chunks[:k]

    def context_for(self, query: str, k: int = 4) -> str:
        return "\n\n".join(f"[{c.ref}] {c.text}" for c in self.search(query, k))

    def summary(self) -> str:
        parts = [f"{s} ({n} chunks)" for s, n in self.sources.items()]
        return f"{len(self.chunks)} chunks from: " + ", ".join(parts)
