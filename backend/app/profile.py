from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from typing import Optional, List
from datetime import datetime
from sqlalchemy import func

from models import (
    get_session, User, BookShelf, SearchEvent, UserBadge, ShelfStatus
)
from auth import get_current_user  # reuse your bearer/cookie auth


router = APIRouter(prefix="/me", tags=["me"])

# ---------- helpers ----------
def _has_badge(sess: Session, user_id: int, code: str) -> bool:
    return bool(sess.exec(
        select(UserBadge).where(UserBadge.user_id==user_id, UserBadge.code==code)
    ).first())

def _award(sess: Session, user_id: int, code: str, name: str, desc: str):
    if _has_badge(sess, user_id, code): 
        return
    sess.add(UserBadge(user_id=user_id, code=code, name=name, description=desc))
    sess.commit()

def recompute_badges(sess: Session, user_id: int):
    # 1) First question
    qcount = sess.exec(
        select(func.count(SearchEvent.id)).where(SearchEvent.user_id==user_id)
    ).one()
    if qcount and qcount[0] >= 1:
        _award(sess, user_id, "FIRST_QUESTION", "First question", "Asked your first question.")

    # 2) Explorer (10+ searches)
    if qcount and qcount[0] >= 10:
        _award(sess, user_id, "EXPLORER", "Explorer", "10+ searches logged.")

    # 3) Voracious (read 5 books)
    rcount = sess.exec(
        select(func.count(BookShelf.id)).where(BookShelf.user_id==user_id, BookShelf.status==ShelfStatus.READ)
    ).one()
    if rcount and rcount[0] >= 5:
        _award(sess, user_id, "VORACIOUS", "Voracious reader", "Finished 5 books.")

# ---------- schemas ----------
class ShelfItemIn(BaseModel):
    title: str
    author: Optional[str] = ""
    status: ShelfStatus = ShelfStatus.WANT

class ShelfItemPatch(BaseModel):
    status: ShelfStatus

# ---------- routes ----------
@router.get("")
def me(user: User = Depends(get_current_user), sess: Session = Depends(get_session)):
    searches = sess.exec(select(func.count(SearchEvent.id)).where(SearchEvent.user_id==user.id)).one()[0]
    want = sess.exec(select(func.count(BookShelf.id)).where(BookShelf.user_id==user.id, BookShelf.status==ShelfStatus.WANT)).one()[0]
    read = sess.exec(select(func.count(BookShelf.id)).where(BookShelf.user_id==user.id, BookShelf.status==ShelfStatus.READ)).one()[0]
    return {
        "email": user.email,
        "display_name": user.email.split("@")[0],
        "stats": {"searches": searches, "want": want, "read": read},
    }

@router.get("/badges")
def my_badges(user: User = Depends(get_current_user), sess: Session = Depends(get_session)):
    return sess.exec(select(UserBadge).where(UserBadge.user_id==user.id).order_by(UserBadge.awarded_at.desc())).all()

@router.get("/shelf")
def shelf(status: Optional[ShelfStatus] = None, user: User = Depends(get_current_user), sess: Session = Depends(get_session)):
    q = select(BookShelf).where(BookShelf.user_id==user.id).order_by(BookShelf.added_at.desc())
    if status: q = q.where(BookShelf.status==status)
    return sess.exec(q).all()

@router.post("/shelf")
def shelf_add(item: ShelfItemIn, user: User = Depends(get_current_user), sess: Session = Depends(get_session)):
    row = BookShelf(user_id=user.id, title=item.title, author=item.author or "", status=item.status)
    sess.add(row); sess.commit(); sess.refresh(row)
    recompute_badges(sess, user.id)
    return row

@router.patch("/shelf/{item_id}")
def shelf_patch(item_id: int, patch: ShelfItemPatch, user: User = Depends(get_current_user), sess: Session = Depends(get_session)):
    row = sess.get(BookShelf, item_id)
    if not row or row.user_id != user.id: raise HTTPException(404, "Not found")
    row.status = patch.status
    sess.add(row); sess.commit()
    recompute_badges(sess, user.id)
    return {"ok": True}

@router.delete("/shelf/{item_id}")
def shelf_delete(item_id: int, user: User = Depends(get_current_user), sess: Session = Depends(get_session)):
    row = sess.get(BookShelf, item_id)
    if not row or row.user_id != user.id: raise HTTPException(404, "Not found")
    sess.delete(row); sess.commit()
    return {"ok": True}

@router.post("/track/search")
def track_search(body: dict, user: User = Depends(get_current_user), sess: Session = Depends(get_session)):
    q = (body.get("query") or "").strip()
    if not q: return {"skipped": True}
    sess.add(SearchEvent(user_id=user.id, query=q)); sess.commit()
    recompute_badges(sess, user.id)
    return {"ok": True}