import math

from src.coach.agent import Toolbox
from src.evals.retrieval import QUERIES, evaluate
from src.knowledge.retrieval import BM25, KnowledgeIndex, as_result, build_embeddings, load_chunks, rrf, tokenize
from tests.test_coach import FakeData


def test_cards_are_chunked_with_sources():
    chunks = load_chunks()
    assert len(chunks) >= 15 and len({c.id for c in chunks}) == len(chunks)
    assert all(c.source and c.text for c in chunks)
    sec = next(c for c in chunks if c.id == "evening-exercise#1")
    assert sec.title == "Exercise in the evening and sleep: In practice"


def test_bm25_and_rrf():
    bm = BM25([tokenize("caffeine late afternoon"), tokenize("evening exercise sleep"), tokenize("sleep sleep")])
    s = bm.scores(tokenize("caffeine"))
    assert s[0] > 0 and s[1] == s[2] == 0
    assert rrf([[0, 1, 2], [2, 0, 1]])[0] == 0          # good in both rankings beats first in one
    assert tokenize("Sleeping and sleeps") == ["sleep", "sleep"]


def test_lexical_retrieval_stays_good():
    """A regression floor for the labeled questions (measured: hit@3 0.90 with BM25)."""
    r = evaluate(KnowledgeIndex.load(), "bm25")
    assert r["queries"] == len(QUERIES) and r["hit_at_k"] >= 0.85 and r["mrr"] >= 0.65


def test_hybrid_uses_dense_vectors_when_available():
    chunks = load_chunks()
    # toy embedder: a "screens" direction, so a query without the card's words still lands on it
    def vec(text):
        t = text.lower()
        v = [1.0 if any(w in t for w in ("screen", "phone", "instagram", "scroll")) else 0.0, 0.1]
        n = math.sqrt(sum(x * x for x in v))
        return [x / n for x in v]

    class Post:
        status_code = 200

        def __init__(self, body):
            self.body = body

        def json(self):
            return self.body

    def post(url, **kw):
        return Post(dict(data=[dict(index=i, embedding=vec(t)) for i, t in enumerate(kw["json"]["input"])]))

    data = build_embeddings(chunks, "k", "m", "u", post=post)
    index = KnowledgeIndex(chunks, data["vectors"], embed_query=vec)
    assert index.dense_ready
    top = index.search("Does scrolling Instagram at night hurt my sleep?", k=1, mode="dense")[0]
    assert top.card == "evening-screens-light"
    assert KnowledgeIndex(chunks).search("coffee", mode="hybrid")   # no vectors: falls back to BM25


def test_agents_can_search_and_cite():
    tb = Toolbox(FakeData())
    r = tb.run("search_guidelines", dict(query="Does caffeine in the afternoon affect sleep?"))
    top = r["results"][0]
    assert top["id"].startswith("caffeine-timing") and "AASM" in top["source"] and len(r["results"]) <= 3
    assert tb.sources and tb.sources[0]["url"].startswith("https://")
    assert as_result([])["results"] == []


def test_queries_are_batched_cached_and_rate_limits_retried():
    from src.knowledge.retrieval import embed
    calls = []

    class R:
        def __init__(self, code, body=None):
            self.status_code, self._body, self.headers = code, body, {}

        def json(self):
            return self._body

    queue = [R(429), R(200, dict(data=[dict(index=0, embedding=[1.0, 0.0])]))]

    def post(url, **kw):
        calls.append(kw["json"]["input"])
        return queue.pop(0)
    waits = []
    assert embed(["q"], "k", "m", "query", "u", post=post, sleep=waits.append) == [[1.0, 0.0]]
    assert len(calls) == 2 and waits == [10.0]

    chunks = load_chunks()
    batches = []
    index = KnowledgeIndex(chunks, {c.id: [1.0, 0.0] for c in chunks}, embed_query=lambda q: 1 / 0)
    index.embed_queries = lambda qs: batches.append(qs) or [[1.0, 0.0] for _ in qs]
    index.prime(["a", "b", "a"])
    index.search("a", mode="dense")
    index.search("b", mode="hybrid")                  # served from the cache, no single-query call
    assert batches == [["a", "b"]]
