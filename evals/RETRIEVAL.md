# Retrieval evaluation (2026-10-20)

30 labeled questions over 18 knowledge chunks (`src/evals/retrieval.py`). Embeddings: none.

| Mode | Hit@1 | Hit@3 | MRR |
|---|---|---|---|
| bm25 | 57% | 90% | 0.72 |

Missed in the top 3:

- **bm25**: Does scrolling Instagram at night hurt my sleep?; Is it okay to work out at night?; How is my baseline calculated?
