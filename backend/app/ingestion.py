import os, json
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
import chromadb
from chromadb.config import Settings

load_dotenv()

APP_DIR   = Path(__file__).resolve().parent              # .../backend/app
DATA_DIR  = APP_DIR / "data"                             # single source of truth
JSONL_FILE = DATA_DIR / "books.jsonl"
CHROMA_DIR = os.getenv("CHROMA_DIR", str(DATA_DIR / "chroma"))
EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")

client = OpenAI()

def load_books():
    if not JSONL_FILE.exists():
        raise SystemExit(f"[INGESTION] books.jsonl not found at: {JSONL_FILE}\n"
                         "Create it and run: python -m app.ingestion")

    items = []
    # utf-8-sig removes a BOM if present
    with open(JSONL_FILE, "r", encoding="utf-8-sig") as f:
        for ln, raw in enumerate(f, 1):
            s = raw.strip()
            if not s or s.startswith("#") or s.startswith("//"):  # allow empty or comment lines
                continue
            try:
                obj = json.loads(s)
            except json.JSONDecodeError as e:
                raise SystemExit(
                    f"[INGESTION] JSONL parse error at line {ln}: {e.msg} (col {e.colno}).\n"
                    f"Offending line:\n{s}"
                )
            items.append({
                "title": obj["title"].strip(),
                "author": obj.get("author","").strip(),
                "difficulty": obj.get("difficulty","Intermediate").strip(),
                "short_summary": obj.get("short_summary","").strip(),
                "full_summary": obj.get("full_summary", obj.get("short_summary","")).strip(),
            })
    print(f"[INGESTION] Loaded {len(items)} books from {JSONL_FILE}")
    return items

def embed(texts):
    resp = client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [d.embedding for d in resp.data]

def main():
    books = load_books()
    embed_texts = [f"{b['title']}\n{b['author']}\n{b['short_summary']}\n{b['difficulty']}" for b in books]
    embs = embed(embed_texts)

    chroma = chromadb.PersistentClient(path=CHROMA_DIR, settings=Settings())
    try: chroma.delete_collection("books")
    except Exception: pass
    col = chroma.create_collection(name="books", metadata={"hnsw:space":"cosine"})

    col.add(
        ids=[f"book_{i}" for i in range(len(books))],
        documents=[b["full_summary"] for b in books],
        metadatas=[{
            "title": b["title"], "author": b["author"], "difficulty": b["difficulty"],
            "short_summary": b["short_summary"],
        } for b in books],
        embeddings=embs,
    )
    print(f"[INGESTION] Indexed {len(books)} books into {CHROMA_DIR}")

if __name__ == "__main__":
    main()
