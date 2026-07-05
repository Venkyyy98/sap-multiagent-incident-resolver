"""Semantic retrieval over the historical incident knowledge base."""
from rag.ingest import get_collection


def retrieve_similar(query: str, k: int = 3) -> list[dict]:
    col = get_collection()
    res = col.query(query_texts=[query], n_results=k)
    out = []
    for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        out.append({"text": doc, "resolution": meta["resolution"],
                    "error_type": meta["error_type"], "similarity": round(1 - dist, 3)})
    return out
