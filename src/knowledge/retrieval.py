"""Retrieval over the curated knowledge base (knowledge/*.md). Pure logic except `embed`.

Why RAG here: claims about the user's own data are already checked against computed evidence,
but general health knowledge ("screens off before bed", "caffeine late in the day") used to
come from the model's memory, unsourced. Now the agents look it up in a small, curated set of
cards, each paraphrased from a named source, and cite it.

* Chunking: each card is split at its "## " sections; a chunk keeps the card title so it
  makes sense on its own.
* Lexical: BM25 with a small stopword list and light suffix stripping.
* Dense (optional): Voyage embeddings (Anthropic's recommended embedding provider), cosine
  similarity on unit vectors. Chunk embeddings are computed once (`make knowledge-index`) and
  stored in knowledge/embeddings.json; only queries are embedded at run time.
* Hybrid: reciprocal rank fusion of the two rankings (k = 60).
* Store: an exact in-memory index. With a few dozen chunks brute force takes microseconds;
  a vector database (e.g. pgvector) becomes worth it with thousands of chunks.
"""
import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent.parent / "knowledge"
EMBEDDINGS_FILE = KNOWLEDGE_DIR / "embeddings.json"
RRF_K = 60
STOP = set("""a an and are as at be before but by can do does for from has have how i if in into is it its
my of on or should so than that the their them then there these they this to too up was what when which while
who why will with you your about after again all also am any because been being between both did doing down
during each few further had having he her here hers him his just me more most no nor not now off once only
other our out over own same she some such very we were where would yours""".split())


@dataclass
class Chunk:
    id: str             # "<card id>#<section>"
    card: str
    title: str
    source: str
    url: str
    text: str
    tokens: list[str] = field(default_factory=list)


def _stem(w: str) -> str:
    for suf in ("ing", "edly", "ed", "ies", "es", "s", "ly"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)] + ("y" if suf == "ies" else "")
    return w


def tokenize(text: str) -> list[str]:
    return [_stem(w) for w in re.findall(r"[a-z0-9]+", text.lower().replace(":", " ")) if w not in STOP]


def parse_card(text: str) -> tuple[dict, str]:
    meta, body = {}, text
    if text.startswith("---"):
        _, head, body = text.split("---", 2)
        for line in head.strip().splitlines():
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
    return meta, body.strip()


def load_chunks(directory: Path = KNOWLEDGE_DIR) -> list[Chunk]:
    chunks = []
    for path in sorted(directory.glob("*.md")):
        meta, body = parse_card(path.read_text())
        sections = re.split(r"\n## ", "\n" + body)
        for i, sec in enumerate(s for s in sections if s.strip()):
            heading, _, rest = sec.partition("\n") if i else ("", "", sec)
            text = " ".join((rest if i else sec).split())
            title = meta.get("title", path.stem) + (f": {heading.strip()}" if heading.strip() else "")
            chunks.append(Chunk(f"{meta.get('id', path.stem)}#{i}", meta.get("id", path.stem), title,
                                meta.get("source", ""), meta.get("url", ""), text,
                                tokenize(title + " " + text)))
    return chunks


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.docs, self.k1, self.b = docs, k1, b
        self.avg = sum(len(d) for d in docs) / max(1, len(docs))
        df = Counter(t for d in docs for t in set(d))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.tf = [Counter(d) for d in docs]

    def scores(self, query: list[str]) -> list[float]:
        out = []
        for d, tf in zip(self.docs, self.tf):
            s = 0.0
            for t in query:
                if t in tf:
                    f = tf[t]
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * len(d) / self.avg))
            out.append(s)
        return out


def rrf(rankings: list[list[int]], k: int = RRF_K) -> list[int]:
    score: dict[int, float] = {}
    for ranking in rankings:
        for r, i in enumerate(ranking):
            score[i] = score.get(i, 0.0) + 1.0 / (k + r + 1)
    return sorted(score, key=lambda i: -score[i])


def chunk_hash(c: Chunk) -> str:
    return hashlib.sha256((c.title + "\n" + c.text).encode()).hexdigest()[:16]


def embedding_text(c: Chunk) -> str:
    return f"{c.title}. {c.text}"


