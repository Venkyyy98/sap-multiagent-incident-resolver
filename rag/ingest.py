"""Ingest historical incident knowledge base into ChromaDB vector store."""
import json
from pathlib import Path
import chromadb
from config import settings
from rag.embeddings import EMBEDDER

DATA = Path(__file__).parent.parent / "data" / "knowledge_base.json"


def get_collection():
    client = chromadb.PersistentClient(path=settings.chroma_dir)
    return client.get_or_create_collection("cpi_incidents", embedding_function=EMBEDDER, metadata={"hnsw:space": "cosine"})


def ingest():
    docs = json.loads(DATA.read_text())
    col = get_collection()
    col.upsert(
        ids=[d["id"] for d in docs],
        documents=[d["text"] for d in docs],
        metadatas=[{"error_type": d["error_type"], "resolution": d["resolution"]} for d in docs],
    )
    print(f"Ingested {len(docs)} KB documents into ChromaDB at {settings.chroma_dir}")


if __name__ == "__main__":
    ingest()
