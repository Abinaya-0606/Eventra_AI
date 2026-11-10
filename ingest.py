"""Reads data/*.txt, chunks them, and stores embeddings in ChromaDB (safe to re-run).

Usage:  python ingest.py
"""
import os
import sys

from app import create_app
from app.services.rag import KnowledgeBaseError, get_collection, load_chunks


def main() -> int:
    app = create_app(os.getenv("APP_ENV", "development"))
    with app.app_context():
        try:
            chunks = load_chunks()
            if not chunks:
                print(f"ERROR: no .txt files found in {app.config['DATA_DIR']}")
                return 1
            collection = get_collection()
            ids = [c["id"] for c in chunks]

            # remove chunks of documents that no longer exist, then upsert (no duplicates)
            keep = set(ids)
            stale = [i for i in collection.get()["ids"] if i not in keep]
            if stale:
                collection.delete(ids=stale)
            collection.upsert(
                ids=ids,
                documents=[c["text"] for c in chunks],
                metadatas=[{"source": c["source"]} for c in chunks],
            )
            print(f"SUCCESS: {len(chunks)} chunks from {len({c['source'] for c in chunks})} documents "
                  f"stored. Collection now holds {collection.count()} chunks.")
            return 0
        except KnowledgeBaseError as exc:
            print(f"ERROR: {exc}")
            return 1
        except Exception as exc:  # show a friendly message instead of a traceback
            print(f"ERROR: ingestion failed: {exc}")
            return 1


if __name__ == "__main__":
    sys.exit(main())
