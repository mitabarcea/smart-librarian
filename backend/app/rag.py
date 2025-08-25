import os, chromadb
from pathlib import Path
from chromadb.config import Settings
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

APP_DIR    = Path(__file__).resolve().parent
CHROMA_DIR = os.getenv("CHROMA_DIR", str(APP_DIR / "data" / "chroma"))
CHAT_MODEL  = os.getenv("CHAT_MODEL", "gpt-4o-nano")
EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")

SYSTEM = (
    "You are a helpful librarian. From the retrieved context (a list of book "
    "titles with authors, difficulties, and short summaries), choose exactly ONE best title "
    "for the user's request. Then CALL the tool get_summary_by_title with that exact title. "
    "If the user mentions an easier/harder read, consider the difficulty labels "
    "(Beginner / Intermediate / Advanced). Always answer in English."
)

client_oai = OpenAI()

def _embed_query(text: str):
    return client_oai.embeddings.create(model=EMBED_MODEL, input=[text]).data[0].embedding

def _col():
    client = chromadb.PersistentClient(path=CHROMA_DIR, settings=Settings())
    try:
        return client.get_collection("books")
    except Exception as e:
        raise RuntimeError(f"No 'books' collection in {CHROMA_DIR}. Did you run ingestion?") from e

def retrieve(query: str, k=5):
    emb = _embed_query(query)
    col = _col()
    res = col.query(
        query_embeddings=[emb],
        n_results=k,
        include=["metadatas","documents","distances"]  # distances for confidence gating
    )
    metas = res["metadatas"][0]
    docs  = res["documents"][0]
    dists = res["distances"][0] if "distances" in res else [1.0]
    hits = []
    for meta, doc in zip(metas, docs):
        hits.append({
            "title": meta.get("title",""),
            "author": meta.get("author",""),
            "difficulty": meta.get("difficulty",""),
            "short_summary": meta.get("short_summary",""),
            "doc": doc,
        })
    best_dist = dists[0] if dists else 1.0
    return hits, best_dist

def chat_recommendation(user_query: str, retrieved):
    context = "\n\n".join([
        f"- {x['title']} — {x['author']} [{x['difficulty']}]: {x['short_summary']}"
        for x in retrieved
    ])
    tools = [{
      "type": "function",
      "function": {
        "name": "get_summary_by_title",
        "description": "Return full details of a book by exact title.",
        "parameters": {"type": "object", "properties": {"title":{"type":"string"}}, "required":["title"]},
      }
    }]
    msg = [
      {"role":"system","content": SYSTEM},
      {"role":"user","content": user_query},
      {"role":"system","content": f"Context (top matches):\n{context}\n\nPick one title and call the tool with that exact title."}
    ]
    return client_oai.chat.completions.create(
        model=CHAT_MODEL, messages=msg, tools=tools, tool_choice="auto",
        temperature=0.3, max_tokens=500
    )


def looks_like_book_query(q: str) -> bool:
    ql = (q or "").lower()
    keywords = [
        "book","novel","read","reading","author","recommend","suggest",
        "fantasy","sci-fi","science fiction","romance","mystery","thriller",
        "history","biography","literature","story","stories","series"
    ]
    return any(k in ql for k in keywords)