def build_embeddings(chunks: list[Chunk], api_key: str, model: str, url: str, post=None) -> dict:
    vectors = embed([embedding_text(c) for c in chunks], api_key, model, "document", url, post)
    return dict(model=model, vectors={c.id: v for c, v in zip(chunks, vectors)},
                hashes={c.id: chunk_hash(c) for c in chunks})


_CACHE: dict = {}


def get_index(settings=None) -> "KnowledgeIndex":
    """The shared index; dense search is on when VOYAGE_API_KEY is set and the chunks are embedded."""
    key = getattr(settings, "voyage_api_key", "") if settings is not None else ""
    if key not in _CACHE:
        embed_query = None
        if key:
            model, url = settings.voyage_model, settings.voyage_url
            embed_query = lambda q: embed([q], key, model, "query", url)[0]  # noqa: E731
        _CACHE[key] = KnowledgeIndex.load(embed_query)
    return _CACHE[key]


def embed(texts: list[str], api_key: str, model: str, input_type: str, url: str, post=None) -> list[list[float]]:
    """Voyage embeddings over HTTP (unit-length vectors)."""
    if post is None:
        import httpx
        post = httpx.post
    resp = post(url, timeout=30, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=dict(input=texts, model=model, input_type=input_type))
    if resp.status_code >= 400:
        raise RuntimeError(f"embedding API returned HTTP {resp.status_code}")
    return [d["embedding"] for d in sorted(resp.json()["data"], key=lambda d: d["index"])]


class KnowledgeIndex:
    """search(query, k, mode) -> chunks. mode: "bm25", "dense" or "hybrid" (dense needs embeddings and
    a query embedder; without them "hybrid" quietly becomes "bm25")."""

    def __init__(self, chunks: list[Chunk], vectors: dict[str, list[float]] | None = None,
                 embed_query=None):
        self.chunks = chunks
        self.bm25 = BM25([c.tokens for c in chunks])
        self.vectors = vectors or {}
        self.embed_query = embed_query

    @classmethod
    def load(cls, embed_query=None, directory: Path = KNOWLEDGE_DIR) -> "KnowledgeIndex":
        """Stored vectors are used only for chunks whose text is unchanged since they were embedded."""
        chunks = load_chunks(directory)
        vectors = {}
        path = directory / "embeddings.json"
        if path.exists():
            stored = json.loads(path.read_text())
            hashes = stored.get("hashes", {})
            vectors = {c.id: stored["vectors"][c.id] for c in chunks
                       if c.id in stored.get("vectors", {}) and hashes.get(c.id) == chunk_hash(c)}
        return cls(chunks, vectors, embed_query)

    @property
    def dense_ready(self) -> bool:
        return self.embed_query is not None and all(c.id in self.vectors for c in self.chunks)

    def _lexical(self, query: str) -> list[int]:
        s = self.bm25.scores(tokenize(query))
        return [i for i in sorted(range(len(s)), key=lambda i: -s[i]) if s[i] > 0]

    def _dense(self, query: str) -> list[int]:
        q = self.embed_query(query)
        sims = [sum(a * b for a, b in zip(q, self.vectors[c.id])) for c in self.chunks]
        return sorted(range(len(sims)), key=lambda i: -sims[i])

    def search(self, query: str, k: int = 3, mode: str = "hybrid") -> list[Chunk]:
        if mode == "dense" and not self.dense_ready:
            raise RuntimeError("dense search needs VOYAGE_API_KEY and make knowledge-index")
        if mode == "bm25" or not self.dense_ready:
            order = self._lexical(query)
        elif mode == "dense":
            order = self._dense(query)
        else:
            order = rrf([self._lexical(query), self._dense(query)])
        return [self.chunks[i] for i in order[:k]]


def as_result(chunks: list[Chunk]) -> dict:
    """What the agents see: short passages with an id and a named source to cite."""
    if not chunks:
        return dict(results=[], note="Nothing relevant in the knowledge base; do not state general facts.")
    return dict(results=[dict(id=c.id, title=c.title, source=c.source, text=c.text) for c in chunks],
                note="Use only what these passages say, and name the source briefly, e.g. (AASM).")
