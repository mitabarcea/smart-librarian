import os, chromadb
from pathlib import Path
from dotenv import load_dotenv
from chromadb.config import Settings

load_dotenv()
APP_DIR    = Path(__file__).resolve().parent
CHROMA_DIR = os.getenv("CHROMA_DIR", str(APP_DIR / "data" / "chroma"))

def get_summary_by_title(title: str):
    if not title:
        return None
    t = title.strip().strip('"\'')

    client = chromadb.PersistentClient(path=CHROMA_DIR, settings=Settings())
    col = client.get_collection("books")

    r = col.get(where={"title": t})
    if r["ids"]:
        meta, full = r["metadatas"][0], r["documents"][0]
        return {
            "title": meta.get("title", t),
            "author": meta.get("author",""),
            "difficulty": meta.get("difficulty",""),
            "full_summary": full,
        }

    # small fallback: case-insensitive exact match
    allr = col.get()
    for i, m in enumerate(allr["metadatas"]):
        if m.get("title","").strip().lower() == t.lower():
            return {
                "title": m.get("title", t),
                "author": m.get("author",""),
                "difficulty": m.get("difficulty",""),
                "full_summary": allr["documents"][i],
            }
    return None

