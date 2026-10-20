"""Build the knowledge base's embeddings and evaluate retrieval.

    make knowledge-index   # embed knowledge/*.md chunks (needs VOYAGE_API_KEY) -> knowledge/embeddings.json
    make eval-retrieval    # hit@1, hit@3 and MRR for BM25, dense and hybrid search -> evals/RETRIEVAL.md

Only the public, paraphrased knowledge cards and the labeled test questions are sent to the
embedding API; no personal data.
"""
import argparse
import json
import sys
from datetime import date

import _bootstrap  # noqa: F401

from src import config
from src.evals.retrieval import QUERIES, evaluate
from src.knowledge import retrieval
from src.settings import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["index", "eval"])
    args = parser.parse_args()
    s = Settings.from_env()
    chunks = retrieval.load_chunks()
    if args.command == "index":
        if not s.voyage_api_key:
            sys.exit("Set VOYAGE_API_KEY in .env first.")
        data = retrieval.build_embeddings(chunks, s.voyage_api_key, s.voyage_model, s.voyage_url)
        retrieval.EMBEDDINGS_FILE.write_text(json.dumps(data))
        print(f"Embedded {len(chunks)} chunks with {s.voyage_model} -> knowledge/embeddings.json")
        return
    index = retrieval.get_index(s)
    modes = ["bm25"] + (["dense", "hybrid"] if index.dense_ready else [])
    if not index.dense_ready:
        print("Dense search off (needs VOYAGE_API_KEY and make knowledge-index); evaluating BM25 only.")
    results = [evaluate(index, m) for m in modes]
    lines = [f"# Retrieval evaluation ({date.today().isoformat()})", "",
             f"{len(QUERIES)} labeled questions over {len(chunks)} knowledge chunks (`src/evals/retrieval.py`). "
             f"Embeddings: {s.voyage_model if index.dense_ready else 'none'}.", "",
             "| Mode | Hit@1 | Hit@3 | MRR |", "|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r['mode']} | {100 * r['hit_at_1']:.0f}% | {100 * r['hit_at_k']:.0f}% | {r['mrr']:.2f} |")
    lines += ["", "Missed in the top 3:", ""]
    for r in results:
        lines.append(f"- **{r['mode']}**: " + ("; ".join(r["misses"]) or "none"))
    (config.PROJECT_ROOT / "evals").mkdir(exist_ok=True)
    (config.PROJECT_ROOT / "evals" / "RETRIEVAL.md").write_text("\n".join(lines) + "\n")
    for r in results:
        print(f"{r['mode']:>6}: hit@1 {r['hit_at_1']:.2f}  hit@3 {r['hit_at_k']:.2f}  MRR {r['mrr']:.2f}")
    print("Wrote evals/RETRIEVAL.md")


if __name__ == "__main__":
    main()
