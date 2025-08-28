from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pathlib import Path
import json
import os
from fastapi import HTTPException
from .rag import retrieve, chat_recommendation, looks_like_book_query
from .tools import get_summary_by_title
from .profanity import is_clean
from .tts import text_to_speech_mp3
from .auth import router as auth_router
from .profile import router as me_router

app = FastAPI(title="Smart Librarian")

# ---- CORS ----
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "null",  # covers file:// in some browsers
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# ---- Routers ----
app.include_router(me_router)
app.include_router(auth_router)

# ---- Serve static frontend at /ui ----
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="ui")

@app.get("/")
def root():
    if FRONTEND_DIR.exists():
        return RedirectResponse(url="/ui/")
    return {"message": "API running", "try": ["/health", "POST /ask"]}

# ---- Schemas ----
class AskReq(BaseModel):
    query: str

class TTSReq(BaseModel):
    text: str
    lang: str | None = "en"   # default English

# ---- Health ----
@app.get("/health")
def health():
    return {"ok": True}

# ---- Ask (RAG + Tool) ----
@app.post("/ask")
def ask(req: AskReq):
    if not is_clean(req.query):
        return {"message": "Please rephrase without inappropriate language."}

    # Retrieve + confidence
    candidates, best_dist = retrieve(req.query, k=5)

    # Intent + quality gate
    MAX_DIST = float(os.getenv("RETRIEVAL_MAX_DISTANCE", "0.45"))  # tune if needed
    if (not looks_like_book_query(req.query)) and (best_dist > MAX_DIST):
        return {
            "message": (
                "I’m your book recommender and your request doesn’t look like a book question. "
                "Try something like:\n• Recommend me a dystopian novel about surveillance\n"
                "• A beginner-friendly fantasy adventure\n• A classic romance with sharp social commentary"
            )
        }

    if not candidates:
        raise HTTPException(status_code=404, detail="No matches found")

    llm = chat_recommendation(req.query, candidates)
    choice = llm.choices[0]
    tool_calls = getattr(choice.message, "tool_calls", None) or []

    if tool_calls:
        tc = tool_calls[0]
        if getattr(tc, "function", None) and tc.function.name == "get_summary_by_title":
            import json
            try:
                args = json.loads(getattr(tc.function, "arguments", "{}") or "{}")
            except Exception:
                args = {}
            title = (args.get("title") or "").strip()
            info = get_summary_by_title(title)
            if not info:
                # fallback to top candidate
                top = candidates[0]
                info = {
                    "title": top["title"], "author": top["author"],
                    "difficulty": top["difficulty"], "full_summary": top["doc"]
                }
            return {
                "recommended_title": info["title"],
                "author": info.get("author",""),
                "difficulty": info.get("difficulty",""),
                "detailed_summary": info["full_summary"],
                "alternatives": [
                    {"title": c["title"], "author": c["author"], "difficulty": c["difficulty"]}
                    for c in candidates[1:4]
                ],
            }

    # Fallback (no tool call)
    text = choice.message.content or f"I recommend {candidates[0]['title']}."
    return {
        "message": text,
        "alternatives": [
            {"title": c["title"], "author": c["author"], "difficulty": c["difficulty"]}
            for c in candidates[1:4]
        ],
    }

# ---- TTS ----
@app.post("/tts")
def tts(req: TTSReq):
    try:
        mp3 = text_to_speech_mp3(req.text, lang=req.lang or "en")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"TTS failed: {type(e).__name__}")
    return StreamingResponse(iter([mp3]), media_type="audio/mpeg")


