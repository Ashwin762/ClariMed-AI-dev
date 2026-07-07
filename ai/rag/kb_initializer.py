"""

Builds the ChromaDB vector store from the REAL authored markdown files in
/knowledge_base/disease/**/*.md, using genuine content-derived embeddings
(ai/rag/embeddings.py) instead of the old hardcoded placeholder vectors
([[1.0, 0.0], [0.0, 1.0]]) and duplicated inline strings.

Run this any time you add/edit a .md file in knowledge_base/ to rebuild
the vector store.
"""

import chromadb
from ai.rag.kb_loader import load_all_docs
from ai.rag.embeddings import embed_batch

COLLECTION_NAME = "clarimed_kb"


def initialize_medical_kb():
    chroma_client = chromadb.PersistentClient(path="./chroma_db")

    # Reset the collection so stale/fake data from earlier runs doesn't linger
    try:
        chroma_client.delete_collection(name=COLLECTION_NAME)
    except Exception:
        pass
    collection = chroma_client.get_or_create_collection(name=COLLECTION_NAME)

    docs = load_all_docs()
    if not docs:
        print("⚠️  No knowledge base .md files found under knowledge_base/disease/. Nothing to seed.")
        return

    # Embed the full document text (frontmatter keywords + all sections) so
    # retrieval can match on real medical vocabulary, not just the title.
    texts = [f"{d['disease_name']} {' '.join(d['keywords'])} {d['full_text']}" for d in docs]
    embeddings = embed_batch(texts)

    ids = [d["id"] for d in docs]
    documents = [d["full_text"] for d in docs]
    metadatas = [
        {
            "disease_name": d["disease_name"],
            "body_part": d["body_part"],
            "specialist": d["specialist"],
            "emergency_possible": d["emergency_possible"],
            "keywords": ", ".join(d["keywords"]),
        }
        for d in docs
    ]

    collection.upsert(
        documents=documents,
        ids=ids,
        embeddings=embeddings,
        metadatas=metadatas,
    )
    print(f"✅ Seeded ChromaDB with {len(docs)} real document(s) using content-derived embeddings:")
    for d in docs:
        print(f"   - {d['id']}: {d['disease_name']} ({d['body_part']})")


if __name__ == "__main__":
    initialize_medical_kb()